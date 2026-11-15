#!/usr/bin/env python3
"""One-card-at-a-time migration for historical misconception viewpoints.

The controller never generates viewpoints itself and never prepares multiple
cards.  A caller supplies one reviewed semantic map and canonical viewpoint;
the controller verifies preservation, commits one card, and advances progress.
"""
from __future__ import annotations

import os
import sys
if os.environ.get("FUTURE2046_PYCACHE_PREFIX"):
    sys.pycache_prefix = os.environ["FUTURE2046_PYCACHE_PREFIX"]
else:
    sys.dont_write_bytecode = True

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from card_migration_format import FOOTER, INVALID_FILENAME, field, read_index, render, split_sections
from pipeline_contract import workspace_layout

CONTRACT = "golden-sentence-migration-v2"
MAP_KEYS = ("primaryObject", "wrongBehavior", "keyCondition", "problemResult", "correctionDirection")


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="microseconds")


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def normalized_text(raw: bytes) -> str:
    return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def preferred_newline(raw: bytes) -> str:
    return "\r\n" if b"\r\n" in raw else "\n"


def paths(root: Path, migration_dir: str | None) -> tuple[Path, Path, Path, Path]:
    layout = workspace_layout(root)
    records = root / layout["record_root"]
    migration = (root / migration_dir).resolve() if migration_dir else records / "migrations" / "golden-sentence-migration-v2-20261111"
    if not migration.is_relative_to(records.resolve()):
        raise ValueError("migration directory must stay inside record_root")
    return root / layout["card_root"], records / "card-index.jsonl", migration, records / "active-card-migration.json"


def lock_path(migration: Path) -> Path:
    return migration / "single-card.lock"


def progress_path(migration: Path) -> Path:
    return migration / "progress.json"


def read_rows(index_path: Path) -> tuple[list[dict], dict[str, dict]]:
    meta, rows = read_index(index_path)
    return meta, rows


def load_progress(migration: Path) -> dict:
    path = progress_path(migration)
    if not path.exists():
        return {"contract": CONTRACT, "status": "ready", "total": 0, "committed": 0, "currentCardId": None, "completedCardIds": [], "updatedAt": stamp()}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def card_ids_in_order(index_path: Path) -> list[str]:
    result = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("recordType") != "indexMeta" and row.get("cardId"):
            result.append(row["cardId"])
    return result


def next_card(root: Path, card_root: Path, index_path: Path, progress: dict) -> tuple[str, Path, dict]:
    _, rows = read_rows(index_path)
    completed = set(progress.get("completedCardIds", []))
    for card_id in card_ids_in_order(index_path):
        if card_id in completed:
            continue
        row = rows[card_id]
        path = root / row["cardPath"]
        if not path.is_file() or path.parent.resolve() != card_root.resolve():
            raise RuntimeError(f"card path missing or outside card_root: {card_id}")
        return card_id, path, row
    raise RuntimeError("all cards already migrated")


def validate_candidate(candidate: dict, old_text: str, row: dict) -> str:
    viewpoint = str(candidate.get("canonicalViewpoint", "")).strip()
    if not viewpoint or "\n" in viewpoint or len(re.findall(r"[\u4e00-\u9fff]", viewpoint)) > 24 or INVALID_FILENAME.search(viewpoint):
        raise ValueError("canonicalViewpoint is empty, too long, or invalid for a filename")
    semantic = candidate.get("sceneSemanticMap")
    if not isinstance(semantic, dict) or any(not str(semantic.get(key, "")).strip() for key in MAP_KEYS):
        raise ValueError("sceneSemanticMap must contain all five non-empty semantic fields")
    quality = candidate.get("viewpointQuality") or {}
    required_true = ("coversPrimaryObject", "preservesSceneTarget", "isNotMechanismOnly", "isNotFragmentSummary")
    if any(quality.get(key) is not True for key in required_true) or quality.get("semanticDrift") is not False:
        raise ValueError("viewpointQuality semantic coverage gate failed")
    review = candidate.get("review")
    if not isinstance(review, dict) or review.get("decision") != "approved" or not review.get("reviewerId") or not review.get("reason"):
        raise ValueError("independent review approval is required")
    front, _before, old_title, old_viewpoint, tail = split_sections(old_text)
    if candidate.get("oldViewpoint") != old_viewpoint or candidate.get("cardId") != field(front, "card_id") or row.get("title") != old_title:
        raise ValueError("candidate does not match the current card snapshot")
    if not tail:
        raise ValueError("scene/evidence content is missing")
    return viewpoint


def init_card(root: Path, migration: Path) -> None:
    card_root, index_path, migration, active = paths(root, str(migration))
    if active.exists():
        raise RuntimeError("a historical card migration is already active; commit or recover it first")
    migration.mkdir(parents=True, exist_ok=True)
    progress = load_progress(migration)
    if progress.get("status") == "paused":
        raise RuntimeError("migration is paused; recover or explicitly resume before init")
    ids = card_ids_in_order(index_path)
    if progress.get("total") not in (0, len(ids)):
        raise RuntimeError("progress total differs from current index")
    progress.update({"contract": CONTRACT, "total": len(ids), "updatedAt": stamp()})
    card_id, card_path, row = next_card(root, card_root, index_path, progress)
    migration_card = migration / "cards" / card_id
    if migration_card.exists():
        raise RuntimeError(f"staging for current card already exists: {card_id}")
    migration_card.mkdir(parents=True)
    original = card_path.read_bytes()
    normalized = normalized_text(original)
    snapshot = {
        "contract": CONTRACT,
        "cardId": card_id,
        "oldPath": row["cardPath"],
        "oldViewpoint": row["viewpoint"],
        "sourceAddress": row["sourceAddress"],
        "oldSha256": sha_bytes(original),
        "sceneEvidenceSha256": sha_bytes(split_sections(normalized)[4].encode("utf-8")),
        "newline": preferred_newline(original),
        "indexRow": row,
        "createdAt": stamp(),
        "status": "awaiting_generation"
    }
    (migration_card / "card.snapshot.md").write_bytes(original)
    write_json(migration_card / "snapshot.json", snapshot)
    write_json(active, {"contract": CONTRACT, "cardId": card_id, "migrationDir": str(migration), "startedAt": snapshot["createdAt"]})
    write_json(progress_path(migration), {**progress, "status": "in_progress", "currentCardId": card_id, "updatedAt": stamp()})
    lock_path(migration).write_text(json.dumps({"cardId": card_id, "createdAt": stamp()}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "awaiting_generation", "cardId": card_id, "cardPath": row["cardPath"], "migrationCard": str(migration_card)}, ensure_ascii=False))


def commit_card(root: Path, migration: Path, candidate_path: Path) -> None:
    card_root, index_path, migration, active = paths(root, str(migration))
    progress = load_progress(migration)
    card_id = progress.get("currentCardId")
    if progress.get("status") != "in_progress" or not card_id or not active.exists() or not lock_path(migration).exists():
        raise RuntimeError("no active single-card migration")
    migration_card = migration / "cards" / card_id
    snapshot = json.loads((migration_card / "snapshot.json").read_text(encoding="utf-8"))
    old_path = root / snapshot["oldPath"]
    old_raw = old_path.read_bytes()
    old_text = normalized_text(old_raw)
    if sha(old_path) != snapshot["oldSha256"]:
        raise RuntimeError("current formal card changed after snapshot; refusing to overwrite")
    _, rows = read_rows(index_path)
    row = rows[card_id]
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    viewpoint = validate_candidate(candidate, old_text, row)
    new_name = f"{Path(snapshot['sourceAddress'].replace('\\', '/')).stem}_{viewpoint}.md"
    new_path = card_root / new_name
    if new_path.exists() and new_path.resolve() != old_path.resolve():
        raise RuntimeError(f"target filename already exists: {new_name}")
    for other_id, other in rows.items():
        if other_id != card_id and other.get("viewpoint") == viewpoint:
            raise RuntimeError(f"duplicate canonical viewpoint already indexed: {other_id}")
    staged = migration_card / new_name
    rendered = render(old_text, viewpoint)
    if sha_bytes(split_sections(rendered)[4].encode("utf-8")) != snapshot["sceneEvidenceSha256"]:
        raise RuntimeError("scene/evidence changed during rendering")
    rendered_bytes = rendered.replace("\n", snapshot.get("newline", "\n")).encode("utf-8")
    staged.write_bytes(rendered_bytes)
    rendered_check = normalized_text(rendered_bytes)
    if not rendered_check.rstrip("\n").endswith(FOOTER) or rendered_check.count(FOOTER) != 1:
        raise RuntimeError("staged card footer missing or duplicated")
    row_new = dict(row)
    row_new.update({"title": viewpoint, "viewpoint": viewpoint, "cardPath": f"{card_root.name}/{new_name}"})
    backup = migration / "backups" / card_id / old_path.name
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(old_path, backup)
    journal = {"contract": CONTRACT, "cardId": card_id, "oldPath": snapshot["oldPath"], "newPath": row_new["cardPath"], "status": "prepared", "oldSha256": snapshot["oldSha256"], "newSha256": sha(staged), "backupPath": str(backup.relative_to(root)), "committedAt": None}
    write_json(migration_card / "journal.json", journal)
    index_lines = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        index_lines.append(json.dumps(row_new if item.get("cardId") == card_id else item, ensure_ascii=False))
    temp_index = migration_card / "card-index.jsonl.tmp"
    temp_index.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    if new_path.resolve() != old_path.resolve():
        old_path.unlink()
    os.replace(staged, new_path)
    os.replace(temp_index, index_path)
    journal.update({"status": "committed", "committedAt": stamp()})
    write_json(migration_card / "journal.json", journal)
    write_json(migration_card / "review.json", {
        "contract": CONTRACT,
        "cardId": card_id,
        "oldViewpoint": candidate["oldViewpoint"],
        "canonicalViewpoint": viewpoint,
        "sceneSemanticMap": candidate["sceneSemanticMap"],
        "viewpointQuality": candidate["viewpointQuality"],
        "review": candidate["review"],
        "status": "committed",
        "committedAt": journal["committedAt"]
    })
    completed = list(progress.get("completedCardIds", [])) + [card_id]
    next_id = None
    ids = card_ids_in_order(index_path)
    for item in ids:
        if item not in completed:
            next_id = item
            break
    write_json(progress_path(migration), {**progress, "status": "ready" if next_id else "completed", "committed": len(completed), "completedCardIds": completed, "currentCardId": None, "nextCardId": next_id, "updatedAt": stamp()})
    active.unlink(missing_ok=True)
    lock_path(migration).unlink(missing_ok=True)
    print(json.dumps({"status": "committed", "cardId": card_id, "newPath": row_new["cardPath"], "committed": len(completed), "nextCardId": next_id}, ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("init", "commit"))
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--migration-dir")
    ap.add_argument("--candidate-json")
    args = ap.parse_args()
    root = Path(args.workspace).resolve()
    if args.command == "init":
        _, _, migration, _ = paths(root, args.migration_dir)
        init_card(root, migration)
    else:
        if not args.candidate_json:
            raise SystemExit("--candidate-json is required for commit")
        _, _, migration, _ = paths(root, args.migration_dir)
        commit_card(root, migration, Path(args.candidate_json).resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
