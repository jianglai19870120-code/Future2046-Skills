#!/usr/bin/env python3
"""Compare a Codex installation with the authoritative Skill package."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def hashes(root: Path) -> dict[str, str]:
    result = {}
    for path in root.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    source, target = Path(args.source).resolve(), Path(args.target).resolve()
    if not source.is_dir() or not target.is_dir():
        print("FAIL: source or target package is missing")
        return 1
    left, right = hashes(source), hashes(target)
    errors = []
    for path in sorted(set(left) | set(right)):
        if left.get(path) != right.get(path):
            errors.append(path)
    if errors:
        print("FAIL: installed package differs")
        for path in errors:
            print(f"- {path}")
        return 1
    print(f"PASS: Codex installation matches ({len(left)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
