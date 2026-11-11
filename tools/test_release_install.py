#!/usr/bin/env python3
"""Install a built release from a clean extracted directory."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--zip")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    archive_path = Path(args.zip).resolve() if args.zip else root / "dist" / f"Future2046-Skills-{version}.zip"
    assert archive_path.is_file(), f"release archive missing: {archive_path}"
    with tempfile.TemporaryDirectory(prefix="future2046-release-smoke-") as temp:
        extracted = Path(temp) / "extracted"
        extracted.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            assert "VERSION" in names
            assert archive.read("VERSION").decode("utf-8").strip() == version
            assert not any("future2046-extract-misconceptions" in name for name in names)
            required_root_files = {
                "LICENSE", "NOTICE.md", "DATA-POLICY.md", "CONTRIBUTING.md",
            }
            assert required_root_files <= names
            archive.extractall(extracted)
        data = yaml.safe_load((extracted / "shared" / "skill-registry.yaml").read_text(encoding="utf-8"))
        assert data.get("release_version") == version
        public_entries = [entry for entry in data["skills"] if entry.get("distribution") == "public"]
        assert any(entry["id"] == "future2046-avoid-pitfalls" for entry in public_entries)
        footer = (extracted / "shared" / "brand-footer.md").read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
        for markdown in (extracted / "skills").rglob("*.md"):
            content = markdown.read_text(encoding="utf-8").replace("\r\n", "\n")
            assert content.rstrip("\n").endswith(footer), markdown
            assert content.count(footer) == 1, markdown
        assert (extracted / "skills" / "Future2046-router" / "LICENSE-NOTICE.md").is_file()
        assert (extracted / "skills" / "Future2046-avoid-pitfalls" / "LICENSE-NOTICE.md").is_file()
        assert (extracted / "tools" / "sync_codex_install.ps1").is_file()
        purity = subprocess.run([sys.executable, str(extracted / "tools" / "check_future2046_purity.py"), "--root", str(extracted)], capture_output=True, text=True, encoding="utf-8", errors="replace")
        if purity.returncode:
            raise AssertionError(purity.stdout + purity.stderr)
        assert (extracted / "requirements.txt").is_file()
        for entry in public_entries:
            if entry.get("distribution") != "public":
                continue
            assert (extracted / entry["package_path"] / "SKILL.md").is_file()
            if entry.get("workspace_template"):
                workspace = Path(temp) / "workspaces" / entry["display_name"]
                shutil.copytree(extracted / entry["workspace_template"], workspace)
                config = yaml.safe_load((workspace / "workspace.yaml").read_text(encoding="utf-8"))
                for key in (field for field in config if field.endswith("_root")):
                    assert (workspace / config[key]).is_dir()
                for path in workspace.rglob("*"):
                    if path.is_file():
                        assert path.name in {"README.md", "workspace.yaml"} or path.name.endswith(".md.template"), path
                assert not (extracted / "workspace-templates").exists()
        if os.name == "nt":
            ps = shutil.which("powershell") or shutil.which("pwsh")
            assert ps, "PowerShell required on Windows"
            target = Path(temp) / "codex-skills"
            proc = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                   str(extracted / "tools" / "sync_codex_install.ps1"), "-InstallRoot", str(target)],
                                  cwd=extracted, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            if proc.returncode:
                raise AssertionError(proc.stdout + proc.stderr)
            for entry in data["skills"]:
                if entry.get("distribution") == "public" and "codex" in entry.get("supported_agents", []):
                    assert (target / entry["package_directory"] / "SKILL.md").is_file()
            discovery = subprocess.run([sys.executable, "-B", str(target / "Future2046-router" / "scripts" / "discover_skills.py")],
                                       capture_output=True, text=True, encoding="utf-8", errors="replace")
            if discovery.returncode:
                raise AssertionError(discovery.stdout + discovery.stderr)
            import json
            available = {item["id"] for item in json.loads(discovery.stdout)["available"]}
            expected = {entry["id"] for entry in data["skills"] if entry["id"] != "future2046" and entry.get("status") == "stable" and "codex" in entry.get("supported_agents", [])}
            assert available == expected, (available, expected)
    print("PASS: clean release extraction, template copy and Codex install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
