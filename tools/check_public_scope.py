#!/usr/bin/env python3
"""Fail when a candidate public package contains local data or machine paths."""
from __future__ import annotations

import argparse
from pathlib import Path

FORBIDDEN_DIRS = {"01_源知识库", "02_误区卡片", "98_处理记录", "99_归档", ".obsidian", "__pycache__"}
FORBIDDEN_SUFFIXES = {".xlsx", ".xls", ".xlsm", ".pyc", ".pyo"}
FORBIDDEN_TEXT = ("E:" + "\\误区拆解工作区", "C:" + "\\Users\\Administrator", "E:" + "/误区拆解工作区")


def check(root: Path, ignore_generated_caches: bool = False) -> list[str]:
    errors: list[str] = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] == "workspaces":
            if path.is_file() and not (
                path.name in {"README.md", "workspace.yaml"}
                or path.name.endswith(".md.template")
            ):
                errors.append(f"unexpected file in clean workspace framework: {rel}")
            continue
        if "__pycache__" in rel.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        is_template_path = bool(rel.parts) and rel.parts[0] == "workspace-templates"
        is_template_file = path.is_file() and (path.name in {"README.md", "workspace.yaml", ".gitkeep"} or path.name.endswith(".md.template"))
        is_template_placeholder = is_template_path and (not path.is_file() or is_template_file)
        if is_template_path and path.is_file() and not is_template_placeholder:
            errors.append(f"unexpected file in empty workspace template: {rel}")
        if any(part in FORBIDDEN_DIRS for part in rel.parts) and not is_template_placeholder:
            errors.append(f"forbidden private directory or cache: {rel}")
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            errors.append(f"forbidden private file type: {rel}")
        if path.is_file() and path.stat().st_size < 5_000_000:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for marker in FORBIDDEN_TEXT:
                if marker in text:
                    errors.append(f"machine-specific path in public file {rel}: {marker}")
    if (root / "workspace-templates").exists():
        errors.append("legacy workspace-templates directory must not be published")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--ignore-generated-caches", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"FAIL: public candidate does not exist: {root}")
        return 1
    errors = check(root, args.ignore_generated_caches)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: public scope is clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
