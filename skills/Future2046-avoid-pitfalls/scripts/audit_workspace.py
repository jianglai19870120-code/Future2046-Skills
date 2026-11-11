#!/usr/bin/env python3
"""Audit historical cards and source coverage without changing formal assets."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from pipeline_contract import workspace_path

SOURCE_SUFFIXES = {".md", ".txt", ".docx", ".pdf"}


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        rows.append(value)
    return rows


def source_files(root: Path) -> list[Path]:
    source_root = workspace_path(root, "source_root")
    return sorted(
        (
            p
            for p in source_root.rglob("*")
            if p.is_file()
            and p.suffix.lower() in SOURCE_SUFFIXES
            and p.name.casefold() != "readme.md"
        ),
        key=lambda p: p.relative_to(root).as_posix().casefold(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit historical misconception cards and source coverage.")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.workspace).resolve()
    records = workspace_path(root, "record_root")
    index_path = records / "card-index.jsonl"
    processing_path = records / "processing-log.jsonl"
    index_rows = read_jsonl(index_path)
    card_rows = [row for row in index_rows if row.get("cardId")]
    sources = source_files(root)
    source_rel = {p.relative_to(root).as_posix() for p in sources}
    cards_by_source: dict[str, list[dict]] = {}
    for row in card_rows:
        source = row.get("sourceAddress", "")
        cards_by_source.setdefault(source, []).append(row)

    processing_rows = read_jsonl(processing_path)
    v4_rows = [row for row in processing_rows if row.get("pipelineVersion") == "v4-artifact"]
    run_root = records / "runs"
    v4_runs_available = run_root.is_dir() and any(run_root.iterdir())
    entries = []
    for path in sources:
        rel = path.relative_to(root).as_posix()
        cards = cards_by_source.get(rel, [])
        card_details = []
        mismatch = False
        for card in cards:
            card_path = root / card.get("cardPath", "")
            exists = card_path.is_file()
            source_matches = card.get("sourceAddress") == rel
            mismatch = mismatch or not exists or not source_matches
            card_details.append({
                "cardId": card.get("cardId"),
                "cardPath": card.get("cardPath"),
                "exists": exists,
                "sourceAddressMatches": source_matches,
                "category": card.get("category", ""),
                "tags": card.get("tags", []),
                "status": card.get("status"),
            })
        if mismatch:
            status = "card_source_mismatch"
        elif cards:
            status = "legacy_card_unverified"
        else:
            status = "no_card_unknown"
        entries.append({
            "sourcePath": rel,
            "sourceKind": "excel_row" if "source_type: \"excel_row\"" in path.read_text(encoding="utf-8", errors="ignore")[:4000] else "file",
            "sourceExists": True,
            "legacyCardCount": len(cards),
            "legacyCards": card_details,
            "v4EvidenceAvailable": any(row.get("sourcePath") == rel for row in v4_rows),
            "status": status,
        })

    missing_index_sources = sorted(set(cards_by_source) - source_rel)
    for source in missing_index_sources:
        entries.append({
            "sourcePath": source,
            "sourceKind": "unknown",
            "sourceExists": False,
            "legacyCardCount": len(cards_by_source[source]),
            "legacyCards": cards_by_source[source],
            "v4EvidenceAvailable": False,
            "status": "source_missing",
        })

    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "workspace": str(root),
        "sourceCount": len(sources),
        "formalCardCount": len(card_rows),
        "sourcesWithCards": len({row["sourcePath"] for row in entries if row["legacyCardCount"]}),
        "sourcesWithoutCards": sum(1 for row in entries if row["legacyCardCount"] == 0),
        "processingLogAvailable": bool(processing_rows),
        "v4RunsAvailable": v4_runs_available,
        "v4RecordCount": len(v4_rows),
        "indexStructurallyValid": len({row.get("cardId") for row in card_rows}) == len(card_rows)
        and all((root / row.get("cardPath", "")).is_file() for row in card_rows),
        "fullRunValidation": bool(v4_rows) and len(v4_rows) >= len(sources),
        "statusCounts": dict(Counter(row["status"] for row in entries)),
        "entries": entries,
    }
    output = Path(args.output).resolve() if args.output else records / "historical-audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "sourceCount", "formalCardCount", "sourcesWithCards", "sourcesWithoutCards",
        "processingLogAvailable", "v4RunsAvailable", "indexStructurallyValid",
        "fullRunValidation", "statusCounts",
    )}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
