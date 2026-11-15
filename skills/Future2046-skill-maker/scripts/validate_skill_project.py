#!/usr/bin/env python3
"""Validate the minimum structure of a Future2046 Skill package."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_dir")
    args = parser.parse_args()
    package = Path(args.skill_dir).resolve()
    required = ["SKILL.md", "skill.yaml", "README.md", "agents/openai.yaml"]
    missing = [item for item in required if not (package / item).is_file()]
    if missing:
        print("FAIL: missing " + ", ".join(missing))
        return 1
    meta = yaml.safe_load((package / "skill.yaml").read_text(encoding="utf-8"))
    skill = (package / "SKILL.md").read_text(encoding="utf-8")
    if meta.get("package_directory") != package.name:
        print("FAIL: package_directory mismatch")
        return 1
    if not skill.startswith("---") or "name:" not in skill.split("---", 2)[1]:
        print("FAIL: invalid SKILL.md frontmatter")
        return 1
    executable_suffixes = {".py", ".ps1"}
    errors = []
    scripts = package / "scripts"
    if scripts.is_dir():
        for path in scripts.rglob("*"):
            if path.is_file() and path.suffix.lower() in executable_suffixes and (
                path.name.startswith("test_") or path.name.endswith("_test.py")
            ):
                errors.append(f"runtime scripts must not contain tests: {path.relative_to(package)}")
    evals = package / "evals"
    if evals.is_dir():
        for path in evals.rglob("*"):
            if path.is_file() and path.suffix.lower() in executable_suffixes and not path.name.startswith("test_"):
                errors.append(f"eval programs must use test_ prefix: {path.relative_to(package)}")
    for folder in ("references", "agents"):
        location = package / folder
        if location.is_dir():
            for path in location.rglob("*"):
                if path.is_file() and path.suffix.lower() in executable_suffixes:
                    errors.append(f"executable belongs in scripts or evals: {path.relative_to(package)}")
    if errors:
        print("FAIL: " + "; ".join(errors))
        return 1
    print("PASS: Skill project structure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
