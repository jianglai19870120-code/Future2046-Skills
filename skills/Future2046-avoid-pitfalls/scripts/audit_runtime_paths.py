#!/usr/bin/env python3
"""Find known production artifacts outside the configured workspace."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from pipeline_contract import workspace_path

PATTERNS = ("create_review*.py", "prepare_commit*.py", "commit*.py", "repair*.py",
            "write_review*.py", "check_*.py", "Future2046-*.py", "MISC-V4-*.json")
OFFICIAL = {"audit_runtime_paths.py", "audit_workspace.py", "commit_run.py",
            "materialize_excel_sources.py", "pipeline_contract.py", "prepare_submission.py",
            "record_review.py", "recover_run.py", "source_queue.py", "stage_receipt.py",
            "validate_pipeline.py"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def collect(folder: Path, recursive: bool) -> list[Path]:
    if not folder.is_dir():
        return []
    paths = set()
    for pattern in PATTERNS:
        iterator = folder.rglob(pattern) if recursive else folder.glob(pattern)
        paths.update(p for p in iterator if p.is_file())
    return sorted(paths)


def is_misconception_artifact(path: Path) -> bool:
    """Avoid reporting similarly named scripts from unrelated projects."""
    name = path.name.lower()
    if path.parent == Path.home() and name.startswith(("prepare_commit_", "write_review_")):
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:65536]
    except OSError:
        return False
    markers = ("MISC-V4", "误区拆解", "avoid-pitfalls",
               "Future2046-Skills\\workspaces\\误区拆解",
               "Future2046-Skills/workspaces/误区拆解")
    return any(marker in text for marker in markers)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--allow-findings", action="store_true")
    args = ap.parse_args()
    try:
        root = Path(args.workspace).resolve()
        records = workspace_path(root, "record_root")
        user_root = Path.home()
        temp_root = Path.home() / "AppData/Local/Temp"
        repo_root = root.parents[1] if root.parent.name == "workspaces" else root.parent
        candidates = []
        # Only inspect direct Temp children.  Recursive Temp trees contain
        # unrelated release-test copies belonging to other projects.
        candidates += [(p, "temporary_production_script") for p in collect(temp_root, False)]
        candidates += [(p, "external_user_artifact") for p in collect(user_root, False)]
        candidates += [(p, "repository_root_artifact") for p in collect(repo_root, False)]
        candidates += [(p, "skill_package_artifact") for p in collect(
            repo_root / "skills" / "Future2046-avoid-pitfalls", True)]
        candidates = [(p, kind) for p, kind in candidates
                      if not p.is_relative_to(records)
                      and not (p.parent.name == "scripts" and p.name in OFFICIAL)
                      and is_misconception_artifact(p)]
        report = {"workspace": str(root), "recordRoot": str(records),
                  "workspaceRuntimeClean": not candidates,
                  "externalArtifacts":[{"path":p.as_posix(),"type":kind,"size":p.stat().st_size,
                                        "sha256":sha(p),"action":"delete_after_confirmation"}
                                       for p,kind in candidates]}
        if args.write:
            out = records / "runtime-path-audit.json"
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if (not candidates or args.allow_findings) else 1
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
