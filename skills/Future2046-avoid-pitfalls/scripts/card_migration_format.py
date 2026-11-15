"""Shared card-format helpers for the one-card historical migration controller."""
from __future__ import annotations

import json
import re
from pathlib import Path

FOOTER = "---\n\n抖音 / 视频号 / 小红书同名：姜来已来2046\n本人微信：jianglai8883\n唯一产品：本人24h会员答疑群（找懂的人问就是捷径）\n\n---"
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*]')


def load_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError("missing frontmatter")
    return text[4:].split("\n---\n", 1)


def field(front: str, key: str) -> str:
    match = re.search(rf'^{re.escape(key)}:\s*["\']?(.*?)["\']?\s*$', front, re.M)
    return match.group(1).strip() if match else ""


def split_sections(text: str) -> tuple[str, str, str, str, str]:
    front, rest = load_frontmatter(text)
    heading = re.search(r"(?m)^# (.+)$", rest)
    marker, scene_marker, evidence_marker = "## 误区观点\n", "## 误区场景\n", "## 原文依据\n"
    if not heading or marker not in rest or scene_marker not in rest or evidence_marker not in rest:
        raise ValueError("card sections incomplete")
    before = rest[:heading.start()]
    viewpoint = rest[rest.index(marker) + len(marker):rest.index(scene_marker)].strip()
    tail = rest[rest.index(scene_marker):]
    return front, before, heading.group(1).strip(), viewpoint, tail


def strip_footer(text: str) -> str:
    normalized = text.replace("\r\n", "\n").rstrip("\n")
    return normalized[:-len(FOOTER)].rstrip("\n") if normalized.endswith(FOOTER) else normalized


def render(original: str, viewpoint: str) -> str:
    front, before, _title, _old_viewpoint, tail = split_sections(original)
    body = before + f"# {viewpoint}\n\n## 误区观点\n\n{viewpoint}\n\n" + tail.lstrip("\n")
    body = strip_footer(body)
    return f"---\n{front}\n---\n" + body.rstrip("\n") + "\n\n" + FOOTER + "\n"


def read_index(index_path: Path) -> tuple[list[dict], dict[str, dict]]:
    rows, meta = [], []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        (meta if item.get("recordType") == "indexMeta" else rows).append(item)
    return meta, {row["cardId"]: row for row in rows}
