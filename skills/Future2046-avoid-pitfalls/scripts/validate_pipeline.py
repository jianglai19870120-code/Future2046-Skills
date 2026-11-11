#!/usr/bin/env python3
"""Validate extract-misconceptions hard-gate receipts and current card/index state."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from pipeline_contract import check_stage, digest, run_file, workspace_path


STAGES = [
    "source_scan",
    "transcription_normalization",
    "misconception_candidate_identification",
    "five_gate_judgment",
    "intra_document_deduplication",
    "global_deduplication_pre",
    "card_draft_generation",
    "oral_polish",
    "independent_review",
    "global_deduplication_final",
    "formal_card_write",
    "index_update",
    "processing_log_write",
    "completion_validation",
]
ALLOWED_TERMINAL = {"completed", "skipped", "failed", "paused"}
ALLOWED_CATEGORIES = {"", "个人IP", "创业搞钱", "成长逆袭"}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSON: {exc}") from exc
    return rows


def artifact_hash(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        digest.update(path.read_bytes())
    elif path.is_dir():
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            digest.update(item.relative_to(path).as_posix().encode("utf-8")); digest.update(item.read_bytes())
    else:
        raise FileNotFoundError(path)
    return digest.hexdigest().upper()


def latest_for_source(rows: list[dict], source: str) -> dict | None:
    matches = [row for row in rows if row.get("sourcePath", "").replace("\\", "/") == source]
    return matches[-1] if matches else None


def card_metadata(card_path: Path) -> tuple[dict, str]:
    text = card_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("missing YAML frontmatter")
    end = text.find("\n---", 3)
    if end < 0:
        raise ValueError("unterminated YAML frontmatter")
    front = text[4:end].splitlines()
    metadata: dict = {}
    current_list = None
    for line in front:
        if re.match(r"^\s+-\s+", line) and current_list:
            metadata[current_list].append(line.split("-", 1)[1].strip().strip('"'))
        elif ":" in line:
            key, raw_value = line.split(":", 1)
            key, raw_value = key.strip(), raw_value.strip()
            if raw_value in {'""', "''"}:
                metadata[key] = ""
                current_list = None
                continue
            value = raw_value.strip('"')
            if value:
                metadata[key] = value
                current_list = None
            else:
                metadata[key] = []
                current_list = key
    return metadata, text


def validate_card(workspace: Path, row: dict, index_by_id: dict, errors: list[str]) -> None:
    card_id = row.get("cardId")
    card_path_value = row.get("cardPath", "")
    card_path = workspace / Path(card_path_value.replace("/", "\\"))
    if not card_id or not card_path_value:
        fail("index record missing cardId/cardPath", errors)
        return
    if not card_path.exists():
        fail(f"{card_id}: card path does not exist: {card_path_value}", errors)
        return
    try:
        metadata, text = card_metadata(card_path)
    except ValueError as exc:
        fail(f"{card_id}: {exc}", errors)
        return
    for key in ("card_id", "category", "tags", "source_address"):
        if key not in metadata:
            fail(f"{card_id}: missing frontmatter field {key}", errors)
    if metadata.get("card_id") != card_id:
        fail(f"{card_id}: frontmatter card_id mismatch", errors)
    if metadata.get("category") not in ALLOWED_CATEGORIES:
        fail(f"{card_id}: invalid category", errors)
    if not isinstance(metadata.get("tags"), list) or not 1 <= len(metadata["tags"]) <= 3:
        fail(f"{card_id}: tags must contain 1-3 items", errors)
    title_match = re.search(r"(?m)^# (.+)$", text)
    if not title_match:
        fail(f"{card_id}: missing H1", errors)
    else:
        title = title_match.group(1).strip()
        if row.get("title") != title:
            fail(f"{card_id}: index title and H1 mismatch", errors)
        expected_prefix = Path(metadata.get("source_address", "")).stem + "_"
        if not card_path.name.startswith(expected_prefix):
            fail(f"{card_id}: filename does not start with source filename", errors)
        if not card_path.name.endswith(f"_{title}.md"):
            fail(f"{card_id}: filename title mismatch", errors)
    for heading in ("## 误区观点", "## 误区场景", "## 原文依据"):
        if heading not in text:
            fail(f"{card_id}: missing section {heading}", errors)
    viewpoint_match = re.search(r"(?ms)^## 误区观点\s*\n(.*?)\n## 误区场景", text)
    if not viewpoint_match:
        fail(f"{card_id}: viewpoint section cannot be parsed", errors)
    else:
        viewpoint = viewpoint_match.group(1).strip()
        if viewpoint != row.get("viewpoint") or len(re.findall(r"[\u4e00-\u9fff]", viewpoint)) > 24 or "\n" in viewpoint:
            fail(f"{card_id}: viewpoint/index mismatch or exceeds 24 Chinese characters", errors)
    if metadata.get("source_address") != row.get("sourceAddress"):
        fail(f"{card_id}: source_address differs from index", errors)


def validate_record(workspace: Path, record: dict, index_rows: list[dict], errors: list[str], require_full_run: bool = False) -> None:
    if record.get("pipelineVersion") == "v4-artifact":
        if record.get("status") == "skipped":
            validate_skipped_v4(workspace, record, errors)
            return
        validate_record_v4(workspace, record, index_rows, errors)
        return
    fail(f"{record.get('sourcePath')}: record is not a v4-artifact run", errors)


def validate_skipped_v4(workspace: Path, record: dict, errors: list[str]) -> None:
    source = record.get("sourcePath", "")
    stage = record.get("failedStage")
    # A skipped run may stop at any pipeline stage. Its receipts must be the
    # exact prefix before that failed stage, rather than a hard-coded subset.
    # This keeps formal-card-write, index-update, and completion-validation
    # failures auditable as well.
    expected = STAGES[:STAGES.index(stage)] if stage in STAGES else None
    if expected is None or [r.get("stage") for r in record.get("stageReceipts", [])] != expected:
        fail(f"{source}: invalid skipped stage position", errors)
    if record.get("cardCount") != 0 or record.get("cardPaths") != [] or not record.get("error"):
        fail(f"{source}: skipped run lacks specific zero-card failure", errors)
    try:
        artifact = run_file(workspace, record["runId"], record["failureArtifactPath"])
        if digest(artifact) != record.get("failureArtifactSha256"):
            fail(f"{source}: failure artifact changed", errors)
        report = json.loads(artifact.read_text(encoding="utf-8"))
        if report.get("stage") != stage or report.get("reason") != record.get("error"):
            fail(f"{source}: failure report differs from skipped record", errors)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        fail(f"{source}: failure artifact invalid: {exc}", errors)


def validate_record_v4(workspace: Path, record: dict, index_rows: list[dict], errors: list[str], allow_pending: bool = False) -> None:
    source = record.get("sourcePath", "")
    run_id = record.get("runId", "")
    receipts = record.get("stageReceipts", [])
    if record.get("pipelineVersion") != "v4-artifact" or record.get("status") != "completed" or record.get("fullRun") is not True:
        fail(f"{source}: not a completed v4 run", errors)
        return
    if not isinstance(receipts, list) or [r.get("stage") for r in receipts] != STAGES:
        fail(f"{source}: incomplete or unordered v4 stage chain", errors)
        return
    journal: dict = {}
    records = workspace_path(workspace, "record_root")
    journal_path = records / "runs" / run_id / "commit-journal.json"
    try:
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        valid_journal_states = ("index_written", "log_written", "committed") if allow_pending else ("committed",)
        if journal.get("status") not in valid_journal_states or journal.get("runId") != run_id:
            fail(f"{source}: commit journal is not in validated or committed state", errors)
    except (OSError, ValueError) as exc:
        fail(f"{source}: commit journal missing or invalid: {exc}", errors)
    previous = None
    for r in receipts[:10]:
        try:
            verified = check_stage(workspace, record, r["stage"], run_file(workspace, run_id, r["evidence"]["artifactPath"]), previous)
            if verified != r["evidence"] or r.get("status") != "completed":
                fail(f"{source}: evidence mismatch at {r['stage']}", errors)
            previous = verified["outputSha256"]
        except (ValueError, OSError, KeyError, TypeError) as exc:
            fail(f"{source}: invalid {r.get('stage')} artifact: {exc}", errors)
    times = [r.get("completedAt", "") for r in receipts]
    if any(not times[i] or times[i] >= times[i + 1] for i in range(len(times)-1)):
        fail(f"{source}: stage times not strictly increasing", errors)
    if receipts[-1].get("evidence", {}).get("result") != "passed" or not receipts[-1].get("evidence", {}).get("recoverableCommit"):
        fail(f"{source}: completion validation absent", errors)
    if receipts[10].get("evidence", {}).get("cards") != journal.get("cards"):
        fail(f"{source}: formal write receipt disagrees with journal", errors)
    if receipts[11].get("evidence", {}).get("indexSha256") != journal.get("indexNewSha256"):
        fail(f"{source}: index update receipt disagrees with journal", errors)
    if receipts[12].get("evidence", {}).get("logPreviousSha256") != journal.get("logOldSha256"):
        fail(f"{source}: log receipt disagrees with journal", errors)
    if receipts[13].get("evidence", {}).get("reviewArtifactSha256") != receipts[8].get("evidence", {}).get("artifactSha256"):
        fail(f"{source}: completion is bound to another review", errors)
    source_entry = journal.get("source")
    if source_entry:
        try:
            if digest(workspace / source_entry["target"]) != source_entry["newSha256"]:
                fail(f"{source}: normalized source differs from committed version", errors)
        except (OSError, ValueError) as exc:
            fail(f"{source}: normalized source missing: {exc}", errors)
    if record.get("cardCount") != len(record.get("cardPaths", [])):
        fail(f"{source}: card count and paths differ", errors)
    index_by_path = {r.get("cardPath"): r for r in index_rows if r.get("cardPath")}
    try:
        review = json.loads(run_file(workspace, run_id, receipts[8]["evidence"]["artifactPath"]).read_text(encoding="utf-8"))
        reviewed = {c.get("cardId"): c["reviewedCardSha256"] for c in review["cards"]}
        if len(reviewed) != record.get("cardCount"):
            fail(f"{source}: review coverage differs from committed card count", errors)
        for path in record.get("cardPaths", []):
            row = index_by_path.get(path)
            if not row:
                fail(f"{source}: card missing from index: {path}", errors)
                continue
            validate_card(workspace, row, {}, errors)
            card = workspace / path
            if digest(card) != reviewed.get(row.get("cardId")):
                fail(f"{source}: formal card differs from reviewed version: {path}", errors)
        if not allow_pending:
            run_copy = json.loads((records / "runs" / run_id / "run.json").read_text(encoding="utf-8"))
            if run_copy != record:
                fail(f"{source}: run.json differs from completed record", errors)
            logs = load_jsonl(records / "processing-log.jsonl")
            if not any(row == record for row in logs):
                fail(f"{source}: completed record absent from processing log", errors)
        if receipts[-1]["evidence"].get("indexSha256") != journal.get("indexNewSha256"):
            fail(f"{source}: index differs from committed snapshot", errors)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        fail(f"{source}: final review/index validation failed: {exc}", errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--source")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--require-full-run", action="store_true", help="require a verified v4-artifact run")
    args = parser.parse_args()
    if bool(args.source) == bool(args.all):
        parser.error("provide exactly one of --source or --all")
    workspace = Path(args.workspace)
    records = workspace_path(workspace, "record_root")
    log_path = records / "processing-log.jsonl"
    index_path = records / "card-index.jsonl"
    errors: list[str] = []
    try:
        logs = load_jsonl(log_path)
        index_rows = load_jsonl(index_path)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1
    index_rows = [row for row in index_rows if row.get("recordType") != "indexMeta"]
    ids = [row.get("cardId") for row in index_rows]
    if len(ids) != len(set(ids)):
        fail("card-index.jsonl contains duplicate cardId", errors)
    if args.require_full_run:
        indexed_paths = {row.get("cardPath") for row in index_rows if row.get("cardPath")}
        actual_paths = {
            p.relative_to(workspace).as_posix()
            for p in workspace_path(workspace, "card_root").glob("*.md")
            if p.name.casefold() != "readme.md"
        }
        for orphan in sorted(actual_paths - indexed_paths):
            fail(f"formal card is not indexed: {orphan}", errors)
    if args.source:
        source = args.source.replace("\\", "/")
        record = latest_for_source(logs, source)
        if not record:
            fail(f"no processing record for {source}", errors)
        else:
            validate_record(workspace, record, index_rows, errors, args.require_full_run)
    else:
        sources = sorted({row.get("sourcePath") for row in logs if row.get("sourcePath", "").lower().endswith(".md") and not row.get("sourcePath", "").startswith("__")})
        if args.require_full_run and not sources:
            fail("no real v4-artifact source records found; historical rebuild records are not a full run", errors)
        if args.require_full_run:
            source_root = workspace_path(workspace, "source_root")
            expected = {
                p.relative_to(workspace).as_posix()
                for p in source_root.rglob("*.md")
                if p.name.casefold() != "readme.md"
            }
            missing_sources = sorted(expected - set(sources))
            for missing in missing_sources:
                fail(f"source has no processing record: {missing}", errors)
        for source in sources:
            record = latest_for_source(logs, source)
            validate_record(workspace, record, index_rows, errors, args.require_full_run)
        if args.require_full_run:
            serial = sorted((latest_for_source(logs, source) for source in sources), key=lambda r: r.get("queuePosition", r.get("sourceSequence", 10**9)))
            for previous, current in zip(serial, serial[1:]):
                previous_position = previous.get("queuePosition", previous.get("sourceSequence"))
                current_position = current.get("queuePosition", current.get("sourceSequence"))
                if not isinstance(current_position, int) or not isinstance(previous_position, int):
                    continue
                if current_position != previous_position + 1:
                    fail(f"serial queue gap between {previous.get('sourcePath')} and {current.get('sourcePath')}", errors)
                if previous.get("status") not in ALLOWED_TERMINAL:
                    fail(f"{current.get('sourcePath')}: previous source has no terminal state", errors)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
