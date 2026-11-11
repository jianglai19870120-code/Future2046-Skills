#!/usr/bin/env python3
"""Read-only preflight for a local GitHub publication."""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    try:
        branch = run(root, "branch", "--show-current")
        remote = run(root, "remote", "-v")
        status = run(root, "status", "--short")
    except (OSError, RuntimeError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"branch={branch or '<detached>'}")
    print(f"remote={'configured' if remote else 'missing'}")
    print(f"working_tree={'clean' if not status else 'has changes'}")
    print("PASS: read-only publication preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
