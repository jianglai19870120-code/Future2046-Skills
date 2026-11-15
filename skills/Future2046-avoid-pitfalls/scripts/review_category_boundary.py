"""Validate an LLM-authored category guide boundary plan before generation."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def workspace_value(workspace: Path, key: str) -> str:
    for line in (workspace / "workspace.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip().strip('"\'')
    raise SystemExit(f"workspace.yaml 缺少 {key}")


def card_set(workspace: Path, category: str):
    record = workspace / workspace_value(workspace, "record_root")
    cards = []
    for line in (record / "card-index.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("recordType") == "indexMeta" or row.get("status") != "active" or row.get("category") != category:
            continue
        path = workspace / row["cardPath"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        cards.append({"cardId": str(row["cardId"]), "sha256": digest})
    return cards, json_hash(cards)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--boundary-plan", required=True)
    parser.add_argument("--category", required=True)
    args = parser.parse_args()
    ws = Path(args.workspace).resolve()
    plan_path = Path(args.boundary_plan).resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    errors = []
    if plan.get("contract") != "category-guide-boundary-v1": errors.append("契约不正确")
    if plan.get("category") != args.category: errors.append("分类不一致")
    cards, fingerprint = card_set(ws, args.category)
    if plan.get("sourceCardSetSha256") != fingerprint: errors.append("正式卡片集合哈希不一致")
    chapters = plan.get("chapters") or []
    chapter_names = [item.get("name") for item in chapters]
    if len(set(chapter_names)) != len(chapter_names): errors.append("篇章名称重复")
    allowed = {(chapter.get("name"), sub.get("name")) for chapter in chapters for sub in chapter.get("subchapters", [])}
    for chapter in chapters:
        if not chapter.get("definition"): errors.append(f"篇章缺少 definition: {chapter.get('name')}")
        subs = chapter.get("subchapters") or []
        if not subs: errors.append(f"篇章没有小标签: {chapter.get('name')}")
        if len({sub.get("name") for sub in subs}) != len(subs): errors.append(f"小标签重复: {chapter.get('name')}")
        for sub in subs:
            for key in ("definition", "includeWhen", "excludeWhen", "evidenceExamples"):
                if not sub.get(key): errors.append(f"小标签缺少 {key}: {chapter.get('name')}/{sub.get('name')}")
    assignments = plan.get("assignments") or []
    if assignments:
        ids = [str(item.get("cardId")) for item in assignments]
        if len(ids) != len(set(ids)): errors.append("assignment 卡片重复")
        if set(ids) != {item["cardId"] for item in cards}: errors.append("assignment 未完整覆盖正式卡片")
        for item in assignments:
            if (item.get("chapter"), item.get("subchapter")) not in allowed: errors.append(f"assignment 归属不存在: {item.get('cardId')}")
            if not item.get("assignmentReason"): errors.append(f"assignment 缺少语义理由: {item.get('cardId')}")
    result = {
        "schemaVersion": 1,
        "contract": "category-guide-boundary-review-v1",
        "category": args.category,
        "reviewedAt": datetime.now(timezone.utc).isoformat(),
        "status": "pass" if not errors else "fail",
        "sourceCardSetSha256": fingerprint,
        "cardCount": len(cards),
        "chapterCount": len(chapters),
        "assignmentMode": "provided" if assignments else "generated_after_boundary_review",
        "errors": errors,
    }
    output = plan_path.parent / "boundary-review.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
