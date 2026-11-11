#!/usr/bin/env python3
"""List only registered and intact sibling Skills as executable candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def discover(router_dir: Path, skills_root: Path | None = None) -> dict:
    catalog = json.loads((router_dir / "references" / "skill-catalog.json").read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1 or not isinstance(catalog.get("skills"), list):
        raise ValueError("invalid router catalog")
    root = skills_root or router_dir.parent
    available, unavailable = [], []
    seen: set[str] = set()
    for entry in catalog["skills"]:
        sid, folder = entry["id"], entry["package_directory"]
        if sid in seen or not re.fullmatch(r"Future2046-[a-z0-9-]+", folder):
            raise ValueError("invalid or duplicate catalog entry")
        seen.add(sid)
        path = root / folder / "SKILL.md"
        if not path.is_file():
            unavailable.append({"id": sid, "reason": "not_installed"})
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8").replace("\r\n", "\n")
        except (OSError, UnicodeError):
            unavailable.append({"id": sid, "reason": "unreadable_definition"})
            continue
        digest = hashlib.sha256(raw).hexdigest()
        name = re.search(r"(?m)^name:\s*([^\s]+)\s*$", text.split("---", 2)[1] if text.startswith("---\n") else "")
        if not name or name.group(1) != sid or digest != entry["skill_sha256"]:
            unavailable.append({"id": sid, "reason": "definition_mismatch"})
            continue
        available.append({**entry, "skill_path": str(path.resolve())})
    return {"release_version": catalog["release_version"], "available": available, "unavailable": unavailable}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--router-dir", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--skills-root")
    args = parser.parse_args()
    try:
        result = discover(Path(args.router_dir).resolve(), Path(args.skills_root).resolve() if args.skills_root else None)
    except (OSError, ValueError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
