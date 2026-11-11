#!/usr/bin/env python3
"""Append and validate the Future2046 human-readable Markdown brand footer."""
from __future__ import annotations

import argparse
from pathlib import Path


FOOTER_FILE = "shared/brand-footer.md"


def load_footer(root: Path) -> str:
    footer = (root / FOOTER_FILE).read_text(encoding="utf-8")
    return footer.replace("\r\n", "\n").rstrip("\n") + "\n"


def markdown_files(root: Path) -> list[Path]:
    return sorted((root / "skills").rglob("*.md"))


def has_valid_footer(text: str, footer: str) -> bool:
    normalized = text.replace("\r\n", "\n")
    core = footer.rstrip("\n")
    return normalized.rstrip("\n").endswith(core) and normalized.count(core) == 1


def append_footer(path: Path, footer: str) -> bool:
    original = path.read_text(encoding="utf-8")
    normalized = original.replace("\r\n", "\n")
    if has_valid_footer(normalized, footer):
        return False
    body = normalized.rstrip("\n")
    path.write_text(body + "\n\n" + footer, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--append-existing", action="store_true")
    parser.add_argument("--append-file", action="append", default=[], help="Append the footer to one or more Markdown files")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    footer = load_footer(root)
    if args.append_file:
        changed = 0
        for value in args.append_file:
            path = Path(value)
            if not path.is_absolute():
                path = root / path
            if path.suffix.lower() != ".md":
                raise SystemExit(f"only Markdown files are supported: {path}")
            changed += append_footer(path.resolve(), footer)
        print(f"PASS: appended brand footer to {changed} specified Markdown files")
        return 0
    files = markdown_files(root)
    if args.append_existing:
        changed = sum(append_footer(path, footer) for path in files)
        print(f"PASS: appended brand footer to {changed} Markdown files")
        return 0
    errors = []
    for path in files:
        if not has_valid_footer(path.read_text(encoding="utf-8"), footer):
            errors.append(str(path.relative_to(root)))
    if errors:
        print("FAIL: invalid or missing brand footer")
        for item in errors:
            print(f"- {item}")
        return 1
    print(f"PASS: brand footer valid in {len(files)} Skill Markdown files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
