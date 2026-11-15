"""Discover and validate every first-level Future2046 workspace."""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


EXCLUDED_ROOT_KEYS = {"record_root", "archive_root"}
EXCLUDED_DIR_NAMES = {"98_处理记录", "99_归档"}


@dataclass(frozen=True)
class Workspace:
    name: str
    technical_skill: str
    directory: str
    path: Path
    config: dict[str, Any]
    roots: tuple[tuple[str, str, Path], ...]
    excluded_roots: tuple[tuple[str, str], ...]

    def manifest_record(self, mode: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": f"workspaces/{self.directory}",
            "technical_skill": self.technical_skill,
            "mode": mode,
            "included_roots": [{"key": key, "path": relative} for key, relative, _ in self.roots],
            "excluded_roots": [{"key": key, "path": relative, "reason": "record/archive data"} for key, relative in self.excluded_roots],
        }


def _relative_root(value: str, config_path: Path) -> str:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"workspace root escapes workspace: {config_path}: {value}")
    normalized = candidate.as_posix()
    if not normalized or normalized == ".":
        raise ValueError(f"workspace root is empty: {config_path}: {value}")
    return normalized


def load_workspace(path: Path, repository_root: Path | None = None) -> Workspace:
    original_path = path
    if original_path.is_symlink():
        raise ValueError(f"workspace symlink is not allowed: {original_path}")
    path = path.resolve()
    if not path.is_dir():
        raise FileNotFoundError(f"workspace directory missing: {path}")
    if path.is_symlink():
        raise ValueError(f"workspace symlink is not allowed: {path}")
    config_path = path / "workspace.yaml"
    if not config_path.is_file():
        raise FileNotFoundError(f"workspace.yaml missing: {path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(config, dict):
        raise ValueError(f"invalid workspace.yaml: {config_path}")
    name = str(config.get("workspace_name") or config.get("display_name") or path.name).strip()
    technical_skill = str(config.get("technical_skill_name") or "").strip()
    if not technical_skill:
        raise ValueError(f"technical_skill_name missing: {config_path}")
    roots: list[tuple[str, str, Path]] = []
    excluded: list[tuple[str, str]] = []
    for key, value in config.items():
        if not key.endswith("_root") or not isinstance(value, str):
            continue
        relative = _relative_root(value, config_path)
        target = (path / relative).resolve()
        if not target.is_relative_to(path):
            raise ValueError(f"workspace root escapes workspace: {config_path}: {value}")
        if key in EXCLUDED_ROOT_KEYS or Path(relative).name in EXCLUDED_DIR_NAMES:
            excluded.append((key, relative))
            continue
        if not target.is_dir():
            raise FileNotFoundError(f"workspace root missing: {target}")
        roots.append((key, relative, target))
    if not roots:
        raise ValueError(f"workspace has no formal *_root directories: {config_path}")
    repository_root = repository_root.resolve() if repository_root else None
    if repository_root and not path.is_relative_to(repository_root / "workspaces"):
        raise ValueError(f"workspace is outside repository workspaces directory: {path}")
    return Workspace(name, technical_skill, path.name, path, config, tuple(roots), tuple(excluded))


def discover_workspaces(root: Path) -> list[Workspace]:
    """Discover every valid first-level directory under ``root/workspaces``."""
    root = root.resolve()
    workspaces_root = root / "workspaces"
    if not workspaces_root.is_dir():
        raise FileNotFoundError(f"workspaces directory missing: {workspaces_root}")
    result: list[Workspace] = []
    for candidate in sorted(workspaces_root.iterdir(), key=lambda item: item.name.casefold()):
        if not candidate.is_dir():
            continue
        if candidate.name.startswith("."):
            continue
        if candidate.is_symlink():
            raise ValueError(f"workspace symlink is not allowed: {candidate}")
        result.append(load_workspace(candidate, root))
    if not result:
        raise ValueError(f"no workspaces found under {workspaces_root}")
    return result
