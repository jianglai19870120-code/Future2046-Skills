#!/usr/bin/env python3
"""Read account workbooks and materialize independently reviewed viral roots."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

ELEMENTS = ("人群", "成本", "猎奇", "反差", "最差", "荷尔蒙", "头牌", "怀旧")
WORST_BASES = ("极端体验",)
WORST_TRIGGER_WHITELIST = (
    "最坏", "最差", "最难吃", "最难喝", "最难用", "最不好", "最不好的",
    "最垃圾", "最失败", "最糟", "最糟糕", "最黑暗", "极差", "极烂", "一文不值",
)
SOURCE_FIELDS = ("account", "source_file", "sheet", "row", "title", "clean_title", "url", "likes", "comments", "favorites", "shares")
ALIASES = {
    "title": ("作品标题", "标题", "作品名称", "视频标题", "视频信息", "作品文案", "title"),
    "likes": ("点赞数", "点赞", "获赞", "点赞量", "likes"),
    "comments": ("评论数", "评论", "评论量", "comments"),
    "favorites": ("收藏数", "收藏", "收藏量", "favorites"),
    "shares": ("分享数", "分享", "转发数", "转发", "分享量", "shares"),
    "url": ("作品链接", "视频链接", "链接", "作品地址", "视频地址", "url"),
}


# Some legacy account exports do not contain a 收藏数 column.  In that case
# the missing metric is explicitly treated as zero; it is never inferred from
# another interaction count.
REQUIRED = ("title", "likes", "comments", "shares")


def norm_header(value: object) -> str:
    return re.sub(r"[\s_\-（）()：:]+", "", str(value or "")).casefold()


def number(value: object, file: Path, sheet: str, row: int, field: str) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    if isinstance(value, bool):
        raise ValueError(f"{file.name}/{sheet} row {row}: {field} is boolean")
    try:
        result = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{file.name}/{sheet} row {row}: invalid {field}={value!r}") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{file.name}/{sheet} row {row}: invalid {field}={value!r}")
    return result


def read_biff_with_excel(path: Path, runtime_dir: Path | None = None) -> list[dict]:
    """Read legacy BIFF workbooks with Excel itself to honor the file's text encoding."""
    if os.name != "nt":
        raise RuntimeError("旧版 .xls 需要 Windows 本机 Excel；未尝试使用可能乱码的替代解码器")
    helper = Path(__file__).with_name("read_xls_com.ps1")
    if runtime_dir is not None:
        runtime_dir = runtime_dir.resolve()
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / ".runtime-keep").touch(exist_ok=True)
    fd, output_name = tempfile.mkstemp(prefix="viral-root-xls-", suffix=".json", dir=str(runtime_dir) if runtime_dir else None)
    os.close(fd)
    output_path = Path(output_name)
    # The Excel bridge writes by path after Python creates the placeholder.
    # Reassert the parent immediately before starting PowerShell so a stale
    # cleanup from another interrupted run cannot remove the bridge directory.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(helper), str(path), str(output_path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Excel COM 只读读取失败：{completed.stderr.strip() or completed.stdout.strip()}")
        data = json.loads(output_path.read_text(encoding="utf-8"))
        if completed.returncode and not data.get("error"):
            raise RuntimeError(f"Excel COM 只读读取失败：{completed.stderr.strip() or completed.stdout.strip()}")
    finally:
        output_path.unlink(missing_ok=True)
    if data.get("error"):
        raise RuntimeError(data["error"])
    return data["sheets"]


def read_workbook(path: Path, runtime_dir: Path | None = None) -> list[dict]:
    raw = path.read_bytes()
    is_biff = raw.startswith(bytes.fromhex("D0CF11E0A1B11AE1"))
    is_zip = raw.startswith(b"PK\x03\x04")
    if is_biff:
        sheets = read_biff_with_excel(path, runtime_dir=runtime_dir)
    elif is_zip:
        import openpyxl
        book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            sheets = [{"name": s.title, "start_row": 1, "rows": list(s.iter_rows(values_only=True))} for s in book.worksheets]
        finally:
            book.close()
    else:
        raise ValueError(f"unsupported workbook signature: {path}")
    records = []
    for sheet in sheets:
        sheet_name = sheet["name"] if isinstance(sheet, dict) else sheet[0]
        rows = sheet["rows"] if isinstance(sheet, dict) else sheet[1]
        start_row = int(sheet.get("start_row", 1)) if isinstance(sheet, dict) else 1
        if not rows:
            continue
        header_idx = None
        columns = {}
        for idx, row in enumerate(rows[:10]):
            mapped = {}
            for col, value in enumerate(row):
                h = norm_header(value)
                for key, aliases in ALIASES.items():
                    if h and any(h == norm_header(a) for a in aliases):
                        mapped.setdefault(key, col)
            if all(k in mapped for k in REQUIRED):
                header_idx, columns = idx, mapped
                break
        if header_idx is None:
            if any(str(v or "").strip() for v in rows[0]):
                raise ValueError(f"{path.name}/{sheet_name}: cannot map required columns; headers={rows[0]!r}")
            continue
        if any("\ufffd" in str(v or "") for row in rows for v in row):
            raise ValueError(f"{path.name}/{sheet_name}: text contains replacement characters; refusing to publish corrupted titles")
        for offset, row in enumerate(rows[header_idx + 1 :], start=header_idx + 1):
            source_row = start_row + offset
            def cell(key: str):
                col = columns.get(key)
                return row[col] if col is not None and col < len(row) else None
            title = str(cell("title") or "").strip()
            if not title:
                continue
            clean = re.split(r"[#＃]", title, maxsplit=1)[0].strip()
            if not clean:
                continue
            metrics = {k: number(cell(k), path, sheet_name, source_row, k) for k in ("likes", "comments", "favorites", "shares")}
            rec = {
                "account": path.stem, "source_file": path.name, "sheet": sheet_name, "row": source_row,
                "title": title, "clean_title": clean, "url": str(cell("url") or "").strip(), **metrics,
            }
            rec["heat"] = rec["likes"] + rec["comments"] * 1.5 + rec["favorites"] * 1.2 + rec["shares"] * 1.5
            rec["source_id"] = hashlib.sha256(json.dumps([rec["account"], rec["sheet"], rec["row"], rec["url"] or rec["title"]], ensure_ascii=False).encode()).hexdigest()[:20]
            rec["review_key"] = hashlib.sha256(json.dumps([rec["account"], rec["clean_title"]], ensure_ascii=False).encode()).hexdigest()[:24]
            records.append(rec)
    return records


def roundheat(v: float) -> str:
    # Heat is aggregated with full precision first, then displayed using
    # ordinary half-up rounding. All source metrics are non-negative.
    return str(math.floor(v + 0.5))


def validate_worst_decision(title: str, item: dict) -> None:
    """Require explicit extreme-bad or failed-result evidence for 最差."""
    status = item.get("status", item.get("reviewer_verdict", "approved"))
    if item.get("element") != "最差" or status != "approved":
        return
    basis = str(item.get("worst_basis", "")).strip()
    trigger = str(item.get("worst_trigger", "")).strip()
    evidence = item.get("evidence")
    if basis not in WORST_BASES:
        raise ValueError(f"最差词根必须使用 worst_basis=极端体验: {title} / {item.get('root')}")
    if not trigger or trigger not in title:
        raise ValueError(f"最差词根必须提供标题中的 worst_trigger: {title} / {item.get('root')}")
    if trigger not in WORST_TRIGGER_WHITELIST:
        raise ValueError(f"最差词根的 worst_trigger 不在严格白名单: {title} / {trigger}")
    if not isinstance(evidence, list) or trigger not in [str(piece) for piece in evidence]:
        raise ValueError(f"最差词根的 worst_trigger 必须同时列入 evidence: {title} / {trigger}")


def reusable_audit(title: str, analysis: object, decisions: object) -> bool:
    """Reject legacy audits that cannot satisfy the current 最差 hard gate."""
    if not isinstance(analysis, dict) or not isinstance(decisions, list):
        return False
    if not all(isinstance(item, dict) and isinstance(item.get("evidence"), list) for item in decisions):
        return False
    for item in decisions:
        if item.get("element") == "最差" and item.get("status", item.get("reviewer_verdict", "approved")) == "approved":
            try:
                validate_worst_decision(title, item)
            except ValueError:
                return False
    return True


def slug(text: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text).strip(" .") or "未命名"


def md(text: object) -> str:
    return str(text or "").replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def validate_title_analysis(title: str, analysis: object, decisions: list[dict]) -> None:
    if not isinstance(analysis, dict):
        raise ValueError(f"title analysis must be an object: {title}")
    for field in ("semantic_summary", "candidate_summary"):
        if not str(analysis.get(field, "")).strip():
            raise ValueError(f"title analysis missing {field}: {title}")
    checks = analysis.get("element_checks")
    if not isinstance(checks, list) or len(checks) != len(ELEMENTS):
        raise ValueError(f"title analysis must check all eight elements: {title}")
    by_element = {}
    for check in checks:
        if not isinstance(check, dict) or check.get("element") not in ELEMENTS or check["element"] in by_element:
            raise ValueError(f"title analysis has invalid element checks: {title}")
        if not isinstance(check.get("applicable"), bool) or not str(check.get("reason", "")).strip():
            raise ValueError(f"title analysis element checks need a boolean and reason: {title}")
        by_element[check["element"]] = check
    if set(by_element) != set(ELEMENTS):
        raise ValueError(f"title analysis is missing an element check: {title}")
    for item in decisions:
        element = item.get("element")
        if item.get("status", item.get("reviewer_verdict", "approved")) == "approved" and (element not in by_element or not by_element[element]["applicable"]):
            raise ValueError(f"approved root contradicts title analysis: {title} / {item.get('root')}")


def confined_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"managed path must be relative and remain inside its root: {relative}")
    target = (root / candidate).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError(f"managed path escapes its root: {relative}")
    return target


def cleanup_runtime_dir(runtime_dir: Path) -> None:
    """Remove transient Excel bridge files and the runtime directory."""
    try:
        if not runtime_dir.is_dir():
            return
        for item in runtime_dir.iterdir():
            # account-sync-*.json is the active review input created by the
            # batch controller; only the Excel COM bridge files are transient
            # at this stage. The controller removes its own input afterward.
            if item.is_file() and (item.name.startswith("viral-root-xls-") or item.name == ".runtime-keep"):
                item.unlink(missing_ok=True)
        # Keep the workspace cache directory itself in place.  Batch commits
        # can run another read immediately (or concurrently after a retry),
        # and the Excel bridge writes its JSON after the PowerShell process
        # starts.  Removing the parent directory here creates a race where
        # COM cannot write the result even though Python created the temp path.
        runtime_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def unique_path(path: Path) -> Path:
    candidate = path
    index = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        index += 1
    return candidate


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--reviews", help="UTF-8 JSON review decisions keyed by review key or exact cleaned title")
    ap.add_argument("--accounts", nargs="+", help="只同步这些已完成账号；未指定时同步全部账号")
    ap.add_argument("--rebuild-all", action="store_true", help="require fresh review decisions and archive prior managed outputs")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    cfg = yaml.safe_load((ws / "workspace.yaml").read_text(encoding="utf-8"))
    source, output, records_dir, archive = tuple((ws / cfg[k]).resolve() for k in ("source_root", "output_root", "record_root", "archive_root"))
    for p in (source, output, records_dir, archive):
        if not p.is_relative_to(ws):
            raise ValueError(f"workspace path escapes root: {p}")
    if not source.is_dir():
        raise ValueError(f"source directory does not exist: {source}")
    runtime_dir = records_dir / ".运行缓存"
    if not runtime_dir.is_relative_to(records_dir):
        raise ValueError("runtime cache path must stay inside record_root")
    element_dirs = cfg.get("element_directories", {})
    if set(element_dirs) != set(ELEMENTS):
        raise ValueError("workspace.yaml must map all eight supported elements to their existing directories")
    resolved_element_dirs = {}
    for element, relative in element_dirs.items():
        target = (output / relative).resolve()
        if not target.is_relative_to(output) or not target.is_dir():
            raise ValueError(f"configured element directory must already exist under output_root: {element} -> {relative}")
        resolved_element_dirs[element] = target.relative_to(output).as_posix()
    state_file = confined_path(records_dir, "source-snapshot.json")
    report_file = confined_path(records_dir, "最近一次同步.md")
    dictionary_file = confined_path(output, "爆款词根词典.md")
    previous = json.loads(state_file.read_text(encoding="utf-8")) if state_file.exists() else {"records": {}, "artifacts": {}}
    prior_audits = previous.get("audit_records", {})
    previous_records = previous.get("records", {})
    prior_audits_by_key = {}
    for source_id, record in previous_records.items():
        account, title = record.get("account"), record.get("clean_title")
        if not account or not title:
            continue
        key = hashlib.sha256(json.dumps([account, title], ensure_ascii=False).encode()).hexdigest()[:24]
        prior_entry = prior_audits.get(key, prior_audits.get(source_id, {}))
        decisions = prior_entry.get("decisions", []) if isinstance(prior_entry, dict) else None
        analysis = prior_entry.get("analysis") if isinstance(prior_entry, dict) else None
        if reusable_audit(title, analysis, decisions):
            prior_audits_by_key.setdefault(key, {"analysis": analysis, "decisions": decisions})
    inputs = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".xls", ".xlsx", ".xlsm") and not p.name.startswith("~$"))
    if not inputs:
        raise ValueError(f"no supported account workbooks found under {source}")
    current = []
    failures = []
    for path in inputs:
        try:
            current.extend(read_workbook(path, runtime_dir=runtime_dir))
        except Exception as exc:
            failures.append(f"{path.name}: {exc}")
    cleanup_runtime_dir(runtime_dir)
    if failures:
        print("INPUT ERRORS; no outputs updated")
        print("\n".join(failures))
        return 2
    if not current:
        raise ValueError("workbooks were readable but contained no usable titled records; refusing to replace existing outputs")
    by_account_title = {}
    for r in current:
        by_account_title.setdefault((r["account"], r["clean_title"]), []).append(r)
    excluded = []
    selected = []
    for group in by_account_title.values():
        best = max(x["likes"] for x in group)
        selected.extend(x for x in group if x["likes"] == best)
        excluded.extend(x for x in group if x["likes"] != best)
    account_scope = set(args.accounts or [])
    if account_scope:
        unknown = sorted(account_scope - {r["account"] for r in selected})
        if unknown:
            raise ValueError(f"requested account is not present in selected source records: {unknown}")
        selected = [r for r in selected if r["account"] in account_scope]
        excluded = [r for r in excluded if r["account"] in account_scope]
    reviews = {}
    if args.reviews:
        review_path = Path(args.reviews).resolve()
        if not review_path.is_relative_to(ws) or not review_path.is_file():
            raise ValueError(f"review JSON must be an existing file inside the configured workspace: {review_path}")
        reviews = json.loads(review_path.read_text(encoding="utf-8"))
        if not isinstance(reviews, dict) or any(not isinstance(value, dict) or not isinstance(value.get("decisions"), list) or not isinstance(value.get("analysis"), dict) for value in reviews.values()):
            raise ValueError("review JSON must map review keys or titles to {analysis, decisions} objects")
    approved_matches = {}
    audit_records = {}
    pending = []
    unreviewed = []
    reviewed_keys = set()
    for r in selected:
        if r["source_id"] in reviews:
            found_entry = reviews[r["source_id"]]
        elif r["review_key"] in reviews:
            found_entry = reviews[r["review_key"]]
        elif r["clean_title"] in reviews:
            found_entry = reviews[r["clean_title"]]
        elif not args.rebuild_all and r["review_key"] in prior_audits_by_key:
            found_entry = prior_audits_by_key[r["review_key"]]
        elif args.dry_run:
            unreviewed.append({"account": r["account"], "title": r["clean_title"], "review_key": r["review_key"]})
            r["matches"] = []
            continue
        else:
            pending.append(r["clean_title"])
            continue
        if not isinstance(found_entry, dict) or not isinstance(found_entry.get("analysis"), dict) or not isinstance(found_entry.get("decisions"), list):
            raise ValueError(f"review entry lacks the required title analysis: {r['clean_title']}")
        analysis = found_entry["analysis"]
        found = found_entry["decisions"]
        validate_title_analysis(r["clean_title"], analysis, found)
        pending_before = len(pending)
        checked = []
        audited = []
        for item in found:
            term, element = str(item.get("root", "")).strip(), item.get("element")
            reviewer_verdict = item.get("reviewer_verdict", item.get("status", "approved"))
            status = item.get("status", "approved")
            audit_reason = str(item.get("audit_reason", "")).strip()
            rationale = str(item.get("rationale", "")).strip()
            auditor = str(item.get("auditor", "")).strip()
            evidence = item.get("evidence")
            if status not in ("approved", "rejected", "uncertain", "pending", "reclassify"):
                raise ValueError(f"unknown review status {status!r}: {r['clean_title']} / {term}")
            if status in ("uncertain", "pending", "reclassify") and item.get("user_decision"):
                status = "rejected"
            elif status in ("uncertain", "pending", "reclassify"):
                pending.append(f"{r['clean_title']} → {term or '未命名'} ({status})")
                audited.append({**item, "status": status})
                continue
            if not term or element not in ELEMENTS:
                raise ValueError(f"invalid model root match for {r['source_id']}: {item}")
            if not isinstance(evidence, list) or not evidence or any(not str(piece).strip() for piece in evidence):
                raise ValueError(f"evidence must be a non-empty array: {r['clean_title']} / {term}")
            if any(str(piece) not in r["clean_title"] for piece in evidence):
                raise ValueError(f"evidence is not present in title: {r['clean_title']} / {evidence}")
            derivation = str(item.get("derivation", "")).strip()
            audit_checks = item.get("audit_checks")
            if not derivation or not rationale or not audit_reason or not auditor:
                raise ValueError(f"review item lacks rationale or independent audit evidence: {r['clean_title']} / {term}")
            names = ("root_faithful", "evidence_exact", "element_valid", "reason_supported")
            if not isinstance(audit_checks, dict) or any(not isinstance(audit_checks.get(name), bool) for name in names):
                raise ValueError(f"review item lacks four independent audit checks: {r['clean_title']} / {term}")
            if status == "approved" and not all(audit_checks[name] for name in names):
                raise ValueError(f"approved review item has a failed audit check: {r['clean_title']} / {term}")
            if element == "最差" and status == "approved":
                validate_worst_decision(r["clean_title"], item)
            normalized = {"root": term, "element": element, "derivation": derivation, "rationale": rationale, "evidence": [str(piece) for piece in evidence], "auditor": auditor, "audit_checks": audit_checks, "audit_reason": audit_reason, "reviewer_verdict": reviewer_verdict, "status": status}
            if element == "最差" and status == "approved":
                normalized["worst_basis"] = str(item["worst_basis"]).strip()
                normalized["worst_trigger"] = str(item["worst_trigger"]).strip()
            if item.get("user_decision"):
                normalized["user_decision"] = item["user_decision"]
            audited.append(normalized)
            if status == "approved":
                checked.append(normalized)
            elif status != "rejected":
                pending.append(f"{r['clean_title']} → {term or '未命名'} ({status})")
        r["matches"] = checked
        approved_matches[r["source_id"]] = checked
        audit_records[r["review_key"]] = {"account": r["account"], "title": r["clean_title"], "analysis": analysis, "decisions": audited}
        if len(pending) == pending_before:
            reviewed_keys.add(r["review_key"])
    if pending and not args.dry_run:
        print("REVIEW REQUIRED; no outputs updated")
        for item in pending:
            print("- " + item)
        return 3
    # 同名词根如果归属不同元素，必须是两个独立条目；内部键固定为 (element, root)。
    root_entries = {}
    for r in selected:
        for hit in r["matches"]:
            root_key = (hit["element"], hit["root"])
            prior = root_entries.setdefault(root_key, {"element": hit["element"], "root": hit["root"], "rationales": [], "evidence": []})
            if hit["rationale"] not in prior["rationales"]:
                prior["rationales"].append(hit["rationale"])
            example = {"title": r["clean_title"], "evidence": hit["evidence"], "derivation": hit["derivation"], "auditor": hit["auditor"], "audit_reason": hit["audit_reason"]}
            if example not in prior["evidence"]:
                prior["evidence"].append(example)
    grouped = {}
    for r in selected:
        for hit in r["matches"]:
            root_key = (hit["element"], hit["root"])
            item = grouped.setdefault(root_key, {"element": hit["element"], "root": hit["root"], "heat": 0.0, "records": []})
            item["heat"] += r["heat"]
            item["records"].append(r)
    planned = {}
    for root_key, data in grouped.items():
        term = data["root"]
        filename = f"{slug(term)}_{roundheat(data['heat'])}.md"
        rel = Path(resolved_element_dirs[data["element"]]) / filename
        if rel.as_posix() in planned.values():
            raise ValueError(f"output filename collision for {data['element']} / {term!r}: {rel.as_posix()}")
        planned[root_key] = rel.as_posix()
    summary_lines = ["# 爆款词根汇总", "", "| 编号 | 爆款词根 | 爆款元素 | 爆款热度 | 出现次数 | 相关选题 |", "|---:|---|---|---:|---:|---|"]
    for i, root_key in enumerate(sorted(grouped, key=lambda k: (-grouped[k]["heat"], grouped[k]["root"], grouped[k]["element"])), 1):
        d = grouped[root_key]
        term = d["root"]
        summary_lines.append(f"| {i} | {md(term)} | {d['element']} | {roundheat(d['heat'])} | {len(d['records'])} | [查看选题](<./{planned[root_key]}>) |")
    rendered = {"爆款词根汇总.md": "\n".join(summary_lines) + "\n"}
    dictionary_lines = ["# 爆款词根词典", "", "本词典只收录通过独立 AI 审核的词根。二级标题为爆款元素，三级标题为归属于该元素的标准爆款词根。元素定义见 Skill 的《八大爆款元素词典》。每个词根条目保留分类理由、标题证据和复核结论。", ""]
    for element in ELEMENTS:
        terms = sorted((root_key for root_key, item in root_entries.items() if item["element"] == element), key=lambda key: key[1])
        dictionary_lines += [f"## {element}", ""]
        if not terms:
            dictionary_lines += ["暂无已审核通过的词根。", ""]
            continue
        for root_key in terms:
            item = root_entries[root_key]
            term = item["root"]
            dictionary_lines += [f"### {term}", "", f"- 爆款元素：{item['element']}", f"- 分类理由：{'；'.join(item['rationales'])}", "- 独立审核状态：通过", "- 标题证据："]
            for example in item["evidence"]:
                evidence_text = "、".join(f"“{piece}”" for piece in example["evidence"])
                dictionary_lines.append(f"  - “{example['title']}”中的证据：{evidence_text}；提炼说明：{example['derivation']}；独立审核：{example['audit_reason']}（{example['auditor']}）")
            dictionary_lines.append("")
    rendered[dictionary_file.name] = "\n".join(dictionary_lines) + "\n"
    for root_key, d in grouped.items():
        term = d["root"]
        p = Path(planned[root_key])
        lines = [f"# {term}_{roundheat(d['heat'])}", "", f"- 爆款元素：{d['element']}", f"- 爆款热度：{roundheat(d['heat'])}", f"- 出现次数：{len(d['records'])}", "", "## 相关选题", ""]
        for r in sorted(d["records"], key=lambda x: (x["account"], x["source_file"], x["row"])):
            lines += [f"### {md(r['account'])}｜{md(r['clean_title'])}", "", f"- 原始标题：{md(r['title'])}", f"- 点赞：{roundheat(r['likes'])}；评论：{roundheat(r['comments'])}；收藏：{roundheat(r['favorites'])}；分享：{roundheat(r['shares'])}", f"- 单条热度：{roundheat(r['heat'])}", f"- 来源：{md(r['source_file'])} / {md(r['sheet'])} / 第 {r['row']} 行"]
            if r["url"]:
                lines.append(f"- 作品：[打开链接](<{r['url']}>)")
            lines.append("")
        rendered[p.as_posix()] = "\n".join(lines)
    old_artifacts = previous.get("artifacts", {})
    if not isinstance(old_artifacts, dict):
        raise ValueError("snapshot artifacts must be a mapping")
    old_paths = [str(value) for value in old_artifacts.values()]
    if len(old_paths) != len(set(old_paths)):
        raise ValueError("snapshot maps multiple roots to the same output path")
    for old_rel in old_paths:
        confined_path(output, old_rel)
    active_rel = set(rendered)
    to_archive = []
    for term, old_rel in old_artifacts.items():
        if old_rel not in active_rel:
            to_archive.append((term, old_rel))
    old_records = previous.get("records", {})
    now_records = {r["source_id"]: {k: r[k] for k in ("account", "source_file", "sheet", "row", "title", "clean_title", "url", "likes", "comments", "favorites", "shares", "review_key")} for r in current}
    diff = {
        "added": sorted(now_records.keys() - old_records.keys()),
        "removed": sorted(old_records.keys() - now_records.keys()),
        "changed": sorted(
            key for key in now_records.keys() & old_records.keys()
            if any(old_records[key].get(field) != now_records[key].get(field) for field in SOURCE_FIELDS)
        ),
    }
    if args.dry_run:
        no_candidate_titles = sum(not record["decisions"] for record in audit_records.values())
        review_tasks = {item["review_key"]: item for item in unreviewed}
        print(json.dumps({"workbooks": [p.name for p in inputs], "source_records": len(current), "selected_records": len(selected), "excluded_duplicates": len(excluded), "roots_from_reviewed_titles": len(grouped), "reviewed_titles": len(reviewed_keys), "no_candidate_titles": no_candidate_titles, "review_required": len(review_tasks) + len(set(pending)), "review_tasks": sorted(review_tasks.values(), key=lambda item: (item["account"], item["title"])), "pending_decisions": sorted(set(pending)), "changes": {k: len(v) for k, v in diff.items()}, "archive": to_archive, "outputs": sorted(rendered)}, ensure_ascii=False, indent=2))
        return 0

    generated_at = datetime.now().isoformat(timespec="seconds")
    state_roots = {f"{element}::{term}": item for (element, term), item in root_entries.items()}
    state_artifacts = {f"{element}::{term}": path for (element, term), path in planned.items()}
    state = {"schema_version": 5, "generated_at": generated_at, "records": now_records, "approved_matches": approved_matches, "audit_records": audit_records, "roots": state_roots, "artifacts": state_artifacts, "diff": diff}
    decisions = [decision for record in audit_records.values() for decision in record["decisions"]]
    approved_n = sum(d.get("status") == "approved" for d in decisions)
    rejected_n = sum(d.get("reviewer_verdict", d.get("status")) == "rejected" for d in decisions)
    uncertain_n = sum(d.get("reviewer_verdict") == "uncertain" for d in decisions)
    user_decided_n = sum(bool(d.get("user_decision")) for d in decisions)
    no_candidate_titles = sum(not record["decisions"] for record in audit_records.values())
    report = ["# 最近一次同步", "", f"- 时间：{generated_at}", f"- 账号表：{len(inputs)}", f"- 源记录：{len(current)}", f"- 参与分析：{len(selected)}", f"- 重复标题排除：{len(excluded)}（点赞并列最高均保留）", f"- 审核覆盖标题：{len(reviewed_keys)}", f"- 无候选词根标题：{no_candidate_titles}", f"- 审核关系：通过 {approved_n}、驳回 {rejected_n}、有争议 {uncertain_n}（用户裁定排除 {user_decided_n}）", f"- 当前词根：{len(grouped)}", f"- 数据变化：新增 {len(diff['added'])}、修改 {len(diff['changed'])}、删除 {len(diff['removed'])}", f"- 归档：{len(to_archive)}", "", "## 词根热度前十", ""]
    for root_key in sorted(grouped, key=lambda k: (-grouped[k]["heat"], grouped[k]["root"], grouped[k]["element"]))[:10]:
        d = grouped[root_key]
        report.append(f"- {d['root']}（{d['element']}）：{roundheat(d['heat'])}，{len(d['records'])} 条")
    if not previous.get("records"):
        report += ["", "首次运行：已建立基线。"]

    output_targets = {confined_path(output, rel): content for rel, content in rendered.items()}
    output_targets[state_file] = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    output_targets[report_file] = "\n".join(report) + "\n"
    if len(output_targets) != len(rendered) + 2:
        raise ValueError("output paths overlap; refusing to write ambiguous artifacts")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = unique_path(records_dir / "备份" / stamp)
    if not backup.resolve().is_relative_to(records_dir):
        raise ValueError("backup path escapes the configured record directory")
    backup.mkdir(parents=True, exist_ok=False)
    archive.mkdir(parents=True, exist_ok=True)
    managed_before = {confined_path(output, str(rel)) for rel in old_artifacts.values()}
    managed_before.update((confined_path(output, "爆款词根汇总.md"), dictionary_file, state_file, confined_path(records_dir, report_file.name)))
    backup_map = {}
    for original in sorted(managed_before, key=str):
        if original.is_file():
            rel = original.relative_to(ws)
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, saved)
            backup_map[original] = saved

    archive_moves = []
    if args.rebuild_all:
        archive_run = unique_path(archive / f"重审前-{stamp}")
        for rel in old_artifacts.values():
            src = confined_path(output, str(rel))
            dst = archive_run / "02_爆款词根" / Path(rel)
            if src.is_file():
                archive_moves.append((src, dst))
        known = (confined_path(output, "爆款词根汇总.md"), dictionary_file, confined_path(records_dir, "词根词典.yaml"), state_file, report_file)
        for src in known:
            if src.is_file():
                archive_moves.append((src, archive_run / src.relative_to(ws)))
    else:
        for _, rel in to_archive:
            src = confined_path(output, str(rel))
            if src.is_file():
                archive_moves.append((src, archive / stamp / Path(rel)))
    finalized_moves = []
    archive_destinations = set()
    for src, dst in archive_moves:
        if not dst.resolve().is_relative_to(archive.resolve()):
            raise ValueError(f"archive destination escapes archive root: {dst}")
        unique_dst = unique_path(dst)
        if unique_dst.resolve() in archive_destinations:
            raise ValueError(f"duplicate archive destination: {unique_dst}")
        archive_destinations.add(unique_dst.resolve())
        finalized_moves.append((src, unique_dst))

    with tempfile.TemporaryDirectory(prefix=".viral-root-stage-", dir=records_dir) as stage_name:
        stage = Path(stage_name)
        staged = {}
        for target, content in output_targets.items():
            stage_file = stage / target.relative_to(ws)
            stage_file.parent.mkdir(parents=True, exist_ok=True)
            stage_file.write_text(content, encoding="utf-8")
            staged[target] = stage_file
        created_archives = []
        committed_targets = []
        try:
            for src, dst in finalized_moves:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                created_archives.append(dst)
            for target, stage_file in staged.items():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(stage_file, target)
                committed_targets.append(target)
        except Exception:
            for target in reversed(committed_targets):
                if target in backup_map:
                    restore = stage / "rollback" / target.relative_to(ws)
                    restore.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(backup_map[target], restore)
                    os.replace(restore, target)
                else:
                    target.unlink(missing_ok=True)
            for archived in reversed(created_archives):
                archived.unlink(missing_ok=True)
            for original, saved in backup_map.items():
                if original.exists():
                    continue
                original.parent.mkdir(parents=True, exist_ok=True)
                restore = stage / "rollback" / original.relative_to(ws)
                restore.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, restore)
                os.replace(restore, original)
            raise
    print(f"PASS: workbooks={len(inputs)} records={len(current)} selected={len(selected)} roots={len(grouped)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2)
