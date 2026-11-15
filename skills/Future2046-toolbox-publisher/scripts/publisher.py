#!/usr/bin/env python3
"""Future2046 release controller: check, prepare, or publish either channel."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from github_release import GitHubError, publish as publish_github, preflight as github_preflight
from feishu_api import FeishuConfig, FeishuError, FeishuPublisher, sha256


def run(command: list[str], *, check: bool = True) -> str:
    proc = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    if check and proc.returncode:
        raise RuntimeError((proc.stdout + "\n" + proc.stderr).strip())
    return (proc.stdout + "\n" + proc.stderr).strip()


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def validate_archive(archive: Path, manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(archive) as bundle:
        names = sorted(info.filename for info in bundle.infolist() if not info.is_dir())
    expected = sorted(item["path"] for item in manifest.get("files", []))
    if names != expected:
        raise RuntimeError(f"{archive.name} 与 manifest 文件集合不一致")
    if int(manifest.get("file_count", -1)) != len(names):
        raise RuntimeError(f"{archive.name} manifest file_count 不一致")
    return manifest


def build_packages() -> dict[str, Path]:
    ver = version()
    dist = ROOT / "dist"; dist.mkdir(exist_ok=True)
    github_zip = dist / f"Future2046-Skills-{ver}.zip"
    member_zip = dist / f"Future2046-Skills-v{ver}.zip"
    run([sys.executable, "-B", "tools/build_release.py", "--root", str(ROOT), "--output", str(github_zip)])
    run([sys.executable, "-B", str(SCRIPT_DIR / "build_member_package.py"), "--root", str(ROOT), "--output", str(member_zip)])
    validate_archive(github_zip, github_zip.with_suffix(".json"))
    validate_archive(member_zip, member_zip.with_suffix(".json"))
    return {"github_zip": github_zip, "github_manifest": github_zip.with_suffix(".json"), "member_zip": member_zip, "member_manifest": member_zip.with_suffix(".json")}


def gates(*, include_archive_validation: bool) -> None:
    commands = [
        [sys.executable, "-B", "tools/check_version_consistency.py", "--root", str(ROOT)],
        [sys.executable, "-B", "tools/check_skill_registry.py", "--root", str(ROOT)],
        [sys.executable, "-B", "tools/generate_router_catalog.py", "--root", str(ROOT), "--check"],
        [sys.executable, "-B", "tools/check_program_boundaries.py", "--root", str(ROOT)],
    ]
    if include_archive_validation:
        commands.append([sys.executable, "-B", "tools/validate_repository.py", "--root", str(ROOT)])
    for command in commands:
        run(command)


def state_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "Future2046-Skills" / "publisher"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{version()}.json"


def execute(mode: str) -> dict:
    if mode not in {"check", "prepare", "publish", "github", "feishu"}:
        raise ValueError(f"未知模式：{mode}")
    gates(include_archive_validation=False)
    packages = build_packages() if mode != "check" else {}
    if mode != "check":
        run([sys.executable, "-B", "tools/validate_repository.py", "--root", str(ROOT)])
    result = {"status": "checked" if mode == "check" else "prepared", "version": version(), "mode": mode, "packages": {key: str(value) for key, value in packages.items()}}
    if mode in {"publish", "github"}:
        result["github"] = publish_github(ROOT, packages["github_zip"], packages["github_manifest"], version())
    if mode in {"publish", "feishu"}:
        manifest = json.loads(packages["member_manifest"].read_text(encoding="utf-8"))
        result["feishu"] = FeishuPublisher(FeishuConfig.from_environment()).publish(packages["member_zip"], version(), manifest.get("archive_sha256"))
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    state_path().write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(); parser.add_argument("--root", default=str(ROOT)); parser.add_argument("--mode", choices=("check", "prepare", "publish", "github", "feishu"), required=True)
    args = parser.parse_args()
    if Path(args.root).resolve() != ROOT:
        raise SystemExit("publisher.py 必须从当前 Future2046-Skills 仓库运行")
    try: result = execute(args.mode)
    except (OSError, RuntimeError, ValueError, GitHubError, FeishuError) as exc:
        failure = {"status": "blocked", "version": version(), "mode": args.mode, "error": str(exc), "finished_at": datetime.now(timezone.utc).isoformat()}
        state_path().write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(failure, ensure_ascii=False)); return 1
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0


if __name__ == "__main__": raise SystemExit(main())
