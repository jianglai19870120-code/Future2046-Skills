"""Build a category guide from an LLM-authored boundary plan and assignments."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def load_workspace(workspace: Path) -> dict:
    try:
        import yaml
        data = yaml.safe_load((workspace / "workspace.yaml").read_text(encoding="utf-8")) or {}
    except ImportError:
        data = {}
        categories = []
        in_categories = False
        for line in (workspace / "workspace.yaml").read_text(encoding="utf-8").splitlines():
            if line.strip() == "supported_categories:":
                in_categories = True
                continue
            if in_categories and re.match(r"^\s*-\s+", line):
                categories.append(line.split("-", 1)[1].strip().strip('"\''))
                continue
            if in_categories and line and not line.startswith((" ", "\t")):
                in_categories = False
            match = re.match(r"^(\w+):\s*[\"']?(.*?)[\"']?$", line)
            if match:
                data[match.group(1)] = match.group(2)
        if categories:
            data["supported_categories"] = categories
    required = ("card_root", "record_root", "guide_root", "supported_categories")
    missing = [key for key in required if key not in data]
    if missing:
        raise SystemExit(f"workspace.yaml 缺少字段: {', '.join(missing)}")
    for key in ("card_root", "record_root", "guide_root"):
        resolved = (workspace / str(data[key])).resolve()
        if workspace not in resolved.parents:
            raise SystemExit(f"{key} 越出工作区: {resolved}")
    if str(data["guide_root"]) in {str(data["card_root"]), str(data["record_root"]), str(data.get("source_root", ""))}:
        raise SystemExit("guide_root 不能指向源稿、正式卡片或处理记录目录")
    return data


def parse_card(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"缺少 frontmatter: {path}")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError(f"frontmatter 未闭合: {path}")
    frontmatter = text[4:end].strip("\n")
    meta = {}
    try:
        import yaml
        meta = yaml.safe_load(frontmatter) or {}
    except ImportError:
        for line in frontmatter.splitlines():
            match = re.match(r"^(\w+):\s*[\"']?(.*?)[\"']?$", line)
            if match:
                meta[match.group(1)] = match.group(2)
    body = text[end + 4:]
    title = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    scene = re.search(r"^##\s+误区场景\s*$([\s\S]*?)(?=^##\s+|\Z)", body, re.M)
    if not title or not scene:
        raise ValueError(f"卡片缺少标题或误区场景: {path}")
    return {
        "path": path,
        "cardId": str(meta.get("card_id", "")),
        "category": str(meta.get("category", "")),
        "title": title.group(1).strip(),
        # Some legacy cards contain escaped line breaks (literal ``\\n``)
        # in the scene body. Normalize them before splitting into Word
        # paragraphs so the escape sequence cannot leak into the guide.
        "scene": scene.group(1).strip().replace("\\r\\n", "\n").replace("\\n", "\n"),
        "sha256": sha256(path),
    }


def load_cards(workspace: Path, cfg: dict, category: str) -> tuple[list[dict], str]:
    record_root = workspace / str(cfg["record_root"])
    card_root = workspace / str(cfg["card_root"])
    index_path = record_root / "card-index.jsonl"
    if not index_path.is_file():
        raise SystemExit(f"索引不存在: {index_path}")
    cards = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("recordType") == "indexMeta" or row.get("status") != "active" or row.get("category") != category:
            continue
        path = workspace / row["cardPath"]
        if not path.is_file() or card_root not in path.resolve().parents:
            raise SystemExit(f"索引卡片路径无效: {path}")
        card = parse_card(path)
        if card["cardId"] != str(row.get("cardId", "")) or card["category"] != category:
            raise SystemExit(f"卡片与索引不一致: {path}")
        cards.append(card)
    if not cards:
        raise SystemExit(f"分类没有正式卡片: {category}")
    fingerprint = json_hash([{ "cardId": c["cardId"], "sha256": c["sha256"] } for c in cards])
    return cards, fingerprint


def validate_plan(plan: dict, category: str, cards: list[dict], fingerprint: str) -> tuple[list[str], dict[str, dict[str, list[dict]]]]:
    if plan.get("contract") != "category-guide-boundary-v1":
        raise SystemExit("boundary-plan 契约不正确")
    if plan.get("category") != category:
        raise SystemExit("boundary-plan 分类不一致")
    if plan.get("sourceCardSetSha256") != fingerprint:
        raise SystemExit("boundary-plan 对应的正式卡片集合已变化")
    chapters = plan.get("chapters") or []
    if not chapters:
        raise SystemExit("boundary-plan 没有篇章")
    order = [str(chapter.get("name", "")) for chapter in chapters]
    if len(set(order)) != len(order) or any(not name for name in order):
        raise SystemExit("boundary-plan 篇章名称重复或为空")
    definitions = {}
    for chapter in chapters:
        subs = chapter.get("subchapters") or []
        if not subs:
            raise SystemExit(f"篇章没有小标签: {chapter.get('name')}")
        names = [str(item.get("name", "")) for item in subs]
        if len(set(names)) != len(names) or any(not name for name in names):
            raise SystemExit(f"小标签名称重复或为空: {chapter.get('name')}")
        for item in subs:
            for key in ("definition", "includeWhen", "excludeWhen", "evidenceExamples"):
                if not item.get(key):
                    raise SystemExit(f"小标签缺少 {key}: {chapter.get('name')}/{item.get('name')}")
        definitions[chapter["name"]] = {item["name"]: [] for item in subs}
    by_id = {card["cardId"]: card for card in cards}
    assignments = plan.get("assignments") or []
    if assignments:
        if len(assignments) != len(cards) or len({str(item.get("cardId")) for item in assignments}) != len(cards):
            raise SystemExit("boundary-plan assignment 未完整覆盖正式卡片")
        chosen = assignments
    else:
        chosen = []
        for card in cards:
            explicit = next((target for phrase, target in (plan.get("titleAssignments") or {}).items() if phrase in card["title"]), None)
            if explicit:
                chosen.append({"cardId": card["cardId"], "chapter": explicit[0], "subchapter": explicit[1], "cardSha256": card["sha256"], "assignmentReason": "边界方案中的明确语义例外，避免局部关键词造成错误归类"})
                continue
            haystack = f"{card['title']}\n{card['scene']}"
            candidates = []
            for chapter in chapters:
                chapter_name = chapter["name"]
                chapter_score = 4 * sum(1 for p in chapter.get("matchTitlePatterns", []) if p in card["title"]) + sum(1 for k in chapter.get("matchKeywords", []) if k in haystack)
                for sub in chapter.get("subchapters", []):
                    sub_score = 4 * sum(1 for p in sub.get("matchTitlePatterns", []) if p in card["title"]) + sum(1 for k in sub.get("matchKeywords", []) if k in haystack)
                    if chapter_score + sub_score:
                        candidates.append((chapter_score + sub_score, chapter_name, sub["name"]))
            candidates.sort(reverse=True)
            if not candidates or (len(candidates) > 1 and candidates[0][0] == candidates[1][0]):
                raise SystemExit(f"无法形成唯一语义归属，需要人工复核: {card['cardId']} / {card['title']}")
            _, chapter, subchapter = candidates[0]
            chosen.append({"cardId": card["cardId"], "chapter": chapter, "subchapter": subchapter, "cardSha256": card["sha256"], "assignmentReason": "依据边界方案的篇章定义与小标签纳入条件，结合标题和完整误区场景归类"})
    for item in chosen:
        card_id = str(item.get("cardId"))
        if card_id not in by_id:
            raise SystemExit(f"assignment 中存在未知卡片: {card_id}")
        chapter = str(item.get("chapter", "")); subchapter = str(item.get("subchapter", ""))
        if chapter not in definitions or subchapter not in definitions[chapter]:
            raise SystemExit(f"assignment 归属不在边界方案中: {card_id}")
        if not item.get("assignmentReason"):
            raise SystemExit(f"assignment 缺少语义理由: {card_id}")
        if item.get("cardSha256") != by_id[card_id]["sha256"]:
            raise SystemExit(f"assignment 卡片哈希变化: {card_id}")
        definitions[chapter][subchapter].append(by_id[card_id] | {"assignmentReason": item["assignmentReason"]})
    for chapter, groups in list(definitions.items()):
        for subchapter in list(groups):
            if not groups[subchapter]:
                del groups[subchapter]
        if not groups:
            del definitions[chapter]
    if sum(len(cards) for groups in definitions.values() for cards in groups.values()) != len(cards):
        raise SystemExit("边界方案分配数量不完整")
    return order, definitions


def set_font(run, name, size, color, bold=False):
    from docx.shared import Pt
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold


def qn(tag):
    from docx.oxml.ns import qn as _qn
    return _qn(tag)


def build_docx(output: Path, category: str, chapter_order: list[str], groups: dict[str, dict[str, list[dict]]]):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(2.2); section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.1); section.right_margin = Cm(2.1)
    styles = doc.styles
    for style_name in ("Normal", "Body Text"):
        style = styles[style_name]
        style.font.name = "Microsoft YaHei"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(11)
        style.font.color.rgb = RGBColor(35, 35, 35)
    red = RGBColor(210, 0, 0)
    dark_red = RGBColor(192, 0, 0)
    black, gray = RGBColor(25, 25, 25), RGBColor(95, 95, 95)

    title = doc.add_paragraph(style="Title")
    title.paragraph_format.space_before = Pt(115)
    set_font(title.add_run(f"{category}避坑指南"), "Microsoft YaHei", 56, red, True)
    desc = doc.add_paragraph(); desc.paragraph_format.space_before = Pt(14)
    set_font(desc.add_run(f"把复杂的{category}行业误区，整理成可以快速浏览的判断地图"), "Microsoft YaHei", 14, gray)
    brand = doc.add_paragraph(); brand.paragraph_format.space_before = Pt(80)
    set_font(brand.add_run("@姜来已来2046"), "Microsoft YaHei", 12, red, True)
    doc.add_page_break()

    heading = doc.add_paragraph(); heading.paragraph_format.space_after = Pt(18)
    set_font(heading.add_run("目录"), "Microsoft YaHei", 24, red, True)
    chapter_index = 0
    for chapter in chapter_order:
        if chapter not in groups:
            continue
        chapter_index += 1
        chapter_cards = sum(len(items) for items in groups[chapter].values())
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(7); p.paragraph_format.keep_with_next = True
        set_font(p.add_run(f"{chapter_index:02d}  {chapter}"), "Microsoft YaHei", 14, dark_red, True)
        set_font(p.add_run(f"    {chapter_cards} 条"), "Microsoft YaHei", 11, dark_red)
        for subchapter, items in groups[chapter].items():
            q = doc.add_paragraph(); q.paragraph_format.left_indent = Cm(1.1); q.paragraph_format.space_after = Pt(2)
            set_font(q.add_run(f"{subchapter}  ·  {len(items)} 条"), "Microsoft YaHei", 10, gray)
    doc.add_page_break()

    first_chapter = True
    for chapter in chapter_order:
        if chapter not in groups:
            continue
        h = doc.add_paragraph(); h.paragraph_format.space_after = Pt(12); h.paragraph_format.keep_with_next = True
        if not first_chapter:
            h.paragraph_format.page_break_before = True
        first_chapter = False
        set_font(h.add_run(chapter), "Microsoft YaHei", 24, red, True)
        number = 0
        for subchapter, items in groups[chapter].items():
            label = doc.add_paragraph(); label.paragraph_format.space_before = Pt(10); label.paragraph_format.space_after = Pt(5); label.paragraph_format.keep_with_next = True
            set_font(label.add_run(subchapter), "Microsoft YaHei", 13, dark_red, True)
            for card in items:
                number += 1
                p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(3); p.paragraph_format.keep_with_next = True
                set_font(p.add_run(f"{number}  {card['title']}"), "Microsoft YaHei", 13, black, True)
                for paragraph in re.split(r"\n\s*\n", card["scene"]):
                    body = doc.add_paragraph(paragraph.strip()); body.paragraph_format.space_after = Pt(5); body.paragraph_format.line_spacing = 1.25
    output.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--boundary-plan", required=True)
    parser.add_argument("--guide-run-id", required=True)
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    cfg = load_workspace(workspace)
    if args.category not in list(cfg["supported_categories"] or []):
        raise SystemExit(f"分类不在 workspace.yaml supported_categories 中: {args.category}")
    cards, fingerprint = load_cards(workspace, cfg, args.category)
    plan_path = Path(args.boundary_plan).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    chapter_order, groups = validate_plan(plan, args.category, cards, fingerprint)
    record_root = workspace / str(cfg["record_root"])
    run_root = record_root / "guides" / "staging" / args.category / args.guide_run_id
    run_root.mkdir(parents=True, exist_ok=True)
    assignment_manifest = {
        "contract": "category-guide-assignment-v1",
        "category": args.category,
        "guideRunId": args.guide_run_id,
        "sourceCardSetSha256": fingerprint,
        "assignments": [
            {"cardId": card["cardId"], "chapter": chapter, "subchapter": subchapter, "cardSha256": card["sha256"], "assignmentReason": card["assignmentReason"]}
            for chapter in chapter_order if chapter in groups for subchapter, items in groups[chapter].items() for card in items
        ],
    }
    (run_root / "assignment-manifest.json").write_text(json.dumps(assignment_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    output = run_root / f"{args.category}避坑指南.docx"
    build_docx(output, args.category, chapter_order, groups)
    manifest = {
        "schemaVersion": 3,
        "category": args.category,
        "guideRunId": args.guide_run_id,
        "boundaryPlan": str(plan_path),
        "sourceCardSetSha256": fingerprint,
        "output": str(output.relative_to(workspace)).replace("\\", "/"),
        "cardCount": len(cards),
        "chapters": {chapter: {sub: len(items) for sub, items in groups[chapter].items()} for chapter in chapter_order if chapter in groups},
        "docxSha256": sha256(output),
        "reviewStatus": "pending",
    }
    (run_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "staged", "category": args.category, "guideRunId": args.guide_run_id, "output": str(output), "cardCount": len(cards)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
