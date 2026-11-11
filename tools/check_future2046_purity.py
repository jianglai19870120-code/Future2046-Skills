#!/usr/bin/env python3
"""Ensure the Future2046 tree has no unapproved external Skill references."""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def term(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


# Constructed from code points so this guard does not publish the forbidden names.
FORBIDDEN = (
    term(100, 98, 115, 45, 115, 107, 105, 108, 108),
    term(100, 98, 115, 45, 115, 107, 105, 108, 108, 45, 109, 97, 107, 101, 114),
    term(100, 98, 115, 115, 107, 105, 108, 108),
    term(100, 111, 110, 116, 98, 101, 115, 105, 108, 101, 110, 116),
)
SKIP_PARTS = {".git", "__pycache__", ".venv", "venv", "env"}


def scan_text(label: str, text: str) -> list[str]:
    return [f"{label}: forbidden reference" for item in FORBIDDEN if item.casefold() in text.casefold()]


def scan_tree(root: Path) -> list[str]:
    errors: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(root).parts):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        errors.extend(scan_text(str(path.relative_to(root)), content))
    return errors


def scan_archive(path: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            try:
                content = archive.read(name).decode("utf-8")
            except (UnicodeDecodeError, OSError, KeyError):
                continue
            errors.extend(scan_text(f"{path.name}:{name}", content))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--installed-root")
    parser.add_argument("--archive", action="append", default=[])
    args = parser.parse_args()
    errors = scan_tree(Path(args.root).resolve())
    if args.installed_root:
        errors.extend(scan_tree(Path(args.installed_root).resolve()))
    for value in args.archive:
        archive = Path(value).resolve()
        if archive.is_file():
            errors.extend(scan_archive(archive))
        else:
            errors.append(f"missing archive: {archive}")
    if errors:
        print("FAIL: Future2046 purity check")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: Future2046 purity check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
