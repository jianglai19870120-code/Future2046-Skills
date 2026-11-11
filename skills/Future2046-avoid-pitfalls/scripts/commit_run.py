#!/usr/bin/env python3
"""Recoverable, locked single-source commit. Never labels partial writes completed."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path

from pipeline_contract import check_stage, digest, inside, read_json, record_path, run_file, workspace_path

PRE = [
    "source_scan", "transcription_normalization", "misconception_candidate_identification",
    "five_gate_judgment", "intra_document_deduplication", "global_deduplication_pre",
    "card_draft_generation", "oral_polish", "independent_review",
    "global_deduplication_final",
]
POST = ["formal_card_write", "index_update", "processing_log_write", "completion_validation"]


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".v4-tmp")
    tmp.write_bytes(body)
    os.replace(tmp, path)


def atomic_json(path: Path, obj: dict) -> None:
    atomic_bytes(path, (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def receipt(stage: str, evidence: dict, previous: str) -> dict:
    started = datetime.now().astimezone()
    if previous:
        old = datetime.fromisoformat(previous)
        if started <= old:
            started = old + timedelta(microseconds=1)
    completed = started + timedelta(microseconds=1)
    return {"stage": stage, "status": "completed", "startedAt": started.isoformat(timespec="microseconds"),
            "completedAt": completed.isoformat(timespec="microseconds"), "evidence": evidence}


def card_fields(path: Path) -> tuple[dict, str]:
    body = path.read_text(encoding="utf-8")
    if not body.startswith("---\n") or "\n---\n" not in body[4:]:
        raise ValueError(f"missing YAML frontmatter: {path}")
    front, rest = body[4:].split("\n---\n", 1)
    fields: dict[str, object] = {}
    current = None
    for line in front.splitlines():
        if line.startswith("  - ") and current == "tags":
            fields["tags"].append(line[4:].strip().strip('"'))
        elif ":" in line:
            key, value = line.split(":", 1)
            current = key.strip()
            fields[current] = [] if current == "tags" else value.strip().strip('"')
    m = re.search(r"(?m)^# (.+)$", rest)
    if not m or any("## " + x not in rest for x in ("误区观点", "误区场景", "原文依据")):
        raise ValueError(f"card sections incomplete: {path}")
    return fields, m.group(1).strip()


def validate_pre(root: Path, run: dict, rows: list[dict]) -> tuple[list[tuple[Path, Path]], list[dict]]:
    records = workspace_path(root, "record_root")
    card_root = workspace_path(root, "card_root")
    receipts = run.get("stageReceipts", [])
    if run.get("pipelineVersion") != "v4-artifact" or run.get("status") != "in_progress":
        raise ValueError("only an active v4 run may commit")
    if [r.get("stage") for r in receipts] != PRE or any(r.get("status") != "completed" for r in receipts):
        raise ValueError("precommit stage order or status invalid")
    for marker in ("pipeline.lock", "active-run.json"):
        if read_json(records / marker).get("runId") != run["runId"]:
            raise ValueError("run does not hold exclusive lock")
    previous = None
    for item in receipts:
        path = run_file(root, run["runId"], item["evidence"]["artifactPath"])
        verified = check_stage(root, run, item["stage"], path, previous)
        if verified != item["evidence"]:
            raise ValueError(f"tampered receipt or artifact: {item['stage']}")
        previous = verified["outputSha256"]
    current_source_sha = digest(inside(root, run["sourcePath"]))
    allowed_source_shas = {
        receipts[0]["evidence"]["outputSha256"],
        receipts[1]["evidence"]["outputSha256"],
    }
    if current_source_sha not in allowed_source_shas:
        raise ValueError("source changed outside the recorded normalization result; restart run")
    review = read_json(run_file(root, run["runId"], receipts[8]["evidence"]["artifactPath"]))
    polish = read_json(run_file(root, run["runId"], receipts[7]["evidence"]["artifactPath"]))
    final_dedup = read_json(run_file(root, run["runId"], receipts[9]["evidence"]["artifactPath"]))
    if final_dedup["indexSha256"] != digest(records / "card-index.jsonl"):
        raise ValueError("index changed after final deduplication; redo final dedup")
    reviewed = {c.get("cardId"): c for c in review["cards"]}
    if set(reviewed) != {c.get("cardId") for c in polish["cards"]}:
        raise ValueError("review did not cover every polished card")
    if len(rows) != len(reviewed) or any(r.get("cardId") not in reviewed for r in rows):
        raise ValueError("index rows differ from reviewed cards")
    if len({r.get("cardId") for r in rows}) != len(rows) or len({r.get("cardPath") for r in rows}) != len(rows):
        raise ValueError("duplicate cardId or cardPath in proposed index")
    staging = records / "staging" / run["runId"] / "cards"
    existing = [json.loads(line) for line in (records / "card-index.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    old_by_id = {r.get("cardId"): r for r in existing if r.get("cardId")}
    old_by_path = {r.get("cardPath"): r for r in existing if r.get("cardPath")}
    targets = []
    for row in rows:
        rel = row["cardPath"]
        target = inside(root, rel)
        if not target.is_relative_to(card_root.resolve()) or target.parent != card_root.resolve():
            raise ValueError("formal card must be directly under card directory")
        staged = staging / target.name
        if digest(staged) != reviewed[row["cardId"]]["reviewedCardSha256"]:
            raise ValueError("staging changed after independent review")
        fields, title = card_fields(staged)
        if (fields.get("card_id"), fields.get("category"), fields.get("tags"), fields.get("source_address")) != (
            row.get("cardId"), row.get("category"), row.get("tags"), row.get("sourceAddress")):
            raise ValueError(f"card metadata disagrees with index: {rel}; fields={fields!r}; row={row!r}")
        if row.get("category") not in ("", "个人IP", "创业搞钱", "成长逆袭") or not 1 <= len(row.get("tags", [])) <= 3:
            raise ValueError(f"card category/tags invalid: {rel}")
        normalization = read_json(run_file(root, run["runId"], receipts[1]["evidence"]["artifactPath"]))
        normalized_source = normalization.get("normalizedSourcePath", run["sourcePath"])
        source = Path(normalized_source).stem
        if fields["source_address"] != normalized_source or target.name != f"{source}_{title}.md" or row.get("title") != title:
            raise ValueError(f"source/title/filename mismatch: {rel}")
        if target.exists() and (row["cardId"] not in old_by_id or old_by_id[row["cardId"]].get("cardPath") != rel):
            raise ValueError(f"target exists under another card identity: {rel}")
        if rel in old_by_path and old_by_path[rel].get("cardId") != row["cardId"]:
            raise ValueError(f"card path already indexed by another ID: {rel}")
        targets.append((staged, target))
    return targets, existing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--index-records", required=True,
                        help="当前 run submission/ 下的工作区相对 POSIX 路径")
    parser.add_argument("--overwrite-existing", action="store_true")
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    records = workspace_path(root, "record_root")
    run_dir = records / "runs" / args.run_id
    run_path = run_dir / "run.json"
    journal_path = run_dir / "commit-journal.json"
    try:
        if journal_path.exists():
            raise ValueError("unresolved commit journal; run recover_run.py --rollback first")
        run = read_json(run_path)
        index_records_path = record_path(root, args.index_records, run_id=args.run_id,
                                         subdirectory="submission")
        rows = json.loads(index_records_path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise ValueError("index records must be a JSON array")
        targets, existing = validate_pre(root, run, rows)
        if any(t.exists() for _, t in targets) and not args.overwrite_existing:
            raise ValueError("existing formal card requires --overwrite-existing")
        index_path = records / "card-index.jsonl"
        log_path = records / "processing-log.jsonl"
        replaced_ids = {r["cardId"] for r in rows}
        new_index = [r for r in existing if r.get("cardId") not in replaced_ids] + rows
        new_index_bytes = ("\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in new_index) + "\n").encode("utf-8")
        if len({r.get("cardId") for r in new_index if r.get("cardId")}) != len([r for r in new_index if r.get("cardId")]):
            raise ValueError("new index has duplicate card IDs")
        backup_dir = run_dir / "rollback"
        backup_dir.mkdir(parents=True, exist_ok=False)
        original = {"index": index_path.read_bytes(), "log": log_path.read_bytes(), "run": run_path.read_bytes()}
        batch_path = records / "batches" / f"{run['batchId']}.json" if run.get("batchId") else None
        if batch_path:
            original["batch"] = batch_path.read_bytes()
        for key, value in original.items():
            atomic_bytes(backup_dir / f"{key}.bin", value)
        card_entries = []
        for i, (staged, target) in enumerate(targets):
            old = target.read_bytes() if target.exists() else None
            if old is not None:
                atomic_bytes(backup_dir / f"card-{i}.bin", old)
                archive = workspace_path(root, "archive_root") / "重跑备份" / args.run_id / target.name
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, archive)
            card_entries.append({"target": target.relative_to(root).as_posix(), "newSha256": digest(staged),
                                 "oldSha256": digest(target) if old is not None else None,
                                 "backupPath": (backup_dir / f"card-{i}.bin").relative_to(root).as_posix() if old is not None else None})
        normalization = read_json(run_file(root, args.run_id, run["stageReceipts"][1]["evidence"]["artifactPath"]))
        corrected = run_file(root, args.run_id, normalization["correctedPath"])
        normalized_source = inside(root, normalization.get("normalizedSourcePath", run["sourcePath"]))
        source_entry = None
        if not normalized_source.exists() or digest(normalized_source) != digest(corrected):
            source_old = normalized_source.read_bytes() if normalized_source.exists() else None
            if source_old is not None:
                atomic_bytes(backup_dir / "source.bin", source_old)
            source_entry = {"target": normalized_source.relative_to(root).as_posix(),
                            "newSha256": digest(corrected),
                            "oldSha256": digest(normalized_source) if source_old is not None else None}
        import hashlib
        journal = {"runId": args.run_id, "status": "prepared", "cards": card_entries,
                   "indexOldSha256": digest(index_path), "indexNewSha256": hashlib.sha256(new_index_bytes).hexdigest().upper(),
                   "logOldSha256": digest(log_path), "batchPath": batch_path.relative_to(root).as_posix() if batch_path else None,
                   "source": source_entry}
        atomic_json(journal_path, journal)
        for staged, target in targets:
            atomic_bytes(target, staged.read_bytes())
        journal["status"] = "cards_written"; atomic_json(journal_path, journal)
        if source_entry:
            atomic_bytes(normalized_source, corrected.read_bytes())
        journal["status"] = "source_written"; atomic_json(journal_path, journal)
        atomic_bytes(index_path, new_index_bytes)
        journal["status"] = "index_written"; atomic_json(journal_path, journal)
        run["cardCount"] = len(rows)
        run["originalSha256"] = run["stageReceipts"][0]["evidence"]["outputSha256"]
        run["correctedSha256"] = run["stageReceipts"][1]["evidence"]["outputSha256"]
        run["cardPaths"] = [r["cardPath"] for r in rows]
        run["cardDetails"] = [{"cardId": r["cardId"], "category": r["category"], "tags": r["tags"], "sourceAddress": r["sourceAddress"]} for r in rows]
        review = read_json(run_file(root, args.run_id, run["stageReceipts"][8]["evidence"]["artifactPath"]))
        run.update({"reviewStatus": "approved", "reviewMode": review["reviewMode"], "reviewAttempts": review.get("reviewAttempts", 1), "oralPolishStatus": "completed"})
        prev = run["stageReceipts"][-1]["completedAt"]
        for stage, evidence in (
            ("formal_card_write", {"cards": card_entries}),
            ("index_update", {"indexSha256": digest(index_path)}),
            ("processing_log_write", {"logPreviousSha256": journal["logOldSha256"]}),
        ):
            item = receipt(stage, evidence, prev); run["stageReceipts"].append(item); prev = item["completedAt"]
        completion = {"result": "passed", "recoverableCommit": True, "indexSha256": digest(index_path),
                      "cardCount": len(rows), "reviewArtifactSha256": run["stageReceipts"][8]["evidence"]["artifactSha256"]}
        item = receipt("completion_validation", completion, prev); run["stageReceipts"].append(item)
        run["status"] = "completed"; run["processedAt"] = stamp(); run["fullRun"] = True
        from validate_pipeline import validate_record_v4
        errors: list[str] = []
        validate_record_v4(root, run, new_index, errors, allow_pending=True)
        if errors:
            raise ValueError("postcommit validation failed: " + "; ".join(errors))
        atomic_json(run_path, run)
        with log_path.open("ab") as handle:
            handle.write((json.dumps(run, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8"))
            handle.flush(); os.fsync(handle.fileno())
        journal["status"] = "log_written"; atomic_json(journal_path, journal)
        errors = []
        validate_record_v4(root, run, new_index, errors, allow_pending=True)
        if errors:
            raise ValueError("completion record validation failed: " + "; ".join(errors))
        if read_json(run_path) != run or json.loads([x for x in log_path.read_text(encoding="utf-8").splitlines() if x.strip()][-1]) != run:
            raise ValueError("run and processing log differ after write")
        if batch_path:
            batch = read_json(batch_path)
            if batch.get("nextPosition") != run["sourceSequence"]:
                raise ValueError("serial batch pointer changed during commit")
            batch["nextPosition"] = run["sourceSequence"] + 1
            atomic_json(batch_path, batch)
        journal["status"] = "committed"; atomic_json(journal_path, journal)
        (records / "active-run.json").unlink()
        (records / "pipeline.lock").unlink()
        print(json.dumps({"runId": args.run_id, "status": "completed", "cardCount": len(rows)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}; retain lock and journal for recovery", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
