#!/usr/bin/env python3
"""Create and commit ten-title semantic review batches for viral-root sync.

This is a production workflow controller. It keeps review work resumable in the
target workspace and never writes source Excel files or formal output files.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    # Windows 控制台可能使用 GBK；标题必须原样输出，不能因 emoji 或中文导致 current/status 失败。
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

import sync_viral_roots as sync


DEFAULT_STATE = "98_处理记录/批次审核状态.json"
DEFAULT_QUEUE = "98_处理记录/批次审核队列.json"
WORST_QUEUE = "98_处理记录/最差复查队列.json"
WORST_STATE = "98_处理记录/最差复查状态.json"
WORST_DIR = "98_处理记录/最差复查"
STRICT_WORST_QUEUE = "98_处理记录/最差严格复核队列.json"
STRICT_WORST_STATE = "98_处理记录/最差严格复核状态.json"
STRICT_WORST_DIR = "98_处理记录/最差严格复核"


def inside(path: Path, root: Path) -> Path:
    value = path.resolve()
    if not value.is_relative_to(root.resolve()):
        raise ValueError(f"path must stay inside workspace: {value}")
    return value


def workspace_paths(ws: Path) -> tuple[Path, Path]:
    cfg = sync.yaml.safe_load((ws / "workspace.yaml").read_text(encoding="utf-8"))
    records = inside(ws / cfg["record_root"], ws)
    source = inside(ws / cfg["source_root"], ws)
    if not records.is_dir() or not source.is_dir():
        raise ValueError("configured source_root and record_root must exist")
    return source, records


def collect_selected(source: Path, records_dir: Path) -> tuple[list[dict], list[dict]]:
    inputs = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".xls", ".xlsx", ".xlsm") and not p.name.startswith("~$"))
    if not inputs:
        raise ValueError("no account workbooks found")
    current: list[dict] = []
    errors = []
    for path in inputs:
        try:
            current.extend(sync.read_workbook(path, runtime_dir=records_dir / ".运行缓存"))
        except Exception as exc:
            errors.append(f"{path.name}: {exc}")
    sync.cleanup_runtime_dir(records_dir / ".运行缓存")
    if errors:
        raise ValueError("; ".join(errors))
    grouped: dict[tuple[str, str], list[dict]] = {}
    for record in current:
        grouped.setdefault((record["account"], record["clean_title"]), []).append(record)
    selected, excluded = [], []
    for records in grouped.values():
        highest = max(record["likes"] for record in records)
        selected.extend(record for record in records if record["likes"] == highest)
        excluded.extend(record for record in records if record["likes"] != highest)
    return sorted(selected, key=lambda record: (record["account"], record["source_file"], record["row"])), excluded


def key(record: dict) -> str:
    return record.get("review_key") or hashlib.sha256(json.dumps([record["account"], record["clean_title"]], ensure_ascii=False).encode()).hexdigest()[:24]


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def validate_decisions(record: dict, decisions: object) -> list[dict]:
    if not isinstance(decisions, list):
        raise ValueError("each batch review value must be an array")
    result = []
    for item in decisions:
        if not isinstance(item, dict):
            raise ValueError("review decision must be an object")
        root = str(item.get("root", "")).strip()
        evidence = item.get("evidence")
        element = item.get("element")
        status = item.get("status", item.get("reviewer_verdict", "approved"))
        if status not in ("approved", "rejected", "uncertain", "pending", "reclassify"):
            raise ValueError(f"unknown review status: {status}")
        if status in ("uncertain", "pending", "reclassify"):
            result.append(item)
            continue
        if not isinstance(evidence, list) or not evidence or any(not str(piece).strip() for piece in evidence):
            raise ValueError(f"evidence must be a non-empty array: {record['clean_title']} / {root}")
        if any(str(piece) not in record["clean_title"] for piece in evidence):
            raise ValueError(f"evidence is not present in title: {record['clean_title']} / {evidence}")
        if element not in sync.ELEMENTS:
            raise ValueError(f"unsupported element: {element}")
        for field in ("derivation", "rationale", "auditor", "audit_reason"):
            if not str(item.get(field, "")).strip():
                raise ValueError(f"missing {field} for {record['clean_title']} / {root}")
        checks = item.get("audit_checks")
        names = ("root_faithful", "evidence_exact", "element_valid", "reason_supported")
        if not isinstance(checks, dict) or any(not isinstance(checks.get(name), bool) for name in names):
            raise ValueError(f"independent audit checks must be four booleans: {record['clean_title']} / {root}")
        if status == "approved" and not all(checks[name] for name in names):
            raise ValueError(f"approved decision requires four positive audit checks: {record['clean_title']} / {root}")
        if element == "最差" and status == "approved":
            sync.validate_worst_decision(record["clean_title"], item)
        result.append(item)
    return result


def validate_analysis(record: dict, analysis: object, decisions: list[dict]) -> dict:
    if not isinstance(analysis, dict):
        raise ValueError(f"each title needs an analysis object: {record['clean_title']}")
    for field in ("semantic_summary", "candidate_summary"):
        if not str(analysis.get(field, "")).strip():
            raise ValueError(f"missing analysis.{field}: {record['clean_title']}")
    checks = analysis.get("element_checks")
    if not isinstance(checks, list) or len(checks) != len(sync.ELEMENTS):
        raise ValueError(f"element_checks must contain all eight elements: {record['clean_title']}")
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or check.get("element") not in sync.ELEMENTS or check.get("element") in seen:
            raise ValueError(f"element_checks must contain each supported element exactly once: {record['clean_title']}")
        if not isinstance(check.get("applicable"), bool) or not str(check.get("reason", "")).strip():
            raise ValueError(f"each element check needs applicable and reason: {record['clean_title']}")
        seen.add(check["element"])
    if seen != set(sync.ELEMENTS):
        raise ValueError(f"element_checks is incomplete: {record['clean_title']}")
    for item in decisions:
        element = item.get("element")
        if item.get("status", item.get("reviewer_verdict", "approved")) == "approved":
            matching = next(check for check in checks if check["element"] == element)
            if not matching["applicable"]:
                raise ValueError(f"approved root uses an element marked not applicable: {record['clean_title']} / {item.get('root')}")
    return analysis


def committed_reviews_for_accounts(state: dict, ws: Path, accounts: set[str]) -> dict:
    """Merge only committed batch reviews belonging to completed accounts."""
    merged: dict[str, dict] = {}
    for number in sorted(state.get("batches", {}), key=lambda value: int(value)):
        batch = state["batches"][number]
        if batch.get("status") != "committed":
            continue
        items = batch.get("items", [])
        if not items or items[0].get("account") not in accounts:
            continue
        review_file = batch.get("review_file")
        if not review_file:
            raise ValueError(f"committed batch {number} has no review file")
        path = inside(ws / review_file, ws)
        data = load_json(path, None)
        if not isinstance(data, dict) or not isinstance(data.get("reviews"), dict):
            raise ValueError(f"committed batch review is invalid: {path}")
        merged.update(data["reviews"])
    expected = {
        item["review_key"]
        for batch in state.get("batches", {}).values()
        if batch.get("status") == "committed"
        and batch.get("items")
        and batch["items"][0].get("account") in accounts
        for item in batch["items"]
    }
    if set(merged) != expected:
        raise ValueError(f"committed review set is incomplete: expected={len(expected)} got={len(merged)}")
    overrides = state.get("worst_recheck_overrides", {})
    if overrides:
        if not isinstance(overrides, dict):
            raise ValueError("worst_recheck_overrides must be a mapping")
        for review_key, replacement in overrides.items():
            if review_key not in merged:
                continue
            if not isinstance(replacement, list):
                raise ValueError(f"worst recheck override must be a list: {review_key}")
            original = merged[review_key].get("decisions", [])
            if not isinstance(original, list):
                raise ValueError(f"committed decisions are invalid: {review_key}")
            # Strict migration cards are authoritative for the historical
            # 最差 relations of this title. Do not match roots by string:
            # legacy batches may contain a slightly different derived root.
            if state.get("strict_worst_recheck"):
                non_worst = [item for item in original if item.get("element") != "最差"]
                corrected = []
                for item in replacement:
                    item = dict(item)
                    item.pop("recheck_of", None)
                    corrected.append(item)
                merged[review_key] = {**merged[review_key], "decisions": non_worst + corrected}
                continue
            by_original = {str(item.get("recheck_of", "")): item for item in replacement if isinstance(item, dict)}
            decisions = []
            for item in original:
                if item.get("element") == "最差" and item.get("root") in by_original:
                    corrected = dict(by_original[item["root"]])
                    corrected.pop("recheck_of", None)
                    decisions.append(corrected)
                else:
                    decisions.append(item)
            merged[review_key] = {**merged[review_key], "decisions": decisions}
    return merged


def build_worst_recheck_queue(state: dict, ws: Path, selected: list[dict]) -> dict:
    """Build a per-account queue from approved historical 最差 relations."""
    selected_by_key = {key(record): record for record in selected}
    account_by_key = {item["review_key"]: item["account"] for item in load_json(inside(ws / DEFAULT_QUEUE, ws), {}).get("selected", [])}
    grouped: dict[str, dict[str, dict]] = {}
    for number in sorted(state.get("batches", {}), key=lambda value: int(value)):
        batch = state["batches"][number]
        if batch.get("status") != "committed":
            continue
        review_file = batch.get("review_file")
        if not review_file:
            continue
        data = load_json(inside(ws / review_file, ws), {})
        for review_key, entry in data.get("reviews", {}).items():
            roots = []
            for decision in entry.get("decisions", []):
                if decision.get("element") == "最差" and decision.get("status", decision.get("reviewer_verdict", "approved")) == "approved":
                    roots.append(dict(decision))
            if not roots:
                continue
            account = account_by_key.get(review_key) or selected_by_key.get(review_key, {}).get("account")
            if not account:
                raise ValueError(f"cannot map worst recheck title to account: {review_key}")
            grouped.setdefault(account, {})[review_key] = {
                "review_key": review_key,
                "account": account,
                "title": entry.get("title", selected_by_key.get(review_key, {}).get("clean_title", "")),
                "source_id": selected_by_key.get(review_key, {}).get("source_id", ""),
                "original_batch": int(number),
                "original_decisions": roots,
            }
    batches = {}
    batch_number = 1
    for account in sorted(grouped):
        items = list(grouped[account].values())
        for offset in range(0, len(items), 10):
            batches[str(batch_number)] = items[offset:offset + 10]
            batch_number += 1
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "selected_titles": sum(len(v) for v in grouped.values()), "selected_relations": sum(len(item["original_decisions"]) for v in grouped.values() for item in v.values()), "batches": batches}


def recheck_status(state: dict, ws: Path) -> dict:
    status = load_json(inside(ws / WORST_STATE, ws), {})
    if status.get("workflow_status") == "active":
        return status
    return {}


def require_no_worst_recheck(ws: Path, state: dict) -> None:
    if state.get("workflow_status") in ("worst_recheck", "strict_worst_recheck"):
        raise ValueError("最差复查尚未完成；当前普通拆解队列已锁定")


def build_strict_worst_recheck_queue(state: dict, ws: Path, selected: list[dict]) -> dict:
    selected_by_key = {key(record): record for record in selected}
    source_queue = load_json(inside(ws / DEFAULT_QUEUE, ws), {})
    account_by_key = {item["review_key"]: item["account"] for item in source_queue.get("selected", [])}
    snapshot = load_json(inside(ws / "98_处理记录/source-snapshot.json", ws), {})
    grouped: dict[str, dict[str, dict]] = {}
    for review_key, entry in snapshot.get("audit_records", {}).items():
        roots = [dict(d) for d in entry.get("decisions", []) if d.get("element") == "最差" and d.get("status", d.get("reviewer_verdict", "approved")) == "approved"]
        if not roots:
            continue
        account = entry.get("account") or account_by_key.get(review_key) or selected_by_key.get(review_key, {}).get("account")
        if not account:
            raise ValueError(f"cannot map strict worst title to account: {review_key}")
        grouped.setdefault(account, {})[review_key] = {
            "review_key": review_key,
            "account": account,
            "title": entry.get("title", selected_by_key.get(review_key, {}).get("clean_title", "")),
            "source_id": selected_by_key.get(review_key, {}).get("source_id", ""),
            "original_decisions": roots,
        }
    batches = {}
    number = 1
    for account in sorted(grouped):
        items = list(grouped[account].values())
        for offset in range(0, len(items), 10):
            batches[str(number)] = items[offset:offset + 10]
            number += 1
    return {"generated_at": datetime.now().isoformat(timespec="seconds"), "selected_titles": sum(len(v) for v in grouped.values()), "selected_relations": sum(len(x["original_decisions"]) for v in grouped.values() for x in v.values()), "batches": batches}


def prepare_strict_worst_recheck(ws: Path, state: dict, source: Path, records_dir: Path) -> dict:
    if state.get("workflow_status") in ("worst_recheck", "strict_worst_recheck"):
        raise ValueError("已有最差复查流程进行中")
    selected, _ = collect_selected(source, records_dir)
    queue = build_strict_worst_recheck_queue(state, ws, selected)
    if not queue["batches"]:
        raise ValueError("没有找到正式最差关系")
    inside(ws / STRICT_WORST_QUEUE, ws).write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    first = next(iter(queue["batches"]))
    state["workflow_status"] = "strict_worst_recheck"
    state["strict_worst_recheck"] = {"active_batch": int(first), "active_account": queue["batches"][first][0]["account"], "completed_batches": [], "total_batches": len(queue["batches"]), "selected_titles": queue["selected_titles"], "selected_relations": queue["selected_relations"], "status": "active"}
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inside(ws / STRICT_WORST_STATE, ws).write_text(json.dumps(state["strict_worst_recheck"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return queue


def prepare_incremental(ws: Path, state: dict, source: Path, records_dir: Path) -> dict:
    """Append only currently selected titles without committed batch reviews."""
    if state.get("workflow_status") not in ("complete", "active"):
        raise ValueError(f"无法建立增量队列：workflow_status={state.get('workflow_status')}")
    selected, excluded = collect_selected(source, records_dir)
    committed_keys = {
        item["review_key"]
        for batch in state.get("batches", {}).values()
        if batch.get("status") == "committed"
        for item in batch.get("items", [])
    }
    pending = [item for item in selected if key(item) not in committed_keys]
    if not pending:
        raise ValueError("没有发现新的未审核选题")
    grouped = {}
    for item in pending:
        grouped.setdefault(item["account"], []).append({"review_key": key(item), "account": item["account"], "title": item["clean_title"], "source_id": item["source_id"]})
    next_number = max((int(n) for n in state.get("batches", {})), default=0) + 1
    new_batches = {}
    for account in sorted(grouped):
        items = grouped[account]
        for offset in range(0, len(items), 10):
            number = next_number
            chunk = items[offset:offset + 10]
            new_batches[str(number)] = {"items": chunk, "status": "pending", "review_file": None, "committed_at": None}
            next_number += 1
    state.setdefault("batches", {}).update(new_batches)
    first = min(int(n) for n in new_batches)
    state["workflow_status"] = "active"
    state["active_batch"] = first
    state["active_account"] = new_batches[str(first)]["items"][0]["account"]
    state["source_records"] = len(selected)
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"pending_titles": len(pending), "excluded_duplicates": len(excluded), "new_batches": len(new_batches), "active_batch": first, "active_account": state["active_account"], "accounts": {account: len(items) for account, items in grouped.items()}}


def commit_strict_worst_recheck(ws: Path, state: dict, reviews_path: Path) -> dict:
    queue = load_json(inside(ws / STRICT_WORST_QUEUE, ws), {})
    meta = state.get("strict_worst_recheck", {})
    active = meta.get("active_batch")
    if state.get("workflow_status") != "strict_worst_recheck" or active is None:
        raise ValueError("当前没有解锁的严格最差复核批次")
    batch = queue.get("batches", {}).get(str(active))
    reviews = load_json(inside(reviews_path, ws), None)
    expected = {item["review_key"] for item in batch or []}
    if not isinstance(reviews, dict) or set(reviews) != expected:
        raise ValueError("严格最差复核批次必须提交恰好对应当前批次的全部选题")
    replacements = {}
    for record in batch:
        entry = reviews[record["review_key"]]
        decisions = entry.get("decisions") if isinstance(entry, dict) else None
        if not isinstance(decisions, list):
            raise ValueError(f"严格最差复核缺少 decisions: {record['review_key']}")
        original = {str(d.get("root", "")) for d in record["original_decisions"]}
        seen = set()
        for item in decisions:
            if not isinstance(item, dict) or item.get("element") != "最差":
                raise ValueError("严格最差复核只能提交最差关系")
            origin = str(item.get("recheck_of", "")).strip()
            if not origin or origin not in original or origin in seen:
                raise ValueError(f"严格最差复核的 recheck_of 无效: {origin}")
            seen.add(origin)
            if item.get("status", item.get("reviewer_verdict", "approved")) == "approved":
                item["worst_basis"] = "极端体验"
                sync.validate_worst_decision(record["title"], item)
        if seen != original:
            raise ValueError(f"严格最差复核必须覆盖原有全部关系: {record['review_key']}")
        replacements[record["review_key"]] = decisions
    out_dir = inside(ws / STRICT_WORST_DIR, ws)
    out_dir.mkdir(parents=True, exist_ok=True)
    inside(out_dir / f"批次_{int(active):04d}.json", ws).write_text(json.dumps({"batch": int(active), "committed_at": datetime.now().isoformat(timespec="seconds"), "reviews": replacements}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    completed = sorted(set(meta.get("completed_batches", [])) | {int(active)})
    next_batch = next((int(n) for n in queue.get("batches", {}) if int(n) not in completed), None)
    meta.update({"completed_batches": completed, "active_batch": next_batch, "active_account": queue["batches"][str(next_batch)][0]["account"] if next_batch else None, "status": "active" if next_batch else "awaiting_finalize"})
    state["strict_worst_recheck"] = meta
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inside(ws / STRICT_WORST_STATE, ws).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"batch": active, "titles": len(batch), "next_batch": next_batch, "status": meta["status"]}


def generate_strict_worst_decisions(ws: Path, state: dict) -> dict:
    """Create the auditable two-way migration cards without semantic expansion.

    This migration intentionally inspects only the historical worst_trigger. A
    relation is approved only when that exact historical trigger is still in
    the formal whitelist; all other historical relations are rejected.
    """
    if state.get("workflow_status") != "strict_worst_recheck":
        raise ValueError("请先运行 prepare-strict-worst-recheck")
    queue = load_json(inside(ws / STRICT_WORST_QUEUE, ws), {})
    out_dir = inside(ws / STRICT_WORST_DIR, ws)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated = []
    for number, batch in sorted(queue.get("batches", {}).items(), key=lambda pair: int(pair[0])):
        reviews = {}
        for record in batch:
            decisions = []
            for original in record["original_decisions"]:
                trigger = str(original.get("worst_trigger", "")).strip()
                approved = trigger in sync.WORST_TRIGGER_WHITELIST and trigger in record["title"]
                decision = {
                    "recheck_of": original.get("root", ""),
                    "root": original.get("root", ""),
                    "element": "最差",
                    "status": "approved" if approved else "rejected",
                    "derivation": "仅按历史 worst_trigger 与严格白名单逐字核对，不新增或改写语义。",
                    "rationale": "标题直接包含严格白名单极端词。" if approved else "标题没有严格白名单极端词，排除。",
                    "evidence": list(original.get("evidence", [])),
                    "auditor": "严格白名单复核程序",
                    "audit_checks": {
                        "root_faithful": approved,
                        "evidence_exact": all(str(fragment) in record["title"] for fragment in original.get("evidence", [])),
                        "element_valid": approved,
                        "reason_supported": approved,
                    },
                    "audit_reason": "worst_trigger 命中严格白名单并逐字出现在标题中。" if approved else "worst_trigger 未命中严格白名单，不进入正式结果。",
                }
                if approved:
                    decision["worst_basis"] = "极端体验"
                    decision["worst_trigger"] = trigger
                    decision["evidence"] = list(dict.fromkeys([*decision["evidence"], trigger]))
                decisions.append(decision)
            reviews[record["review_key"]] = {"decisions": decisions}
        path = inside(out_dir / f"批次_{int(number):04d}审核.json", ws)
        path.write_text(json.dumps(reviews, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        generated.append(path.relative_to(ws).as_posix())
    return {"batches": len(generated), "files": generated}


def finalize_strict_worst_recheck(ws: Path, state: dict, records_dir: Path) -> dict:
    queue = load_json(inside(ws / STRICT_WORST_QUEUE, ws), {})
    meta = state.get("strict_worst_recheck", {})
    if state.get("workflow_status") != "strict_worst_recheck" or meta.get("status") != "awaiting_finalize":
        raise ValueError("严格最差复核尚未完成全部批次")
    overrides = {}
    for number in sorted(queue.get("batches", {}), key=lambda value: int(value)):
        data = load_json(inside(ws / STRICT_WORST_DIR / f"批次_{int(number):04d}.json", ws), None)
        if not isinstance(data, dict):
            raise ValueError(f"严格最差复核批次文件缺失: {number}")
        overrides.update(data.get("reviews", {}))
    # Rebuild-all reads the committed batch view, which can contain historical
    # worst relations no longer present in the current formal snapshot. Keep
    # those relations out of the new formal result instead of allowing them to
    # reappear during the rebuild.
    committed = committed_reviews_for_accounts(state, ws, set(state.get("completed_accounts", [])))
    for review_key, entry in committed.items():
        if review_key in overrides:
            continue
        legacy = []
        for item in entry.get("decisions", []):
            if item.get("element") != "最差":
                continue
            legacy.append({
                "recheck_of": item.get("root", ""),
                "root": item.get("root", ""),
                "element": "最差",
                "status": "rejected",
                "derivation": "该历史关系不在本次正式快照的严格复核范围内，不重新纳入正式结果。",
                "rationale": "不进入严格白名单复核后的正式结果。",
                "evidence": list(item.get("evidence", [])) or [str(item.get("root", ""))],
                "auditor": "严格白名单复核程序",
                "audit_checks": {"root_faithful": False, "evidence_exact": True, "element_valid": False, "reason_supported": False},
                "audit_reason": "历史批次关系未登记在当前正式快照，按严格迁移规则排除。",
            })
        if legacy:
            overrides[review_key] = legacy
    original_state = inside(ws / DEFAULT_STATE, ws).read_bytes()
    state["worst_recheck_overrides"] = overrides
    state["strict_worst_recheck"]["status"] = "syncing"
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        result = sync_completed_accounts(ws, records_dir, state, list(state.get("completed_accounts", [])), rebuild_all=True)
    except Exception:
        inside(ws / DEFAULT_STATE, ws).write_bytes(original_state)
        raise
    state["workflow_status"] = "active"
    state["strict_worst_recheck"]["status"] = "complete"
    state["strict_worst_recheck"]["active_batch"] = None
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inside(ws / STRICT_WORST_STATE, ws).write_text(json.dumps(state["strict_worst_recheck"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def prepare_worst_recheck(ws: Path, state: dict, source: Path, records_dir: Path) -> dict:
    if state.get("workflow_status") == "worst_recheck":
        raise ValueError("最差复查队列已经存在；请使用 current-worst 查看")
    selected, _ = collect_selected(source, records_dir)
    queue = build_worst_recheck_queue(state, ws, selected)
    if not queue["batches"]:
        raise ValueError("没有找到可复查的已通过最差关系")
    queue_path = inside(ws / WORST_QUEUE, ws)
    state_path = inside(ws / DEFAULT_STATE, ws)
    queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    first = next(iter(queue["batches"]))
    state["workflow_status"] = "worst_recheck"
    state["worst_recheck"] = {"active_batch": int(first), "active_account": queue["batches"][first][0]["account"], "completed_batches": [], "total_batches": len(queue["batches"]), "selected_titles": queue["selected_titles"], "selected_relations": queue["selected_relations"]}
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    status_path = inside(ws / WORST_STATE, ws)
    status_path.write_text(json.dumps(state["worst_recheck"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return queue


def commit_worst_recheck(ws: Path, state: dict, reviews_path: Path) -> dict:
    queue = load_json(inside(ws / WORST_QUEUE, ws), {})
    meta = state.get("worst_recheck", {})
    active = meta.get("active_batch")
    if state.get("workflow_status") != "worst_recheck" or active is None:
        raise ValueError("当前没有解锁的最差复查批次")
    batch = queue.get("batches", {}).get(str(active))
    if not isinstance(batch, list):
        raise ValueError(f"最差复查批次不存在: {active}")
    reviews = load_json(inside(reviews_path, ws), None)
    if not isinstance(reviews, dict) or set(reviews) != {item["review_key"] for item in batch}:
        raise ValueError("最差复查批次必须提交恰好对应当前批次的全部选题")
    replacements = {}
    for item in batch:
        review_key = item["review_key"]
        entry = reviews[review_key]
        decisions = entry.get("decisions") if isinstance(entry, dict) else None
        if not isinstance(decisions, list):
            raise ValueError(f"最差复查缺少 decisions: {review_key}")
        original = {str(d.get("root", "")) for d in item["original_decisions"]}
        seen = set()
        for decision in decisions:
            if not isinstance(decision, dict) or decision.get("element") != "最差":
                raise ValueError(f"最差复查只能提交最差关系: {review_key}")
            origin = str(decision.get("recheck_of", "")).strip()
            if not origin or origin not in original or origin in seen:
                raise ValueError(f"最差复查的 recheck_of 与原关系不一致: {review_key} / {origin}")
            seen.add(origin)
        if seen != original:
            raise ValueError(f"最差复查必须覆盖原有全部关系: {review_key}")
        record = {"clean_title": item["title"]}
        validate_decisions(record, decisions)
        unresolved = [d for d in decisions if d.get("status", d.get("reviewer_verdict", "approved")) in ("uncertain", "pending", "reclassify") and not d.get("user_decision")]
        if unresolved:
            raise ValueError(f"最差复查存在未决关系: {review_key}")
        replacements[review_key] = decisions
    out_dir = inside(ws / WORST_DIR, ws)
    out_dir.mkdir(parents=True, exist_ok=True)
    destination = inside(out_dir / f"批次_{int(active):04d}.json", ws)
    destination.write_text(json.dumps({"batch": int(active), "committed_at": datetime.now().isoformat(timespec="seconds"), "reviews": replacements}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    completed = list(meta.get("completed_batches", []))
    if int(active) not in completed:
        completed.append(int(active))
    next_batch = None
    for number, entries in queue.get("batches", {}).items():
        if int(number) not in completed:
            next_batch = int(number)
            break
    meta["completed_batches"] = sorted(completed)
    meta["active_batch"] = next_batch
    if next_batch is None:
        meta["active_account"] = None
        meta["status"] = "awaiting_finalize"
    else:
        meta["active_account"] = queue["batches"][str(next_batch)][0]["account"]
        meta["status"] = "active"
    state["worst_recheck"] = meta
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inside(ws / WORST_STATE, ws).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"batch": active, "titles": len(batch), "next_batch": next_batch, "status": meta["status"]}


def finalize_worst_recheck(ws: Path, state: dict, records_dir: Path) -> dict:
    queue = load_json(inside(ws / WORST_QUEUE, ws), {})
    meta = state.get("worst_recheck", {})
    if state.get("workflow_status") != "worst_recheck" or meta.get("status") != "awaiting_finalize":
        raise ValueError("最差复查尚未完成全部批次")
    overrides = {}
    for number in sorted(queue.get("batches", {}), key=lambda value: int(value)):
        path = inside(ws / WORST_DIR / f"批次_{int(number):04d}.json", ws)
        data = load_json(path, None)
        if not isinstance(data, dict):
            raise ValueError(f"最差复查批次文件缺失: {path}")
        overrides.update(data.get("reviews", {}))
    original_state = inside(ws / DEFAULT_STATE, ws).read_bytes()
    state["worst_recheck_overrides"] = overrides
    state["worst_recheck"]["status"] = "syncing"
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        completed_accounts = list(state.get("completed_accounts", []))
        if completed_accounts:
            result = sync_completed_accounts(ws, records_dir, state, completed_accounts, rebuild_all=True)
        else:
            result = {"accounts": [], "output": "no completed accounts"}
    except Exception:
        inside(ws / DEFAULT_STATE, ws).write_bytes(original_state)
        raise
    state["workflow_status"] = "active"
    state["worst_recheck"]["status"] = "complete"
    state["worst_recheck"]["active_batch"] = None
    inside(ws / DEFAULT_STATE, ws).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    inside(ws / WORST_STATE, ws).write_text(json.dumps(state["worst_recheck"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def sync_completed_accounts(ws: Path, records_dir: Path, state: dict, accounts: list[str], rebuild_all: bool = False) -> dict:
    """Synchronize cumulative formal outputs for the supplied completed accounts."""
    account_set = set(accounts)
    if not account_set:
        raise ValueError("at least one completed account is required for account sync")
    reviews = committed_reviews_for_accounts(state, ws, account_set)
    runtime_dir = inside(records_dir / ".运行缓存", records_dir)
    runtime_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="account-sync-", suffix=".json", dir=str(runtime_dir))
    review_path = Path(name)
    try:
        with open(fd, "w", encoding="utf-8", closefd=True) as handle:
            json.dump(reviews, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        command = [
            sys.executable,
            str(Path(__file__).with_name("sync_viral_roots.py")),
            "--workspace", str(ws),
            "--reviews", str(review_path),
            "--accounts", *sorted(account_set),
        ]
        if rebuild_all:
            command.append("--rebuild-all")
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode:
            detail = (completed.stdout + "\n" + completed.stderr).strip()
            raise RuntimeError(f"account formal sync failed (exit {completed.returncode}): {detail}")
        return {"accounts": sorted(account_set), "output": completed.stdout.strip()}
    finally:
        review_path.unlink(missing_ok=True)
        try:
            if runtime_dir.is_dir() and not any(runtime_dir.iterdir()):
                runtime_dir.rmdir()
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ten-title viral-root review batches")
    parser.add_argument("command", choices=("prepare", "prepare-incremental", "current", "commit", "confirm-account", "sync-account", "status", "finalize", "prepare-worst-recheck", "current-worst", "commit-worst-recheck", "finalize-worst-recheck", "prepare-strict-worst-recheck", "generate-strict-worst-decisions", "current-strict-worst", "commit-strict-worst-recheck", "finalize-strict-worst-recheck"))
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--new-run", action="store_true", help="reset prior batch statuses and start a new semantic review run")
    parser.add_argument("--first-account", help="place this account first in the serial review queue")
    parser.add_argument("--batch", type=int)
    parser.add_argument("--account")
    parser.add_argument("--sync-account", action="store_true", help="账号确认前先同步累计正式产物")
    parser.add_argument("--reviews")
    args = parser.parse_args()
    if args.batch_size != 10:
        raise ValueError("the production review contract requires exactly 10 titles per batch")
    ws = Path(args.workspace).resolve()
    source, records_dir = workspace_paths(ws)
    state_path = inside(ws / DEFAULT_STATE, ws)
    queue_path = inside(ws / DEFAULT_QUEUE, ws)
    state = load_json(state_path, {"schema_version": 1, "batch_size": 10, "batches": {}, "created_at": None})

    if args.command == "prepare-worst-recheck":
        queue = prepare_worst_recheck(ws, state, source, records_dir)
        print(json.dumps({"status": "worst_recheck_prepared", "selected_titles": queue["selected_titles"], "selected_relations": queue["selected_relations"], "batches": len(queue["batches"]), "active_batch": state["worst_recheck"]["active_batch"], "active_account": state["worst_recheck"]["active_account"]}, ensure_ascii=False))
        return 0

    if args.command == "current-worst":
        if state.get("workflow_status") != "worst_recheck":
            raise ValueError("当前没有进行中的最差复查")
        meta = state.get("worst_recheck", {})
        active = meta.get("active_batch")
        if active is None:
            raise ValueError("最差复查批次已全部提交，请运行 finalize-worst-recheck")
        queue = load_json(inside(ws / WORST_QUEUE, ws), {})
        print(json.dumps({"batch": active, "account": meta.get("active_account"), "items": queue.get("batches", {}).get(str(active), [])}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "commit-worst-recheck":
        if not args.reviews:
            raise ValueError("--reviews is required for worst recheck commit")
        result = commit_worst_recheck(ws, state, inside(Path(args.reviews), ws))
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "finalize-worst-recheck":
        result = finalize_worst_recheck(ws, state, records_dir)
        print(json.dumps({"status": "worst_recheck_synced", **result}, ensure_ascii=False))
        return 0

    if args.command == "prepare-strict-worst-recheck":
        queue = prepare_strict_worst_recheck(ws, state, source, records_dir)
        print(json.dumps({"status": "strict_worst_recheck_prepared", "selected_titles": queue["selected_titles"], "selected_relations": queue["selected_relations"], "batches": len(queue["batches"]), "active_batch": state["strict_worst_recheck"]["active_batch"], "active_account": state["strict_worst_recheck"]["active_account"]}, ensure_ascii=False))
        return 0

    if args.command == "generate-strict-worst-decisions":
        result = generate_strict_worst_decisions(ws, state)
        print(json.dumps({"status": "strict_worst_decisions_generated", **result}, ensure_ascii=False))
        return 0

    if args.command == "current-strict-worst":
        if state.get("workflow_status") != "strict_worst_recheck":
            raise ValueError("当前没有进行中的严格最差复核")
        meta = state.get("strict_worst_recheck", {})
        active = meta.get("active_batch")
        if active is None:
            raise ValueError("严格最差复核批次已全部提交，请运行 finalize-strict-worst-recheck")
        queue = load_json(inside(ws / STRICT_WORST_QUEUE, ws), {})
        print(json.dumps({"batch": active, "account": meta.get("active_account"), "items": queue.get("batches", {}).get(str(active), [])}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "commit-strict-worst-recheck":
        if not args.reviews:
            raise ValueError("--reviews is required for strict worst recheck commit")
        result = commit_strict_worst_recheck(ws, state, inside(Path(args.reviews), ws))
        print(json.dumps(result, ensure_ascii=False))
        return 0

    if args.command == "finalize-strict-worst-recheck":
        result = finalize_strict_worst_recheck(ws, state, records_dir)
        print(json.dumps({"status": "strict_worst_recheck_synced", **result}, ensure_ascii=False))
        return 0

    if args.command == "prepare":
        selected, excluded = collect_selected(source, records_dir)
        if args.first_account:
            account_groups = {}
            account_order = []
            for record in selected:
                account = record["account"]
                if account not in account_groups:
                    account_groups[account] = []
                    account_order.append(account)
                account_groups[account].append(record)
            if args.first_account not in account_groups:
                raise ValueError(f"--first-account was not found in selected source records: {args.first_account}")
            ordered_accounts = [args.first_account] + [account for account in account_order if account != args.first_account]
            selected = [record for account in ordered_accounts for record in account_groups[account]]
        queue = []
        for record in selected:
            queue.append({"review_key": key(record), "account": record["account"], "title": record["clean_title"], "source_id": record["source_id"]})
        batches = {}
        batch_index = 1
        cursor = 0
        while cursor < len(queue):
            account = queue[cursor]["account"]
            account_items = []
            while cursor < len(queue) and queue[cursor]["account"] == account:
                account_items.append(queue[cursor])
                cursor += 1
            for offset in range(0, len(account_items), 10):
                batches[str(batch_index)] = account_items[offset:offset + 10]
                batch_index += 1
        old_batches = {} if args.new_run else state.get("batches", {})
        first_batch = next(iter(batches), None)
        first_account = batches[first_batch][0]["account"] if first_batch else None
        state = {"schema_version": 3, "batch_size": 10, "created_at": datetime.now().isoformat(timespec="seconds"), "source_records": len(queue), "excluded_duplicates": len(excluded), "batches": {}, "completed_accounts": [], "active_batch": int(first_batch) if first_batch else None, "active_account": first_account, "workflow_status": "active" if first_batch else "complete"}
        for index, items in enumerate(batches.values(), 1):
            old = old_batches.get(str(index), {})
            same_items = [entry.get("review_key") for entry in old.get("items", [])] == [entry.get("review_key") for entry in items]
            state["batches"][str(index)] = {"items": items, "status": old.get("status", "pending") if same_items else "pending", "review_file": old.get("review_file") if same_items else None, "committed_at": old.get("committed_at") if same_items else None}
        queue_path.write_text(json.dumps({"generated_at": datetime.now().isoformat(timespec="seconds"), "selected": queue, "batches": batches}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"selected_records": len(queue), "excluded_duplicates": len(excluded), "batches": len(batches), "batch_size": 10}, ensure_ascii=False))
        return 0

    if not state_path.exists():
        raise ValueError("run prepare before this command")
    batches = state.get("batches", {})
    require_no_worst_recheck(ws, state)
    if args.command == "status":
        counts = {status: sum(item.get("status") == status for item in batches.values()) for status in ("pending", "committed")}
        print(json.dumps({"source_records": state.get("source_records", 0), "batches": len(batches), "counts": counts, "workflow_status": state.get("workflow_status", "legacy"), "active_batch": state.get("active_batch"), "active_account": state.get("active_account")}, ensure_ascii=False))
        return 0

    if args.command == "prepare-incremental":
        result = prepare_incremental(ws, state, source, records_dir)
        print(json.dumps({"status": "incremental_prepared", **result}, ensure_ascii=False))
        return 0

    if args.command == "current":
        active = state.get("active_batch")
        if state.get("workflow_status") != "active" or active is None:
            raise ValueError(f"no batch is currently unlocked; workflow_status={state.get('workflow_status')}")
        print(json.dumps({"batch": active, "account": state.get("active_account"), "items": batches[str(active)]["items"]}, ensure_ascii=False, indent=2))
        return 0

    if args.command in ("confirm-account", "sync-account"):
        # Recover the legacy final-batch state where the queue was marked
        # complete before the last account-level sync/confirmation.
        if state.get("workflow_status") == "complete" and args.account:
            account_batches = [item for item in batches.values() if item.get("items") and item["items"][0].get("account") == args.account]
            if account_batches and all(item.get("status") == "committed" for item in account_batches) and args.account not in state.get("completed_accounts", []):
                state["workflow_status"] = "awaiting_account_confirmation"
                state["active_batch"] = None
                state["active_account"] = args.account
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if state.get("workflow_status") != "awaiting_account_confirmation":
            raise ValueError(f"account confirmation is not currently required; workflow_status={state.get('workflow_status')}")
        if not args.account or args.account != state.get("active_account"):
            raise ValueError(f"--account must confirm the completed active account: {state.get('active_account')}")
        if args.command == "confirm-account" and not args.sync_account:
            raise ValueError("account boundary requires --sync-account so formal outputs are committed before advancing")
        completed_accounts = list(state.get("completed_accounts", []))
        if args.command == "sync-account" or args.account not in completed_accounts:
            sync_result = sync_completed_accounts(ws, records_dir, state, completed_accounts + [args.account])
            if args.account not in completed_accounts:
                completed_accounts.append(args.account)
            state["completed_accounts"] = completed_accounts
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            sync_result = {"accounts": completed_accounts, "output": "already synced"}
        if args.command == "sync-account":
            print(json.dumps({"status": "account_synced", **sync_result}, ensure_ascii=False))
            return 0
        next_batch = None
        for number, item in batches.items():
            if item.get("status") == "pending":
                next_batch = int(number)
                break
        if next_batch is None:
            state["workflow_status"] = "complete"
            state["active_batch"] = None
            state["active_account"] = None
        else:
            state["active_batch"] = next_batch
            state["active_account"] = batches[str(next_batch)]["items"][0]["account"]
            state["workflow_status"] = "active"
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": state["workflow_status"], "active_batch": state.get("active_batch"), "active_account": state.get("active_account"), "synced_accounts": state.get("completed_accounts", [])}, ensure_ascii=False))
        return 0

    if args.command == "commit":
        if state.get("workflow_status") != "active":
            raise ValueError(f"cannot commit while workflow_status={state.get('workflow_status')}")
        if args.batch is None or str(args.batch) not in batches:
            raise ValueError("--batch must identify an existing batch")
        if int(args.batch) != int(state.get("active_batch")):
            raise ValueError(f"only the currently unlocked batch {state.get('active_batch')} may be committed")
        batch = batches[str(args.batch)]
        if not args.reviews:
            raise ValueError("--reviews is required for commit")
        review_path = inside(Path(args.reviews), ws)
        reviews = load_json(review_path, None)
        if not isinstance(reviews, dict):
            raise ValueError("batch review file must be a JSON object")
        expected = {item["review_key"] for item in batch["items"]}
        if set(reviews) != expected:
            raise ValueError(f"batch must contain exactly its 10-title review keys; expected={len(expected)} got={len(reviews)}")
        by_key = {item["review_key"]: item for item in batch["items"]}
        # The queue was built from the selected source snapshot and the batch
        # is the only unlocked unit.  Re-reading every legacy workbook here
        # makes each commit contend with Excel COM and can leave multiple
        # readers hanging.  Validate against the immutable current-batch
        # records instead; source changes are detected by the next preflight
        # or incremental preparation before another batch is unlocked.
        current = {
            item["review_key"]: {"clean_title": item["title"]}
            for item in batch["items"]
        }
        committed = {}
        for review_key, entry in reviews.items():
            if review_key not in current:
                raise ValueError(f"review key is no longer selected: {review_key}")
            if isinstance(entry, dict) and not isinstance(entry.get("decisions"), list) and isinstance(entry.get("analysis"), dict) and isinstance(entry["analysis"].get("decisions"), list):
                # Accept the review card's compact authoring form and normalize
                # it to the formal top-level decisions field before validation.
                entry = {**entry, "decisions": entry["analysis"]["decisions"]}
            if not isinstance(entry, dict) or not isinstance(entry.get("decisions"), list):
                raise ValueError(f"new review schema requires analysis and decisions objects: {review_key}")
            decisions = validate_decisions(current[review_key], entry["decisions"])
            analysis = validate_analysis(current[review_key], entry.get("analysis"), decisions)
            committed[review_key] = {"title": current[review_key]["clean_title"], "analysis": analysis, "decisions": decisions}
        unresolved = [
            (review_key, item.get("root", ""), item.get("status", item.get("reviewer_verdict", "")))
            for review_key, entry in committed.items()
            for item in entry["decisions"]
            if item.get("status", item.get("reviewer_verdict", "approved")) in ("uncertain", "pending", "reclassify")
        ]
        if unresolved:
            raise ValueError(f"batch contains unresolved review items and cannot be committed: {unresolved}")
        batch_dir = inside(records_dir / "批次审核", records_dir)
        batch_dir.mkdir(parents=True, exist_ok=True)
        destination = inside(batch_dir / f"批次_{int(args.batch):04d}.json", records_dir)
        destination.write_text(json.dumps({"batch": int(args.batch), "committed_at": datetime.now().isoformat(timespec="seconds"), "reviews": committed}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        batch["status"] = "committed"
        batch["review_file"] = destination.relative_to(ws).as_posix()
        batch["committed_at"] = datetime.now().isoformat(timespec="seconds")
        next_number = int(args.batch) + 1 if str(int(args.batch) + 1) in batches else None
        if next_number is None:
            # The final batch of an account still requires account-level
            # formal sync before the account is marked complete. This also
            # applies when the account is the final account in the queue.
            current_account = batch["items"][0].get("account") if batch.get("items") else state.get("active_account")
            if current_account and current_account not in state.get("completed_accounts", []):
                state["workflow_status"] = "awaiting_account_confirmation"
                state["active_account"] = current_account
            else:
                state["workflow_status"] = "complete"
                state["active_account"] = None
            state["active_batch"] = None
        elif batches[str(next_number)]["items"][0]["account"] == state.get("active_account"):
            state["workflow_status"] = "active"
            state["active_batch"] = next_number
        else:
            state["workflow_status"] = "awaiting_account_confirmation"
            state["active_batch"] = None
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"batch": args.batch, "status": "committed", "titles": len(batch["items"]), "workflow_status": state["workflow_status"], "next_batch": state.get("active_batch"), "next_account": state.get("active_account")}, ensure_ascii=False))
        return 0

    if any(item.get("status") != "committed" for item in batches.values()):
        raise ValueError("all ten-title batches must be committed before finalize")
    merged = {}
    for item in batches.values():
        batch_file = inside(ws / item["review_file"], ws)
        data = load_json(batch_file, {})
        merged.update(data.get("reviews", {}))
    final_reviews = inside(records_dir / "本轮审核_已完成.json", ws)
    final_reviews.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ready", "reviewed_titles": len(merged), "reviews": final_reviews.relative_to(ws).as_posix()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL: {exc}")
        raise SystemExit(2)
