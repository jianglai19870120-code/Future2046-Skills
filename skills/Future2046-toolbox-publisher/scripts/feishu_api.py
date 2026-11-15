#!/usr/bin/env python3
"""Self-contained Feishu Wiki ZIP publisher for Future2046."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

API_ROOT = "https://open.feishu.cn/open-apis"
WIKI_TOKEN = re.compile(r"/(?:wiki|space)/([^/?#]+)")
SINGLE_UPLOAD_MAX_BYTES = 20 * 1024 * 1024


class FeishuError(RuntimeError):
    pass


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    root_url: str

    @classmethod
    def from_environment(cls) -> "FeishuConfig":
        values = {name: os.environ.get(name, "").strip() for name in (
            "AI_VIRAL_FEISHU_APP_ID", "AI_VIRAL_FEISHU_APP_SECRET", "AI_VIRAL_FEISHU_ROOT_URL"
        )}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise FeishuError("飞书发布配置缺失：" + ", ".join(missing))
        return cls(values["AI_VIRAL_FEISHU_APP_ID"], values["AI_VIRAL_FEISHU_APP_SECRET"], values["AI_VIRAL_FEISHU_ROOT_URL"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def root_token(url: str) -> str:
    match = WIKI_TOKEN.search(url)
    if not match:
        raise FeishuError("AI_VIRAL_FEISHU_ROOT_URL 必须是飞书 Wiki 页面链接")
    return match.group(1)


class FeishuPublisher:
    def __init__(self, config: FeishuConfig, session: requests.Session | None = None) -> None:
        self.config = config
        self.session = session or requests.Session()
        self._token = ""

    def _access_token(self) -> str:
        if self._token:
            return self._token
        try:
            response = self.session.post(
                API_ROOT + "/auth/v3/tenant_access_token/internal",
                json={"app_id": self.config.app_id, "app_secret": self.config.app_secret}, timeout=30,
            )
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise FeishuError(f"飞书应用鉴权失败：{exc}") from exc
        token = str(payload.get("tenant_access_token") or "")
        if not response.ok or int(payload.get("code", 0)) != 0 or not token:
            raise FeishuError("飞书应用鉴权失败，请检查 App ID、App Secret 和应用启用状态")
        self._token = token
        return token

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._access_token()}"}
        try:
            response = self.session.request(method, API_ROOT + path, headers={**headers, **kwargs.pop("headers", {})}, timeout=30, **kwargs)
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise FeishuError(f"飞书接口请求失败 {method} {path}: {exc}") from exc
        if not response.ok or int(payload.get("code", 0)) != 0:
            raise FeishuError(f"飞书接口失败 {method} {path}: {payload.get('msg') or response.text}")
        return payload.get("data") or {}

    def resolve_root(self) -> dict[str, str]:
        data = self._request("GET", "/wiki/v2/spaces/get_node", params={"token": root_token(self.config.root_url)})
        node = data.get("node") or data
        result = {"space_id": str(node.get("space_id") or ""), "node_token": str(node.get("node_token") or ""), "document_id": str(node.get("obj_token") or "")}
        if not result["space_id"] or not result["node_token"] or result["document_id"] == "" or node.get("obj_type") != "docx":
            raise FeishuError("知识库页面不是可编辑的新版 docx 文档")
        return result

    def list_blocks(self, document_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token
            data = self._request("GET", f"/docx/v1/documents/{document_id}/blocks", params=params)
            batch = data.get("items") or data.get("blocks") or []
            if not isinstance(batch, list):
                raise FeishuError("飞书文档块响应格式异常")
            items.extend(item for item in batch if isinstance(item, dict))
            page_token = str(data.get("page_token") or "")
            if not page_token or not data.get("has_more"):
                return items

    def zip_block(self, document_id: str) -> dict[str, str]:
        candidates = []
        for block in self.list_blocks(document_id):
            file_data = block.get("file") or {}
            name = str(file_data.get("name") or "")
            block_id = str(block.get("block_id") or "")
            token = str(file_data.get("token") or "")
            if block.get("block_type") == 23 and block_id and name.lower().endswith(".zip"):
                candidates.append({"block_id": block_id, "file_token": token, "name": name})
        if len(candidates) != 1:
            raise FeishuError(f"固定知识库页面必须且只能有一个 ZIP 附件，当前找到 {len(candidates)} 个")
        return candidates[0]

    def _upload_small(self, archive: Path, block_id: str) -> str:
        with archive.open("rb") as stream:
            data = self._request("POST", "/drive/v1/medias/upload_all", data={
                "file_name": archive.name, "parent_type": "docx_file", "parent_node": block_id, "size": str(archive.stat().st_size)
            }, files={"file": (archive.name, stream, "application/zip")})
        token = str(data.get("file_token") or data.get("file", {}).get("token") or "")
        if not token:
            raise FeishuError("飞书普通上传响应缺少 file_token")
        return token

    def _upload_large(self, archive: Path, block_id: str) -> str:
        size = archive.stat().st_size
        prepared = self._request("POST", "/drive/v1/medias/upload_prepare", json={"file_name": archive.name, "parent_type": "docx_file", "parent_node": block_id, "size": size})
        upload_id = str(prepared.get("upload_id") or "")
        block_size = int(prepared.get("block_size") or 0)
        block_num = int(prepared.get("block_num") or 0)
        if not upload_id or block_size <= 0 or block_num <= 0:
            raise FeishuError("飞书分片上传初始化响应不完整")
        with archive.open("rb") as stream:
            for seq in range(block_num):
                chunk = stream.read(block_size)
                if not chunk:
                    raise FeishuError(f"飞书分片上传缺少第 {seq + 1} 块")
                self._request("POST", "/drive/v1/medias/upload_part", data={"upload_id": upload_id, "seq": str(seq), "size": str(len(chunk))}, files={"file": (archive.name, io.BytesIO(chunk), "application/zip")})
            if stream.read(1):
                raise FeishuError("飞书分片大小不足以覆盖会员包")
        result = self._request("POST", "/drive/v1/medias/upload_finish", json={"upload_id": upload_id, "block_num": block_num})
        token = str(result.get("file_token") or "")
        if not token:
            raise FeishuError("飞书分片上传完成响应缺少 file_token")
        return token

    def publish(self, archive: Path, version: str, expected_sha256: str | None = None) -> dict[str, Any]:
        if not archive.is_file():
            raise FeishuError(f"会员包不存在：{archive}")
        actual_sha = sha256(archive)
        if expected_sha256 and actual_sha != expected_sha256:
            raise FeishuError("会员包 SHA-256 与 manifest 不一致")
        root = self.resolve_root()
        previous = self.zip_block(root["document_id"])
        token = self._upload_large(archive, previous["block_id"]) if archive.stat().st_size > SINGLE_UPLOAD_MAX_BYTES else self._upload_small(archive, previous["block_id"])
        self._request("PATCH", f"/docx/v1/documents/{root['document_id']}/blocks/{previous['block_id']}", params={"document_revision_id": -1}, json={"replace_file": {"token": token}})
        current = self.zip_block(root["document_id"])
        if current["block_id"] != previous["block_id"] or current["file_token"] != token or current["name"] != archive.name:
            raise FeishuError("飞书原位替换后的文件回读校验失败")
        return {"version": version, "document_id": root["document_id"], "file_block_id": current["block_id"], "previous_file_name": previous["name"], "current_file_name": current["name"], "file_token": token, "size": archive.stat().st_size, "sha256": actual_sha}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--sha256")
    args = parser.parse_args()
    try:
        result = FeishuPublisher(FeishuConfig.from_environment()).publish(Path(args.archive).resolve(), args.version, args.sha256)
    except (OSError, FeishuError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False)); return 1
    print(json.dumps({"status": "published", **result}, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
