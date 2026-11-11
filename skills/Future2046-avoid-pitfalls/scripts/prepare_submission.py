#!/usr/bin/env python3
"""Validate that submission inputs are inside the current run's E: workspace."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline_contract import digest, record_path, read_json, workspace_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--index-records", required=True,
                    help="submission/ 下的工作区相对 POSIX 路径")
    ap.add_argument("--final-dedup", required=True,
                    help="submission/ 下的最终去重报告相对 POSIX 路径")
    args = ap.parse_args()
    try:
        root = Path(args.workspace).resolve()
        records = workspace_path(root, "record_root")
        index_path = record_path(root, args.index_records, run_id=args.run_id,
                                 subdirectory="submission")
        dedup_path = record_path(root, args.final_dedup, run_id=args.run_id,
                                 subdirectory="submission")
        rows = json.loads(index_path.read_text(encoding="utf-8"))
        dedup = read_json(dedup_path)
        if not isinstance(rows, list):
            raise ValueError("index-records 必须是 JSON 数组")
        if dedup.get("result") != "passed":
            raise ValueError("最终全局去重未通过")
        print(json.dumps({"status": "ready", "runId": args.run_id,
                          "indexRecords": index_path.relative_to(root).as_posix(),
                          "indexSha256": digest(index_path),
                          "finalDedup": dedup_path.relative_to(root).as_posix(),
                          "recordRoot": records.relative_to(root).as_posix()},
                         ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
