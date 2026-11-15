#!/usr/bin/env python3
"""Validate a 少走弯路 workspace before any runtime state is created."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline_contract import workspace_layout, workspace_path, workspace_setting


def repository_root() -> Path:
    """Locate this Skill's repository without constraining a user's workspace path."""
    return Path(__file__).resolve().parents[3]


def verify(workspace: Path) -> dict[str, str]:
    """Return validated runtime locations without creating them."""
    root = workspace.resolve()
    repo = repository_root()
    wrong_root = (repo / "工作区").resolve()
    if root == wrong_root or root.is_relative_to(wrong_root):
        raise ValueError("禁止把仓库根目录下的 工作区 作为正式工作区")
    layout = workspace_layout(root)
    records = workspace_path(root, "record_root")
    if not records.is_relative_to(root):
        raise ValueError("记录目录越出工作区")
    return {
        "workspace": str(root),
        "repositoryRoot": str(repo),
        "recordRoot": str(records),
        "pythonCache": str(records / "cache" / "python"),
        "temporaryCache": str(records / "cache" / "tmp"),
        "wrongWorkspaceRoot": str(wrong_root),
        "technicalSkillName": str(workspace_setting(root, "technical_skill_name", "")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a 少走弯路 workspace before runtime writes.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(Path(args.workspace))
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(f"PASS: workspace guard: {report['workspace']}")
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
