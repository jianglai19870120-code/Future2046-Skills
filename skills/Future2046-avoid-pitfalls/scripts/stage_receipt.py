#!/usr/bin/env python3
"""Create a locked run and append exactly one real stage receipt at a time."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from pipeline_contract import check_stage, digest, record_path, run_file, workspace_path

STAGES = [
    "source_scan", "transcription_normalization", "misconception_candidate_identification",
    "five_gate_judgment", "intra_document_deduplication", "global_deduplication_pre",
    "card_draft_generation", "oral_polish", "independent_review",
    "global_deduplication_final", "formal_card_write", "index_update",
    "processing_log_write", "completion_validation",
]
COMMIT_ONLY = {"formal_card_write", "index_update", "processing_log_write", "completion_validation"}
TERMINAL = {"completed", "skipped", "failed", "paused"}


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def after(value: str) -> str:
    current = datetime.fromisoformat(value)
    candidate = datetime.now().astimezone()
    if candidate <= current:
        candidate = current + timedelta(microseconds=1)
    return candidate.isoformat(timespec="microseconds")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def artifact_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    elif path.is_dir():
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(item.relative_to(path).as_posix().encode("utf-8"))
            digest.update(item.read_bytes())
    else:
        raise RuntimeError(f"artifact does not exist: {path}")
    return digest.hexdigest().upper()


def source_seq(source: str, position: int) -> int:
    if position < 1:
        raise ValueError("position must be a positive queue position")
    # Queue position is authoritative. Source filenames may be reused by
    # different source containers (for example Excel-materialized files), so
    # never infer queue order from a filename number.
    return position


def source_metadata(path: Path) -> dict:
    """Read lightweight source identity fields from generated Markdown frontmatter."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"sourceKind": "text"}
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        return {"sourceKind": "text"}
    front = text[4:].split("\n---\n", 1)[0]
    fields = {}
    for line in front.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip('"')
    if fields.get("source_type") == "excel_row":
        return {"sourceKind": "excel_row", "sourceIdentity": fields.get("source_row_fingerprint"),
                "sourceExcel": fields.get("source_excel"), "sourceSheet": fields.get("source_sheet"),
                "sourceRow": int(fields["source_row"]) if fields.get("source_row", "").isdigit() else None}
    return {"sourceKind": fields.get("source_type", "text")}


def paths(root: Path) -> tuple[Path, Path]:
    records = workspace_path(root, "record_root")
    return records / "active-run.json", records / "pipeline.lock"


def start(args: argparse.Namespace) -> int:
    root = Path(args.workspace)
    records = workspace_path(root, "record_root")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id) or (args.batch_id and not re.fullmatch(r"[A-Za-z0-9_-]+", args.batch_id)):
        raise RuntimeError("run-id and batch-id may contain only ASCII letters, digits, underscore and hyphen")
    source = args.source.replace("\\", "/")
    source_path = root / Path(source.replace("/", "\\"))
    if not source_path.exists():
        raise RuntimeError(f"source does not exist: {source}")
    active, lock = paths(root)
    if active.exists():
        raise RuntimeError("another run is active; complete or recover it before starting the next source")
    seq = source_seq(source, args.position)
    batch_path = records / "batches" / f"{args.batch_id}.json" if args.batch_id else None
    if batch_path:
        if args.batch_start_position is None:
            raise RuntimeError("batch requires --batch-start-position")
        if batch_path.exists():
            batch = read_json(batch_path)
            if batch.get("startPosition") != args.batch_start_position or batch.get("nextPosition") != args.position:
                raise RuntimeError("source does not match persisted serial batch queue")
        elif args.position != args.batch_start_position:
            raise RuntimeError("first batch source must match batch start position")
    log = records / "processing-log.jsonl"
    if args.batch_id and args.position != args.batch_start_position and log.exists():
        rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()]
        previous = [r for r in rows if r.get("batchId") == args.batch_id and r.get("sourceSequence") == args.position - 1]
        if not previous or previous[-1].get("pipelineVersion") != "v4-artifact" or previous[-1].get("status") not in {"completed", "skipped"}:
            raise RuntimeError(f"previous source {args.position - 1} has no verified v4 terminal record in batch")
    elif args.batch_id and args.position != args.batch_start_position:
        raise RuntimeError("batch has no previous completed source")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        with lock.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps({"runId": args.run_id, "pid": os.getpid(), "startedAt": stamp()}, ensure_ascii=False) + "\n")
    except FileExistsError as exc:
        raise RuntimeError("pipeline.lock already exists; another run is active or requires recovery") from exc
    run_dir = records / "runs" / args.run_id
    try:
        run_dir.mkdir(parents=True, exist_ok=False)
        (records / "staging" / args.run_id / "cards").mkdir(parents=True, exist_ok=False)
    except Exception:
        if lock.exists():
            lock.unlink()
        raise
    run = {"pipelineVersion": "v4-artifact", "oralPolishContract": "dialogue-v2", "normalizationWritebackRequired": True, "candidateEnumerationRequired": True, "viewpointPatternRequired": True, "runId": args.run_id, "batchId": args.batch_id, "producerId": args.producer_id, "sourcePath": source, "sourceSequence": seq, "queuePosition": seq, "status": "in_progress", "stageReceipts": [], "createdAt": stamp()}
    run.update(source_metadata(source_path))
    write_json(run_dir / "run.json", run)
    write_json(active, {"runId": args.run_id, "sourcePath": source, "sourceSequence": seq, "queuePosition": seq, "status": "in_progress", "startedAt": run["createdAt"]})
    if batch_path and not batch_path.exists():
        batch_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(batch_path, {"batchId": args.batch_id, "startPosition": args.batch_start_position, "nextPosition": args.position, "createdAt": run["createdAt"]})
    print(json.dumps(run, ensure_ascii=False))
    return 0


def record(args: argparse.Namespace) -> int:
    root = Path(args.workspace)
    records = workspace_path(root, "record_root")
    run_path = records / "runs" / args.run_id / "run.json"
    if not run_path.exists():
        raise RuntimeError("run does not exist")
    run = read_json(run_path)
    if run.get("status") != "in_progress":
        raise RuntimeError("run is not in_progress")
    receipts = run.get("stageReceipts", [])
    expected = STAGES[len(receipts)] if len(receipts) < len(STAGES) else None
    if args.stage != expected:
        raise RuntimeError(f"expected stage {expected}, received {args.stage}")
    if args.stage in COMMIT_ONLY:
        raise RuntimeError(f"{args.stage} can only be produced by commit_run.py")
    active, lock = paths(root)
    if not active.is_file() or not lock.is_file() or read_json(active).get("runId") != args.run_id or read_json(lock).get("runId") != args.run_id:
        raise RuntimeError("run does not hold the active pipeline lock")
    if args.status != "completed":
        raise RuntimeError("use recovery flow for failed, skipped, or paused stages")
    previous_hash = receipts[-1]["evidence"]["outputSha256"] if receipts else None
    artifact_path = run_file(root, args.run_id, args.artifact)
    evidence = check_stage(root, run, args.stage, artifact_path, previous_hash)
    if args.stage == "source_scan" and digest(root / run["sourcePath"]) != evidence["outputSha256"]:
        raise RuntimeError("source changed before snapshot receipt")
    previous = receipts[-1].get("completedAt") if receipts else None
    started = after(previous) if previous else stamp()
    completed = after(started)
    receipts.append({"stage": args.stage, "status": args.status, "startedAt": started, "completedAt": completed, "evidence": evidence})
    run["stageReceipts"] = receipts
    if args.status != "completed":
        run["status"] = args.status
    write_json(run_path, run)
    print(json.dumps(receipts[-1], ensure_ascii=False))
    return 0


def record_batch(args: argparse.Namespace) -> int:
    """Record a contiguous group of already-produced artifacts in one process.

    This only reduces process startup and repeated workspace/config loading. Each
    item still goes through the same stage validator and is written as its own
    receipt, so batching cannot skip or reorder stages.
    """
    root = Path(args.workspace).resolve()
    manifest = record_path(root, args.stages_json)
    items = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        raise RuntimeError("stages-json must contain a non-empty array")
    for item in items:
        if not isinstance(item, dict) or not item.get("stage") or not item.get("artifact"):
            raise RuntimeError("each batched stage requires stage and artifact")
        one = argparse.Namespace(
            workspace=args.workspace,
            run_id=args.run_id,
            stage=item["stage"],
            status="completed",
            artifact=item["artifact"],
        )
        record(one)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start")
    s.add_argument("--workspace", required=True); s.add_argument("--source", required=True); s.add_argument("--run-id", required=True); s.add_argument("--position", type=int, required=True); s.add_argument("--producer-id", required=True); s.add_argument("--batch-id"); s.add_argument("--batch-start-position", type=int)
    r = sub.add_parser("record")
    r.add_argument("--workspace", required=True); r.add_argument("--run-id", required=True); r.add_argument("--stage", choices=STAGES, required=True); r.add_argument("--status", choices=["completed"], default="completed"); r.add_argument("--artifact", required=True, help="workspace-relative stage artifact inside current run")
    b = sub.add_parser("record-batch")
    b.add_argument("--workspace", required=True); b.add_argument("--run-id", required=True); b.add_argument("--stages-json", required=True, help="JSON array of contiguous {stage, artifact} items")
    args = ap.parse_args()
    try:
        if args.command == "start":
            return start(args)
        if args.command == "record":
            return record(args)
        return record_batch(args)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
