#!/usr/bin/env python3
"""Enforce the placement boundary between framework tools and Skill programs."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
from pathlib import Path

from check_skill_registry import registry


ROOT_TOOLS = {
    "brand_footer.py", "build_release.py", "check_future2046_purity.py",
    "check_program_boundaries.py", "check_public_scope.py",
    "check_skill_registry.py", "check_version_consistency.py",
    "generate_router_catalog.py", "read_registry.py", "sync_codex_install.ps1",
    "test_multiskill_framework.py", "test_release_install.py",
    "validate_repository.py", "verify_codex_install.py",
}
EXECUTABLE_SUFFIXES = {".py", ".ps1"}


def check(root: Path) -> list[str]:
    errors: list[str] = []
    tools = root / "tools"
    actual_tools = {path.name for path in tools.iterdir() if path.is_file() and path.suffix.lower() in EXECUTABLE_SUFFIXES}
    unknown = sorted(actual_tools - ROOT_TOOLS)
    missing = sorted(ROOT_TOOLS - actual_tools)
    errors.extend(f"root tools contains unclassified program: {name}" for name in unknown)
    errors.extend(f"root tool missing from system catalog: {name}" for name in missing)
    for base in (tools, root / "skills"):
        for path in base.rglob("*"):
            if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo"}:
                errors.append(f"source package must not retain Python cache: {path.relative_to(root)}")

    guide = tools / "README.md"
    if not guide.is_file():
        errors.append("tools/README.md is required as the human-readable system tool catalog")
    else:
        guide_text = guide.read_text(encoding="utf-8")
        for name in sorted(ROOT_TOOLS):
            if name not in guide_text:
                errors.append(f"tools/README.md does not classify: {name}")

    entries = registry(root)["skills"]
    declared_tests = {
        entry["package_path"]: set(entry.get("tests", []))
        for entry in entries
    }
    for entry in entries:
        package = root / entry["package_path"]
        scripts = package / "scripts"
        if scripts.is_dir():
            for path in scripts.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in EXECUTABLE_SUFFIXES:
                    continue
                if path.name.startswith("test_") or path.name.endswith("_test.py"):
                    errors.append(f"Skill runtime scripts must not contain tests: {path.relative_to(root)}")
        evals = package / "evals"
        if evals.is_dir():
            for path in evals.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in EXECUTABLE_SUFFIXES:
                    continue
                rel = path.relative_to(package).as_posix()
                if rel not in declared_tests[entry["package_path"]]:
                    errors.append(f"Skill test is not registered: {path.relative_to(root)}")
                if not path.name.startswith("test_"):
                    errors.append(f"Skill eval program must use test_ prefix: {path.relative_to(root)}")
        for folder in ("references", "agents"):
            location = package / folder
            if location.is_dir():
                for path in location.rglob("*"):
                    if path.is_file() and path.suffix.lower() in EXECUTABLE_SUFFIXES:
                        errors.append(f"executable program belongs in scripts or evals: {path.relative_to(root)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Future2046 program placement boundaries.")
    parser.add_argument("--root", required=True)
    args = parser.parse_args()
    try:
        errors = check(Path(args.root).resolve())
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: framework tools and Skill programs are correctly separated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
