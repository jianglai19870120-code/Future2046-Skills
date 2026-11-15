#!/usr/bin/env python3
"""Read-only release gate for branch, remote, status and version tag."""
from __future__ import annotations
import argparse, subprocess
from pathlib import Path
import yaml

def canonical_remote(value: str) -> str:
    value = value.strip().removesuffix('.git')
    if value.startswith('git@github.com:'):
        return value.split(':', 1)[1]
    if 'github.com/' in value:
        return value.split('github.com/', 1)[1]
    return value

def run(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=False).stdout.strip()

def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); a=ap.parse_args(); root=Path(a.root).resolve()
    version=(root/"VERSION").read_text(encoding="utf-8").strip()
    cfg=yaml.safe_load((root/"skills/Future2046-toolbox-publisher/references/destinations.yaml").read_text(encoding="utf-8"))
    expected=cfg["github"]["repository"]; branch=run(root,"branch","--show-current"); remote=run(root,"remote","get-url","origin")
    errors=[]
    if branch != cfg["github"]["branch"]: errors.append(f"branch is {branch!r}, expected {cfg['github']['branch']!r}")
    if canonical_remote(remote).rstrip("/") != expected.rstrip("/"): errors.append(f"origin is {remote!r}, expected repository {expected!r}")
    tag=cfg["github"]["tag_format"].format(version=version)
    if run(root,"ls-remote","--tags","origin",f"refs/tags/{tag}"): errors.append(f"remote tag already exists: {tag}")
    print(f"version={version}\nbranch={branch}\nremote={remote}\ntag={tag}")
    print("working_tree:")
    print(run(root,"status","--short") or "clean")
    if errors:
        print("BLOCKED:"); print("\n".join(f"- {e}" for e in errors)); return 1
    print("PASS: read-only release preflight"); return 0
if __name__=="__main__": raise SystemExit(main())
