#!/usr/bin/env python3
"""Validate the minimum structure of a Future2046 Skill package."""
from __future__ import annotations

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
    print("PASS: Skill project structure")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
