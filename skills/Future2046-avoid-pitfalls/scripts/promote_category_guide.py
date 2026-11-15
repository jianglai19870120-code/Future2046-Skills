"""Promote a reviewed staged category guide atomically with rollback backup."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def record_root(workspace: Path) -> Path:
    cfg = workspace / "workspace.yaml"
    for line in cfg.read_text(encoding="utf-8").splitlines():
        if line.startswith("record_root:"):
            value = line.split(":", 1)[1].strip().strip('"\'')
            return workspace / value
    raise SystemExit("workspace.yaml 缺少 record_root")


def guide_root(workspace: Path) -> Path:
    for line in (workspace / "workspace.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("guide_root:"):
            root = (workspace / line.split(":", 1)[1].strip().strip('"\'')).resolve()
            if workspace not in root.parents:
                raise SystemExit("guide_root 越出工作区")
            return root
    raise SystemExit("workspace.yaml 缺少 guide_root")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--guide-run-id", required=True)
    args = parser.parse_args()
    ws = Path(args.workspace).resolve()
    record = record_root(ws) / "guides"
    staging = record / "staging" / args.category / args.guide_run_id
    review_path = staging / "review.json"
    review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.is_file() else {}
    if review.get("status") != "pass" or review.get("visualReview") != "pass":
        raise SystemExit("结构或视觉审核未通过，不允许正式替换")
    source = staging / f"{args.category}避坑指南.docx"
    output_root = guide_root(ws)
    output_root.mkdir(parents=True, exist_ok=True)
    base = output_root / f"{args.category}避坑指南.docx"
    target = base
    if target.exists():
        target = output_root / f"{args.category}避坑指南_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
    if not source.is_file(): raise SystemExit(f"staging 文档不存在: {source}")
    rollback = record / "rollback"
    rollback.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        backup = rollback / f"{args.category}避坑指南_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        shutil.copy2(target, backup)
    temp = target.with_suffix(".docx.tmp")
    shutil.copy2(source, temp)
    os.replace(temp, target)
    result = {"category": args.category, "guideRunId": args.guide_run_id, "status": "promoted", "promotedAt": datetime.now(timezone.utc).isoformat(), "target": str(target.relative_to(ws)).replace("\\", "/")}
    (record / "guides" / "promotions" / f"{args.category}_{args.guide_run_id}.json").parent.mkdir(parents=True, exist_ok=True)
    (record / "guides" / "promotions" / f"{args.category}_{args.guide_run_id}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
