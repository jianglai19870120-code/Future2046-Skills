#!/usr/bin/env python3
"""Inspect, roll back an interrupted commit, or resolve the current source."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from pipeline_contract import digest, inside, read_json, run_file, workspace_path


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def atomic_bytes(path: Path, value: bytes) -> None:
    tmp = path.with_name(path.name + ".recovery-tmp")
    tmp.write_bytes(value)
    os.replace(tmp, path)


def atomic_json(path: Path, value: dict) -> None:
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def rollback(root: Path, run_dir: Path, journal: dict) -> None:
    backup = run_dir / "rollback"
    for entry in journal["cards"]:
        target = inside(root, entry["target"])
        old_hash = entry.get("oldSha256")
        current = digest(target) if target.exists() else None
        if current not in (old_hash, entry["newSha256"]):
            raise ValueError(f"card changed externally; manual resolution required: {target}")
    source_entry = journal.get("source")
    if source_entry:
        source_target = inside(root, source_entry["target"])
        source_current = digest(source_target) if source_target.exists() else None
        if source_current not in (source_entry["oldSha256"], source_entry["newSha256"]):
            raise ValueError("normalized source changed externally; manual resolution required")
    for filename, key, expected in (
        ("card-index.jsonl", "index.bin", journal["indexOldSha256"]),
        ("processing-log.jsonl", "log.bin", journal["logOldSha256"]),
    ):
        original = (backup / key).read_bytes()
        import hashlib
        if hashlib.sha256(original).hexdigest().upper() != expected:
            raise ValueError(f"rollback backup corrupt: {key}")
    for entry in journal["cards"]:
        target = inside(root, entry["target"])
        if entry.get("oldSha256") is None:
            target.unlink(missing_ok=True)
        else:
            original = inside(root, entry["backupPath"]).read_bytes()
            atomic_bytes(target, original)
    if source_entry:
        source_target = inside(root, source_entry["target"])
        if source_entry["oldSha256"] is None:
            source_target.unlink(missing_ok=True)
        else:
            atomic_bytes(source_target, (backup / "source.bin").read_bytes())
    records = workspace_path(root, "record_root")
    current_index = digest(records / "card-index.jsonl")
    if current_index not in (journal["indexOldSha256"], journal["indexNewSha256"]):
        raise ValueError("index changed externally; manual resolution required")
    original_log = (backup / "log.bin").read_bytes()
    live_log = (records / "processing-log.jsonl").read_bytes()
    if not live_log.startswith(original_log) or len(live_log[len(original_log):].splitlines()) > 1:
        raise ValueError("processing log changed externally; manual resolution required")
    atomic_bytes(records / "card-index.jsonl", (backup / "index.bin").read_bytes())
    atomic_bytes(records / "processing-log.jsonl", (backup / "log.bin").read_bytes())
    atomic_bytes(run_dir / "run.json", (backup / "run.bin").read_bytes())
    if journal.get("batchPath"):
        batch_target = inside(root, journal["batchPath"])
        atomic_bytes(batch_target, (backup / "batch.bin").read_bytes())
    journal["status"] = "rolled_back"
    journal["rolledBackAt"] = stamp()
    archived = run_dir / f"commit-journal-rolled-back-{datetime.now().astimezone().strftime('%Y%m%d%H%M%S%f')}.json"
    atomic_json(archived, journal)
    (run_dir / "commit-journal.json").unlink()
    os.replace(backup, run_dir / ("rollback-" + archived.stem.rsplit("-", 1)[-1]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--rollback", action="store_true")
    group.add_argument("--pause", action="store_true")
    group.add_argument("--resume", action="store_true")
    group.add_argument("--skip", action="store_true")
    group.add_argument("--fail", action="store_true", help="mark the current run failed without advancing the serial batch")
    group.add_argument("--finalize", action="store_true")
    group.add_argument("--suspend-paused", action="store_true", help="release the global lock while preserving a paused run")
    parser.add_argument("--restart-stage", choices=["transcription_normalization", "misconception_candidate_identification", "five_gate_judgment", "intra_document_deduplication", "global_deduplication_pre", "card_draft_generation", "oral_polish", "independent_review", "global_deduplication_final"], help="reset a paused run from a repairable stage")
    parser.add_argument("--reason")
    parser.add_argument("--failed-stage")
    parser.add_argument("--failure-artifact")
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    records = workspace_path(root, "record_root")
    active = records / "active-run.json"
    lock = records / "pipeline.lock"
    try:
        if not active.is_file() and not lock.is_file():
            print("NO_ACTIVE_RUN")
            return 0
        if not active.is_file() or not lock.is_file():
            raise ValueError("active-run and lock disagree; manual recovery required")
        info = read_json(active)
        if read_json(lock).get("runId") != info["runId"]:
            raise ValueError("lock belongs to a different run")
        run_dir = records / "runs" / info["runId"]
        run_path = run_dir / "run.json"
        run = read_json(run_path)
        journal_path = run_dir / "commit-journal.json"
        journal = read_json(journal_path) if journal_path.exists() else None
        if args.rollback:
            if not journal or journal.get("status") == "committed":
                raise ValueError("no interrupted commit to roll back")
            rollback(root, run_dir, journal)
            print(json.dumps({"runId": info["runId"], "status": "rolled_back", "lockRetained": True}, ensure_ascii=False))
            return 0
        if args.finalize:
            if not journal or journal.get("status") != "committed" or run.get("status") != "completed":
                raise ValueError("only a fully committed run with retained lock can be finalized")
            from validate_pipeline import load_jsonl, validate_record_v4
            errors: list[str] = []
            validate_record_v4(root, run, load_jsonl(records / "card-index.jsonl"), errors)
            if errors:
                raise ValueError("cannot finalize inconsistent run: " + "; ".join(errors))
            active.unlink(); lock.unlink()
            print(json.dumps({"runId": info["runId"], "status": "completed", "lockRetained": False}, ensure_ascii=False))
            return 0
        if args.suspend_paused:
            if run.get("status") != "paused":
                raise ValueError("suspend-paused requires a paused run")
            event = {"runId": run["runId"], "action": "suspend_paused_run", "reason": args.reason or "released lock to process an explicitly requested isolated rerun", "at": stamp()}
            event_path = records / "recovery-events.jsonl"
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            run["lockReleasedAt"] = event["at"]
            run["lockReleaseReason"] = event["reason"]
            atomic_json(run_path, run)
            active.unlink(); lock.unlink()
            print(json.dumps({"runId": run["runId"], "status": "paused", "lockRetained": False, "suspended": True}, ensure_ascii=False))
            return 0
        if args.restart_stage:
            if journal:
                raise ValueError("interrupted commit must be rolled back before restarting a stage")
            if run.get("status") != "paused":
                raise ValueError("restart-stage requires a paused run")
            stages = ["source_scan", "transcription_normalization", "misconception_candidate_identification", "five_gate_judgment", "intra_document_deduplication", "global_deduplication_pre", "card_draft_generation", "oral_polish", "independent_review", "global_deduplication_final", "formal_card_write", "index_update", "processing_log_write", "completion_validation"]
            restart_index = stages.index(args.restart_stage)
            discarded = [r.get("stage") for r in run.get("stageReceipts", [])[restart_index:]]
            if [r.get("stage") for r in run.get("stageReceipts", [])] != stages[:len(run.get("stageReceipts", []))]:
                raise ValueError("run stage receipts are not a valid prefix")
            if len(run.get("stageReceipts", [])) < restart_index:
                raise ValueError("requested restart stage has not been reached")
            event = {"runId": run["runId"], "action": "restart_stage", "stage": args.restart_stage, "discardedStages": discarded, "reason": args.reason or "controlled late-stage repair", "at": stamp()}
            event_path = records / "recovery-events.jsonl"
            with event_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            run["stageReceipts"] = run.get("stageReceipts", [])[:restart_index]
            run["status"] = "in_progress"
            run["restartedFromStage"] = args.restart_stage
            run["restartReason"] = event["reason"]
            atomic_json(run_path, run)
            print(json.dumps({"runId": info["runId"], "status": "in_progress", "restartStage": args.restart_stage, "discardedStages": discarded, "lockRetained": True}, ensure_ascii=False))
            return 0
        if journal and journal.get("status") not in ("rolled_back", "committed"):
            raise ValueError("interrupted commit must be rolled back before other recovery")
        if args.pause:
            run["status"] = "paused"; run["pauseReason"] = args.reason or "manual pause"; run["pausedAt"] = stamp()
            atomic_json(run_path, run)
        elif args.resume:
            if run["status"] != "paused":
                raise ValueError("only paused run can resume")
            run["status"] = "in_progress"; atomic_json(run_path, run)
        elif args.skip or args.fail:
            if not args.reason or not args.failed_stage or not args.failure_artifact:
                raise ValueError("skip/fail requires a failed stage, reason and failure artifact")
            if run["status"] not in ("in_progress", "paused") or journal:
                raise ValueError("cannot skip a run during/after commit")
            pipeline_stages = ["source_scan", "transcription_normalization", "misconception_candidate_identification", "five_gate_judgment", "intra_document_deduplication", "global_deduplication_pre", "card_draft_generation", "oral_polish", "independent_review", "global_deduplication_final", "formal_card_write", "index_update", "processing_log_write", "completion_validation"]
            stage_names = [r.get("stage") for r in run.get("stageReceipts", [])]
            if args.failed_stage not in pipeline_stages:
                raise ValueError("unknown failed stage")
            failed_index = pipeline_stages.index(args.failed_stage)
            if stage_names != pipeline_stages[:failed_index]:
                raise ValueError("skip stage does not match current run position")
            failure_path = run_file(root, info["runId"], args.failure_artifact)
            failure = read_json(failure_path)
            if failure.get("runId") != info["runId"] or failure.get("stage") != args.failed_stage or failure.get("reason") != args.reason:
                raise ValueError("failure report does not match current run")
            terminal_status = "skipped" if args.skip else "failed"
            run.update({"status": terminal_status, "failedStage": args.failed_stage, "error": args.reason,
                        "failureArtifactPath": args.failure_artifact, "failureArtifactSha256": digest(failure_path),
                        "processedAt": stamp(), "cardCount": 0, "cardPaths": []})
            atomic_json(run_path, run)
            with (records / "processing-log.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(run, ensure_ascii=False, separators=(",", ":")) + "\n")
                handle.flush(); os.fsync(handle.fileno())
            if args.skip and run.get("batchId"):
                batch_path = records / "batches" / f"{run['batchId']}.json"
                batch = read_json(batch_path)
                if batch.get("nextPosition") != run["sourceSequence"]:
                    raise ValueError("serial batch pointer changed before skip")
                batch["nextPosition"] = run["sourceSequence"] + 1
                atomic_json(batch_path, batch)
            active.unlink(); lock.unlink()
        result = {"runId": info["runId"], "sourcePath": info["sourcePath"], "status": run["status"],
                  "nextStageIndex": len(run.get("stageReceipts", [])), "lockRetained": lock.exists()}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
