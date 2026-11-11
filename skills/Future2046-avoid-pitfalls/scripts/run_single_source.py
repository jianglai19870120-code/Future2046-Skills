#!/usr/bin/env python3
"""Safe controller for initializing and validating one V4 source run.

This controller handles the mechanical run setup and source snapshot only.
Semantic correction, candidate selection, polishing and review still require
real stage artifacts and must never be fabricated by a wrapper script.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from pipeline_contract import digest, inside, run_file, workspace_path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent


def invoke(script: str, args: list[str], workspace: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(HERE / script), "--workspace", str(workspace), *args],
        text=True, encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise RuntimeError(f"{script} failed with exit code {result.returncode}")


def init_run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    source = args.source.replace("\\", "/")
    source_path = inside(workspace, source)
    if source_path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("single-source controller currently accepts Markdown or text sources")
    start_args = ["start", "--source", source, "--run-id", args.run_id,
                  "--position", str(args.position), "--producer-id", args.producer_id]
    if args.batch_id:
        start_args += ["--batch-id", args.batch_id, "--batch-start-position", str(args.batch_start_position)]
    invoke("stage_receipt.py", start_args, workspace)
    records = workspace_path(workspace, "record_root")
    run_dir = records / "runs" / args.run_id
    snapshot = run_dir / "source-snapshot" / source_path.name
    corrected = run_dir / "corrected" / f"{source_path.stem}.md"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    corrected.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, snapshot)
    corrected.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    artifact = run_dir / "source_scan.json"
    artifact.write_text(json.dumps({
        "runId": args.run_id, "sourcePath": source, "stage": "source_scan",
        "sourceSnapshotPath": snapshot.relative_to(workspace).as_posix(),
        "sourceSha256": digest(snapshot),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    invoke("stage_receipt.py", ["record", "--run-id", args.run_id,
                                 "--stage", "source_scan", "--artifact",
                                 artifact.relative_to(workspace).as_posix()], workspace)
    print(json.dumps({"runId": args.run_id, "sourcePath": source,
                      "snapshotPath": snapshot.relative_to(workspace).as_posix(),
                      "correctedPath": corrected.relative_to(workspace).as_posix(),
                      "nextStage": "transcription_normalization",
                      "sourceWriteback": "disabled by default"}, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize and validate one safe V4 source run")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="create a locked run and verified source snapshot")
    init.add_argument("--workspace", required=True)
    init.add_argument("--source", required=True)
    init.add_argument("--run-id", required=True)
    init.add_argument("--position", required=True, type=int)
    init.add_argument("--producer-id", required=True)
    init.add_argument("--batch-id")
    init.add_argument("--batch-start-position", type=int)
    init.set_defaults(func=init_run)
    validate = sub.add_parser("validate", help="validate a run using the formal pipeline validator")
    validate.add_argument("--workspace", required=True)
    validate.add_argument("--source", required=True)
    validate.set_defaults(func=lambda a: subprocess.call([sys.executable, str(HERE / "validate_pipeline.py"), "--workspace", a.workspace, "--source", a.source, "--require-full-run"]))
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
