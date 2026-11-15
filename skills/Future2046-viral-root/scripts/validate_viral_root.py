#!/usr/bin/env python3
"""Production preflight for a viral-root workspace.

This replaces the old development-only regression runner for routine checks.
It is read-only and reports actionable failures without touching source files.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import sync_viral_roots as sync


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate viral-root workspace before sync")
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    ws = Path(args.workspace).resolve()
    cfg = sync.yaml.safe_load((ws / "workspace.yaml").read_text(encoding="utf-8"))
    output = (ws / cfg["output_root"]).resolve()
    records = (ws / cfg["record_root"]).resolve()
    archive = (ws / cfg["archive_root"]).resolve()
    errors = []
    if not output.is_relative_to(ws) or not records.is_relative_to(ws) or not archive.is_relative_to(ws):
        errors.append("configured paths escape the workspace")
    for element, relative in cfg.get("element_directories", {}).items():
        target = (output / relative).resolve()
        if not target.is_relative_to(output) or not target.is_dir():
            errors.append(f"missing element directory: {element} -> {relative}")
    snapshot = records / "source-snapshot.json"
    if snapshot.exists():
        try:
            data = json.loads(snapshot.read_text(encoding="utf-8"))
            for relative in data.get("artifacts", {}).values():
                sync.confined_path(output, str(relative))
                if not (output / relative).is_file():
                    errors.append(f"missing registered artifact: {relative}")
        except Exception as exc:
            errors.append(str(exc))
    for path in ws.rglob("*"):
        if path.is_file() and (path.suffix.lower() in (".pyc", ".pyo") or path.name == ".DS_Store"):
            errors.append(f"runtime cache must be removed: {path.relative_to(ws)}")
        if path.is_dir() and path.name == "__pycache__":
            errors.append(f"runtime cache must be removed: {path.relative_to(ws)}")
    if errors:
        print("FAIL: viral-root preflight")
        print("\n".join(f"- {error}" for error in errors))
        return 2
    print(json.dumps({"status": "ready", "workspace": str(ws), "formal_outputs": output.exists()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
