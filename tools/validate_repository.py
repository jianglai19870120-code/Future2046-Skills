#!/usr/bin/env python3
"""Run the repository-level structural and behavior checks."""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from check_skill_registry import registry


def run(command: list[str], cwd: Path) -> list[str]:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, encoding="utf-8", env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if result.returncode:
        return [f"{ ' '.join(command) }\n{result.stdout}{result.stderr}"]
    return []


def check_links(root: Path) -> list[str]:
    errors = []
    for base in (root, root / "docs", root / "shared", root / "skills", root / "workspaces"):
        if not base.exists():
            continue
        files = base.glob("*.md") if base == root else base.rglob("*.md")
        for file in files:
            if "__pycache__" in file.parts:
                continue
            content = file.read_text(encoding="utf-8")
            for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", content):
                path = target.split("#", 1)[0].strip()
                if not path or path.startswith(("http:", "https:", "mailto:")):
                    continue
                if not (file.parent / path).exists():
                    errors.append(f"broken link in {file.relative_to(root)}: {target}")
    return errors


def check_workspace_source(root: Path) -> list[str]:
    """Validate that the registered workspace source has its public guide."""
    local = root / "workspaces" / "误区拆解"
    if not (local / "README.md").is_file() or not (local / "workspace.yaml").is_file():
        return ["workspace source requires README.md and workspace.yaml"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--skip-behavior", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []
    for relative in ("README.md", "LICENSE", "NOTICE.md", "DATA-POLICY.md", "CONTRIBUTING.md", "VERSION", "CHANGELOG.md", ".gitignore", "shared/skill-registry.yaml", "docs/新手入门.md"):
        if not (root / relative).is_file():
            errors.append(f"missing repository file: {relative}")
    extra_docs = sorted(path.name for path in (root / "docs").glob("*.md") if path.name != "新手入门.md")
    if extra_docs:
        errors.append(f"docs contains additional Markdown files: {', '.join(extra_docs)}")
    if (root / "docs" / "新手入门.md").is_file():
        home = (root / "README.md").read_text(encoding="utf-8")
        guide = (root / "docs" / "新手入门.md").read_text(encoding="utf-8")
        for entry in registry(root)["skills"]:
            if entry.get("distribution") == "public" and entry.get("status") == "stable":
                for location, content in (("README.md", home), ("docs/新手入门.md", guide)):
                    if entry["id"] not in content:
                        errors.append(f"{location} missing published Skill: {entry['id']}")
    for script in root.glob("tools/*.py"):
        try:
            ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
        except SyntaxError as exc:
            errors.append(f"syntax error in {script}: {exc}")
    errors += check_links(root)
    errors += check_workspace_source(root)
    errors += run([sys.executable, str(root / "tools" / "check_skill_registry.py"), "--root", str(root)], root)
    errors += run([sys.executable, str(root / "tools" / "generate_router_catalog.py"), "--root", str(root), "--check"], root)
    errors += run([sys.executable, str(root / "tools" / "check_version_consistency.py"), "--root", str(root)], root)
    errors += run([sys.executable, str(root / "tools" / "check_public_scope.py"), "--root", str(root / "skills"), "--ignore-generated-caches"], root)
    errors += run([sys.executable, str(root / "tools" / "check_future2046_purity.py"), "--root", str(root), "--archive", str(root / "dist" / f"Future2046-Skills-{(root / 'VERSION').read_text(encoding='utf-8').strip()}.zip")], root)
    if not args.skip_behavior:
        for entry in registry(root)['skills']:
            for test in entry.get('tests', []):
                errors += run([sys.executable, "-B", str(root / entry['package_path'] / test)], root)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS: repository validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
