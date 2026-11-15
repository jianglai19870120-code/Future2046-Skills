"""Review a generated category guide against the current formal card set."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def value(workspace: Path, key: str) -> str:
    for line in (workspace / "workspace.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip().strip('"\'')
    raise SystemExit(f"workspace.yaml 缺少 {key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--guide-run-id", required=True)
    parser.add_argument("--visual-reviewed", action="store_true")
    parser.add_argument("--render-dir", default="")
    args = parser.parse_args()
    ws = Path(args.workspace).resolve()
    run = ws / value(ws, "record_root") / "guides" / "staging" / args.category / args.guide_run_id
    errors = []
    manifest_path = run / "manifest.json"
    review_boundary = run / "boundary-review.json"
    docx = run / f"{args.category}避坑指南.docx"
    if not manifest_path.is_file(): errors.append("manifest.json 不存在")
    if not review_boundary.is_file(): errors.append("boundary-review.json 不存在")
    if not docx.is_file(): errors.append("DOCX 不存在")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    boundary = json.loads(review_boundary.read_text(encoding="utf-8")) if review_boundary.is_file() else {}
    if boundary.get("status") != "pass": errors.append("边界审核未通过")
    cards = manifest.get("cards", [])
    assignments = json.loads((run / "assignment-manifest.json").read_text(encoding="utf-8")).get("assignments", []) if (run / "assignment-manifest.json").is_file() else []
    if manifest.get("category") != args.category: errors.append("manifest 分类不一致")
    if manifest.get("cardCount") != len(assignments): errors.append("manifest 数量与 assignment 不一致")
    if len({item.get("cardId") for item in assignments}) != len(assignments): errors.append("assignment 卡片重复")
    card_root = ws / value(ws, "card_root")
    for item in assignments:
        card_index = ws / value(ws, "record_root") / "card-index.jsonl"
        row = next((json.loads(line) for line in card_index.read_text(encoding="utf-8").splitlines() if line.strip() and json.loads(line).get("cardId") == item.get("cardId")), None)
        if not row:
            errors.append(f"卡片不在索引: {item.get('cardId')}")
            continue
        path = ws / row["cardPath"]
        if not path.is_file() or card_root not in path.resolve().parents: errors.append(f"卡片路径无效: {item.get('cardId')}")
        elif sha256(path) != item.get("cardSha256"): errors.append(f"卡片哈希变化: {item.get('cardId')}")
    if manifest.get("sourceCardSetSha256") != boundary.get("sourceCardSetSha256"): errors.append("输入卡片集合哈希不一致")
    if docx.is_file():
        try:
            from docx import Document
            text = "\n".join(p.text for p in Document(docx).paragraphs)
            if args.category not in text or "避坑指南" not in text: errors.append("标题缺失")
            for forbidden in ("误区观点", "错误后果", "正确转向", "原文依据", "来源卡片", "source_address", "小标签｜"):
                if forbidden in text: errors.append(f"出现不应展示的字段: {forbidden}")
            for item in assignments:
                if item.get("subchapter") not in text: errors.append(f"小标签缺失: {item.get('cardId')}")
            for chapter, groups in manifest.get("chapters", {}).items():
                expected = sum(groups.values())
                actual = [item.get("number") for item in cards if item.get("chapter") == chapter]
                if actual and actual != list(range(1, expected + 1)): errors.append(f"篇章编号不连续: {chapter}")
            if manifest.get("docxSha256") != sha256(docx): errors.append("DOCX 哈希与 manifest 不一致")
        except Exception as exc:
            errors.append(f"DOCX 无法打开: {exc}")
    visual = "pending"
    if args.visual_reviewed:
        render = Path(args.render_dir) if args.render_dir else run / "render"
        if not list(render.glob("*.png")): errors.append("视觉审核已声明，但没有 PNG 页面")
        else: visual = "pass"
    result = {"schemaVersion": 2, "category": args.category, "guideRunId": args.guide_run_id, "reviewedAt": datetime.now(timezone.utc).isoformat(), "status": "pass" if not errors else "fail", "visualReview": visual, "errors": errors, "manifest": str(manifest_path)}
    (run / "review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
