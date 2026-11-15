#!/usr/bin/env python3
"""GitHub push/tag/Release helper using Git and Git Credential Manager."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class GitHubError(RuntimeError):
    pass


def git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace", capture_output=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if check and proc.returncode:
        raise GitHubError(f"git {' '.join(args)} 失败：{proc.stderr.strip()}")
    return proc.stdout.strip()


def repository_from_remote(remote: str) -> str:
    value = remote.strip().removesuffix(".git")
    if value.startswith("git@github.com:"):
        return value.split(":", 1)[1]
    marker = "github.com/"
    if marker in value:
        return value.split(marker, 1)[1].split("/", 2)[0] + "/" + value.split(marker, 1)[1].split("/", 2)[1]
    raise GitHubError(f"不是受支持的 GitHub remote：{remote}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def credential_headers() -> dict[str, str]:
    proc = subprocess.run(["git", "credential", "fill"], input="protocol=https\nhost=github.com\n\n", text=True, encoding="utf-8", capture_output=True, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if proc.returncode:
        raise GitHubError("Git Credential Manager 未提供 GitHub 凭据")
    values = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1); values[key] = value
    if not values.get("username") or not values.get("password"):
        raise GitHubError("Git Credential Manager 中缺少 GitHub 用户名或凭据")
    encoded = base64.b64encode(f"{values['username']}:{values['password']}".encode()).decode()
    return {"Authorization": "Basic " + encoded, "Accept": "application/vnd.github+json", "User-Agent": "Future2046-toolbox-publisher"}


def api(method: str, url: str, headers: dict[str, str], body: bytes | None = None, content_type: str = "application/json") -> dict[str, Any]:
    request = urllib.request.Request(url, method=method, data=body, headers={**headers, "Content-Type": content_type})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise GitHubError(f"GitHub API {method} {url} 失败：HTTP {exc.code} {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"GitHub API 网络失败：{exc}") from exc


def preflight(root: Path, branch: str, tag: str) -> dict[str, str]:
    current_branch = git(root, "branch", "--show-current")
    remote = git(root, "remote", "get-url", "origin")
    if current_branch != branch:
        raise GitHubError(f"当前分支为 {current_branch}，预期为 {branch}")
    if git(root, "status", "--porcelain"):
        raise GitHubError("工作区存在未提交改动，发布器不会擅自提交或覆盖")
    git(root, "fetch", "--prune", "origin", branch)
    local = git(root, "rev-parse", "HEAD")
    upstream = git(root, "rev-parse", f"origin/{branch}")
    if local != upstream:
        raise GitHubError("本地分支与远程分支不一致，拒绝发布")
    if git(root, "ls-remote", "--tags", "origin", f"refs/tags/{tag}"):
        raise GitHubError(f"远程 Tag 已存在：{tag}")
    return {"remote": remote, "repository": repository_from_remote(remote), "commit": local}


def publish(root: Path, archive: Path, manifest: Path, version: str, branch: str = "main") -> dict[str, Any]:
    tag = f"v{version}"
    state = preflight(root, branch, tag)
    if not archive.is_file() or not manifest.is_file():
        raise GitHubError("GitHub Release 资产不存在")
    headers = credential_headers()
    api_root = "https://api.github.com/repos/" + state["repository"]
    try:
        api("GET", f"{api_root}/releases/tags/{tag}", headers)
    except GitHubError as exc:
        if "HTTP 404" not in str(exc):
            raise
    else:
        raise GitHubError(f"GitHub Release 已存在：{tag}")
    release = api("POST", f"{api_root}/releases", headers, json.dumps({"tag_name": tag, "target_commitish": branch, "name": f"Future2046-Skills {version}", "body": f"Future2046-Skills {version} 双通道发布。"}).encode())
    upload_root = str(release["upload_url"]).split("{", 1)[0]
    uploaded = []
    for path, content_type in ((archive, "application/zip"), (manifest, "application/json")):
        url = upload_root + "?name=" + urllib.parse.quote(path.name)
        asset = api("POST", url, headers, path.read_bytes(), content_type)
        if asset.get("state") != "uploaded" or int(asset.get("size", -1)) != path.stat().st_size:
            raise GitHubError(f"GitHub 资产回读失败：{path.name}")
        uploaded.append({"name": asset["name"], "size": asset["size"], "sha256": sha256(path), "state": asset["state"]})
    verified = api("GET", f"{api_root}/releases/tags/{tag}", headers)
    names = {asset.get("name") for asset in verified.get("assets", [])}
    if {archive.name, manifest.name} - names:
        raise GitHubError("GitHub Release 资产集合不完整")
    return {"status": "published", "repository": state["repository"], "commit": state["commit"], "tag": tag, "release_url": verified.get("html_url"), "assets": uploaded}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--root", required=True); parser.add_argument("--archive", required=True); parser.add_argument("--manifest", required=True); parser.add_argument("--version", required=True); parser.add_argument("--branch", default="main")
    args = parser.parse_args()
    try: result = publish(Path(args.root).resolve(), Path(args.archive).resolve(), Path(args.manifest).resolve(), args.version, args.branch)
    except (OSError, GitHubError) as exc: print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False)); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == "__main__": raise SystemExit(main())
