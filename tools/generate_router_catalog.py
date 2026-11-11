#!/usr/bin/env python3
"""Generate or verify the router's portable catalog from registered Skills."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from check_skill_registry import registry

def expected_catalog(root: Path) -> dict:
    data = registry(root)
    router_id = data.get("framework", {}).get("router_id", "future2046")
    skills = []
    for entry in data["skills"]:
        if entry["id"] == router_id or entry.get("distribution") != "public" or entry.get("status") != "stable" or "codex" not in entry.get("supported_agents", []):
            continue
        path = root / entry["package_path"] / entry.get("entrypoint", "SKILL.md")
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if not text.startswith("---\n"):
            raise ValueError(f"missing frontmatter: {entry['id']}")
        front = yaml.safe_load(text.split("---", 2)[1])
        handoff = front.get("metadata", {}).get("future2046_handoff")
        if front.get("name") != entry["id"] or not isinstance(handoff, dict) or any(not isinstance(handoff.get(field), str) or not handoff[field].strip() for field in ("accepts", "produces", "excludes")):
            raise ValueError(f"invalid routing metadata: {entry['id']}")
        skills.append({
            "id": entry["id"],
            "package_directory": entry["package_directory"],
            "display_name": entry["display_name"],
            "description": front["description"],
            "handoff": handoff,
            "skill_sha256": hashlib.sha256(raw).hexdigest(),
        })
    return {"schema_version": 1, "release_version": data["release_version"], "skills": sorted(skills, key=lambda item: item["id"])}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    target = root / "skills" / "Future2046-router" / "references" / "skill-catalog.json"
    try:
        content = json.dumps(expected_catalog(root), ensure_ascii=False, indent=2) + "\n"
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FAIL: {exc}")
        return 1
    if args.write:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"PASS: generated {target}")
        return 0
    if not target.is_file() or target.read_text(encoding="utf-8") != content:
        print("FAIL: router catalog is stale; run tools/generate_router_catalog.py --write")
        return 1
    print("PASS: router catalog matches registry and Skill definitions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
