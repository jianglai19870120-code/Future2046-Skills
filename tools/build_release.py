#!/usr/bin/env python3
"""Build a public zip containing Skill packages and clean workspace frameworks."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import argparse
import json
import shutil
import subprocess
import tempfile
import zipfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from check_skill_registry import registry
from workspace_discovery import discover_workspaces
import yaml


PUBLIC_FILES = ("README.md", "LICENSE", "NOTICE.md", "DATA-POLICY.md", "CONTRIBUTING.md", "VERSION", "CHANGELOG.md", "requirements.txt")


def copy_clean_workspace(workspace, destination: Path) -> None:
    """Extract only the portable framework from a real local workspace."""
    source = workspace.path
    config_path = source / "workspace.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "README.md", destination / "README.md")
    shutil.copy2(config_path, destination / "workspace.yaml")
    for _, relative, source_dir in workspace.roots:
        target = Path(relative)
        source_dir = source / target
        destination_dir = destination / target
        destination_dir.mkdir(parents=True, exist_ok=True)
        # Keep only explanatory and format-template files. Never copy local data.
        for path in source_dir.rglob("*"):
            if not path.is_file() or path.name != "README.md" and not path.name.endswith(".md.template"):
                continue
            relative_file = path.relative_to(source_dir)
            target_file = destination_dir / relative_file
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target_file)
    for _, relative in workspace.excluded_roots:
        (destination / relative).mkdir(parents=True, exist_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    catalog_check = subprocess.run([sys.executable, str(root / "tools" / "generate_router_catalog.py"), "--root", str(root), "--check"], text=True)
    if catalog_check.returncode:
        return catalog_check.returncode
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    output = Path(args.output).resolve() if args.output else root / "dist" / f"Future2046-Skills-{version}.zip"
    with tempfile.TemporaryDirectory(prefix="future2046-release-") as temp:
        stage = Path(temp) / "Future2046-Skills"
        stage.mkdir()
        for relative in PUBLIC_FILES:
            shutil.copy2(root / relative, stage / relative)
        for directory in ("docs", "shared", "tools", ".github"):
            shutil.copytree(
                root / directory,
                stage / directory,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        release_registry = registry(root)
        release_registry['skills'] = [entry for entry in release_registry['skills'] if entry.get('distribution') == 'public' and entry.get('status') == 'stable']
        (stage / 'shared' / 'skill-registry.yaml').write_text(
            yaml.safe_dump(release_registry, allow_unicode=True, sort_keys=False), encoding='utf-8')
        workspaces = discover_workspaces(root)
        registered_templates = {entry.get('workspace_template') for entry in release_registry['skills'] if entry.get('workspace_template')}
        discovered_paths = {f"workspaces/{workspace.directory}" for workspace in workspaces}
        missing_templates = sorted(registered_templates - discovered_paths)
        if missing_templates:
            raise FileNotFoundError(f"registered workspace template missing: {', '.join(missing_templates)}")
        for entry in release_registry['skills']:
            package_path = entry['package_path']
            shutil.copytree(root / package_path, stage / package_path, dirs_exist_ok=True,
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        for workspace in workspaces:
            copy_clean_workspace(workspace, stage / "workspaces" / workspace.directory)
        check = subprocess.run([sys.executable, str(root / "tools" / "check_public_scope.py"), "--root", str(stage)], text=True)
        if check.returncode:
            return check.returncode
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(stage).as_posix())
                elif path.is_dir() and not any(path.iterdir()):
                    archive.writestr(path.relative_to(stage).as_posix().rstrip("/") + "/", "")
        files = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                files.append({"path": path.relative_to(stage).as_posix(), "size": path.stat().st_size, "sha256": digest})
        manifest = {
            "schema_version": 2,
            "package_type": "github_public",
            "version": version,
            "package": output.name,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "skills": [entry["id"] for entry in release_registry["skills"]],
            "workspaces": [workspace.manifest_record("clean_template") for workspace in workspaces],
            "file_count": len(files),
            "total_size": sum(item["size"] for item in files),
            "files": files,
        }
        (output.with_suffix(".json")).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: built {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
