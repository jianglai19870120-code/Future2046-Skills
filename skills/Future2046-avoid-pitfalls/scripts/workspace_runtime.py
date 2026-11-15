#!/usr/bin/env python3
"""Run an official command with workspace-scoped Python and temporary caches."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

from workspace_guard import verify


OFFICIAL_SCRIPTS = {
    "audit_runtime_paths.py", "audit_workspace.py", "commit_run.py",
    "materialize_excel_sources.py", "migrate_card_viewpoint_single.py",
    "prepare_submission.py", "record_review.py", "recover_run.py",
    "run_single_source.py", "source_queue.py", "stage_receipt.py",
    "validate_pipeline.py", "workspace_guard.py", "generate_category_guide.py",
    "review_category_boundary.py", "review_category_guide.py", "promote_category_guide.py", "render_category_guide.py",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch an official 少走弯路 command safely.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--script", required=True, choices=sorted(OFFICIAL_SCRIPTS))
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="arguments for the selected script; begin with --")
    args = parser.parse_args()
    try:
        report = verify(Path(args.workspace))
        cache_python = Path(report["pythonCache"])
        cache_tmp = Path(report["temporaryCache"])
        cache_python.mkdir(parents=True, exist_ok=True)
        cache_tmp.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({
            "FUTURE2046_WORKSPACE_LAUNCHED": "1",
            "PYTHONPYCACHEPREFIX": str(cache_python),
            "FUTURE2046_PYCACHE_PREFIX": str(cache_python),
            "TEMP": str(cache_tmp),
            "TMP": str(cache_tmp),
            "TMPDIR": str(cache_tmp),
        })
        extra = list(args.command)
        if extra[:1] == ["--"]:
            extra = extra[1:]
        script = Path(__file__).resolve().parent / args.script
        result = subprocess.run(
            # All official commands use subparsers, so the workspace option
            # must be appended after the selected subcommand and its options.
            [sys.executable, str(script), *extra, "--workspace", report["workspace"]],
            env=env,
        )
        return result.returncode
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
