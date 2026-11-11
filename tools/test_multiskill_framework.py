#!/usr/bin/env python3
"""Exercise registry, build and Codex sync with a temporary second Skill."""
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


def command(*args: str, cwd: Path) -> None:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode:
        raise AssertionError(f"{' '.join(args)}\n{proc.stdout}{proc.stderr}")


def must_fail(*args: str, cwd: Path) -> None:
    proc = subprocess.run(args, cwd=cwd, capture_output=True,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if proc.returncode == 0:
        raise AssertionError(f"unexpected pass: {' '.join(args)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    root = Path(parser.parse_args().root).resolve()
    with tempfile.TemporaryDirectory(prefix="future2046-multiskill-") as temp:
        sample = Path(temp) / "repo"
        sample.mkdir()
        for file in ("README.md", "LICENSE", "NOTICE.md", "DATA-POLICY.md", "CONTRIBUTING.md", "VERSION", "CHANGELOG.md", "requirements.txt", ".gitignore"):
            shutil.copy2(root / file, sample / file)
        for folder in ("docs", "shared", "tools", "skills", "workspaces"):
            shutil.copytree(root / folder, sample / folder,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        name, sid = "Future2046-test-skill", "future2046-test-skill"
        pkg = sample / "skills" / name
        (pkg / "agents").mkdir(parents=True)
        (pkg / "SKILL.md").write_text(f"---\nname: {sid}\ndescription: Temporary test Skill.\nmetadata:\n  future2046_handoff:\n    accepts: input\n    produces: output\n    excludes: unrelated tasks\n---\n\n# Test\n", encoding="utf-8")
        (pkg / "README.md").write_text("# Test Skill\n", encoding="utf-8")
        (pkg / "agents" / "openai.yaml").write_text('interface:\n  display_name: "测试 Skill"\n', encoding="utf-8")
        data = yaml.safe_load((sample / "shared" / "skill-registry.yaml").read_text(encoding="utf-8"))
        entry = {
            "id": sid, "package_directory": name, "display_name": "测试 Skill",
            "version": data["release_version"], "status": "stable", "entrypoint": "SKILL.md",
            "package_path": f"skills/{name}", "workspace_template": "",
            "supported_agents": ["codex"], "runtime": {"python": ">=3.11,<3.14"},
            "distribution": "public", "tests": [],
        }
        data["skills"].append(entry)
        for relative in ("README.md", "docs/新手入门.md"):
            page = sample / relative
            page.write_text(page.read_text(encoding="utf-8") + f"\n{sid}\n", encoding="utf-8")
        (sample / "shared" / "skill-registry.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (pkg / "skill.yaml").write_text(yaml.safe_dump({key: entry[key] for key in (
            "id", "package_directory", "display_name", "version", "entrypoint",
            "workspace_template", "supported_agents", "runtime", "distribution")},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
        command(sys.executable, "-B", "tools/check_skill_registry.py", "--root", str(sample), cwd=sample)
        meta_path = pkg / "skill.yaml"
        original_meta = meta_path.read_text(encoding="utf-8")
        meta_path.write_text(original_meta.replace(entry["version"], "9.9.9"), encoding="utf-8")
        must_fail(sys.executable, "-B", "tools/check_version_consistency.py", "--root", str(sample), cwd=sample)
        meta_path.write_text(original_meta, encoding="utf-8")
        unregistered = sample / "skills" / "Future2046-unregistered"
        unregistered.mkdir()
        (unregistered / "SKILL.md").write_text("# Unknown\n", encoding="utf-8")
        must_fail(sys.executable, "-B", "tools/check_skill_registry.py", "--root", str(sample), cwd=sample)
        (unregistered / "SKILL.md").unlink()
        unregistered.rmdir()
        template = sample / "workspaces" / "测试技能"
        template.mkdir()
        fields = {"source_root": "输入", "card_root": "输出", "record_root": "记录", "archive_root": "归档"}
        (template / "workspace.yaml").write_text(yaml.safe_dump({"technical_skill_name": name, **fields}, allow_unicode=True), encoding="utf-8")
        (template / "README.md").write_text("# 空白工作区\n", encoding="utf-8")
        for folder in fields.values():
            (template / folder).mkdir()
            (template / folder / ".gitkeep").write_text("", encoding="utf-8")
        entry["workspace_template"] = "workspaces/测试技能"
        data["skills"][-1] = entry
        (sample / "shared" / "skill-registry.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        (pkg / "skill.yaml").write_text(yaml.safe_dump({key: entry[key] for key in (
            "id", "package_directory", "display_name", "version", "entrypoint",
            "workspace_template", "supported_agents", "runtime", "distribution")},
            allow_unicode=True, sort_keys=False), encoding="utf-8")
        command(sys.executable, "-B", "tools/check_skill_registry.py", "--root", str(sample), cwd=sample)
        command(sys.executable, "-B", "tools/check_version_consistency.py", "--root", str(sample), cwd=sample)
        command(sys.executable, "-B", "tools/generate_router_catalog.py", "--root", str(sample), "--write", cwd=sample)
        command(sys.executable, "-B", "tools/generate_router_catalog.py", "--root", str(sample), "--check", cwd=sample)
        output = Path(temp) / "release.zip"
        command(sys.executable, "-B", "tools/build_release.py", "--root", str(sample), "--output", str(output), cwd=sample)
        with zipfile.ZipFile(output) as archive:
            assert f"skills/{name}/SKILL.md" in archive.namelist()
            assert "skills/Future2046-router/references/skill-catalog.json" in archive.namelist()
            assert "workspaces/测试技能/workspace.yaml" in archive.namelist()
            assert "tools/sync_codex_install.ps1" in archive.namelist()
        if os.name == "nt":
            installed = Path(temp) / "installed"
            ps = shutil.which("powershell") or shutil.which("pwsh")
            assert ps, "PowerShell required on Windows"
            router_only = Path(temp) / "router-only"
            command(ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sample / "tools" / "sync_codex_install.ps1"), "-SkillId", "future2046", "-InstallRoot", str(router_only), cwd=sample)
            lone = subprocess.run([sys.executable, "-B", str(router_only / "Future2046-router" / "scripts" / "discover_skills.py")], text=True, capture_output=True, encoding="utf-8", errors="replace")
            assert lone.returncode == 0 and '"available": []' in lone.stdout
            command(ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sample / "tools" / "sync_codex_install.ps1"), "-InstallRoot", str(installed), cwd=sample)
            discover = subprocess.run([sys.executable, "-B", str(installed / "Future2046-router" / "scripts" / "discover_skills.py")], text=True, capture_output=True, encoding="utf-8", errors="replace")
            assert discover.returncode == 0 and sid in discover.stdout
            target = installed / name
            stale = target / "obsolete.txt"
            stale.write_text("old", encoding="utf-8")
            (pkg / "README.md").write_text("# Test Skill updated\n", encoding="utf-8")
            (pkg / "SKILL.md").write_text((pkg / "SKILL.md").read_text(encoding="utf-8") + "\nUpdated rule.\n", encoding="utf-8")
            must_fail(sys.executable, "-B", "tools/generate_router_catalog.py", "--root", str(sample), "--check", cwd=sample)
            command(sys.executable, "-B", "tools/generate_router_catalog.py", "--root", str(sample), "--write", cwd=sample)
            command(ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(sample / "tools" / "sync_codex_install.ps1"), "-SkillId", sid, "-InstallRoot", str(installed), cwd=sample)
            assert not stale.exists() and (target / "README.md").read_bytes() == (pkg / "README.md").read_bytes()
            discover = subprocess.run([sys.executable, "-B", str(installed / "Future2046-router" / "scripts" / "discover_skills.py")], text=True, capture_output=True, encoding="utf-8", errors="replace")
            assert discover.returncode == 0 and '"unavailable": []' in discover.stdout
    print("PASS: temporary second Skill registry, build and install")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
