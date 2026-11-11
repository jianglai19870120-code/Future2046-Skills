#!/usr/bin/env python3
"""Build a stable source queue and select the next unfinished source."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from pipeline_contract import workspace_path, workspace_rel_path

SOURCE_SUFFIXES = {".md", ".txt", ".docx", ".pdf"}
TERMINAL = {"completed", "skipped", "failed"}


def is_source_instruction(path: Path) -> bool:
    """Ignore workspace guidance files; template files use a non-source suffix."""
    return path.name.casefold() == "readme.md"


def natural_path_key(path: Path) -> tuple[str, ...]:
    """Sort source names with numeric suffixes in human order."""
    value = path.as_posix().casefold()
    return tuple(
        f"1{int(token):020d}" if token.isdigit() else f"0{token}"
        for token in re.split(r"(\d+)", value) if token
    )


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def latest_logs(records: Path) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in load_jsonl(records / "processing-log.jsonl"):
        source = row.get("sourcePath")
        if isinstance(source, str) and source and not source.startswith("__"):
            latest[source.replace("\\", "/")] = row
    return latest


def load_previous_queue(records: Path) -> dict[str, dict]:
    path = records / "source-queue.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {item["sourcePath"]: item for item in data.get("sources", []) if isinstance(item, dict) and item.get("sourcePath")}


def source_kind(path: Path) -> str:
    if path.suffix.lower() == ".md":
        try:
            text = path.read_text(encoding="utf-8")
            if "source_type: \"excel_row\"" in text[:4000]:
                return "excel_row"
        except (OSError, UnicodeError):
            pass
    return "file"


def build_queue(workspace: Path) -> dict:
    source_root = workspace_path(workspace, "source_root")
    records = workspace_path(workspace, "record_root")
    logs = latest_logs(records)
    previous = load_previous_queue(records)
    paths = sorted(
        p for p in source_root.rglob("*")
        if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES and not is_source_instruction(p)
    )
    paths.sort(key=lambda path: natural_path_key(path.relative_to(workspace)))
    known_positions = {
        item["sourcePath"]: item["queuePosition"]
        for item in previous.values()
        if isinstance(item.get("queuePosition"), int)
    }
    for source, row in logs.items():
        position = row.get("queuePosition", row.get("sourceSequence"))
        if isinstance(position, int):
            known_positions[source] = position
    next_position = max(known_positions.values(), default=0) + 1
    sources = []
    for path in paths:
        rel = path.relative_to(workspace).as_posix()
        if rel not in known_positions:
            known_positions[rel] = next_position
            next_position += 1
        row = logs.get(rel, {})
        status = row.get("status", "new")
        sources.append({
            "sourcePath": rel,
            "sourceKind": source_kind(path),
            "queuePosition": known_positions[rel],
            "status": status,
            "terminal": status in TERMINAL,
            "runId": row.get("runId"),
        })
    sources.sort(key=lambda item: (item["queuePosition"], item["sourcePath"]))
    next_source = next((item for item in sources if not item["terminal"]), None)
    return {"schemaVersion": 1, "updatedAt": stamp(), "nextSource": next_source, "sources": sources}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build a stable queue for source documents.")
    parser.add_argument("command", choices=["scan", "next"])
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--write", action="store_true", help="persist source-queue.json")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    records = workspace_path(workspace, "record_root")
    queue = build_queue(workspace)
    if args.write:
        records.mkdir(parents=True, exist_ok=True)
        path = records / "source-queue.json"
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    if args.command == "next":
        print(json.dumps(queue["nextSource"], ensure_ascii=False))
    else:
        queue_path = records / "source-queue.json" if args.write else None
        print(json.dumps({"sourceCount": len(queue["sources"]), "nextSource": queue["nextSource"], "queuePath": workspace_rel_path(workspace, queue_path) if queue_path else None}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
