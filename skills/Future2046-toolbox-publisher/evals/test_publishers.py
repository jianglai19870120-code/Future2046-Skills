from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from feishu_api import FeishuConfig, FeishuError, FeishuPublisher
from github_release import repository_from_remote


class Response:
    ok = True
    text = ""

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class Session:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if url.endswith("tenant_access_token/internal"):
            return Response({"code": 0, "tenant_access_token": "test-token"})
        return Response({"code": 0, "data": {"file_token": "uploaded-token"}})

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return Response({"code": 0, "data": {"file_token": "uploaded-token"}})


class LargeSession(Session):
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if url.endswith("upload_prepare"):
            return Response({"code": 0, "data": {"upload_id": "upload-id", "block_size": 2, "block_num": 2}})
        if url.endswith("upload_finish"):
            return Response({"code": 0, "data": {"file_token": "large-token"}})
        return Response({"code": 0, "data": {}})

class PublisherTests(unittest.TestCase):
    def test_missing_feishu_config_is_explicit(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(FeishuError, "AI_VIRAL_FEISHU_APP_ID"):
                FeishuConfig.from_environment()

    def test_small_upload_uses_single_upload_endpoint(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "small.zip"
            archive.write_bytes(b"zip")
            session = Session()
            publisher = FeishuPublisher(FeishuConfig("id", "secret", "https://x.feishu.cn/wiki/token"), session)
            token = publisher._upload_small(archive, "block")
            self.assertEqual(token, "uploaded-token")
            self.assertTrue(any("upload_all" in call[1] for call in session.calls))

    def test_large_upload_uses_multipart_endpoints(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "large.zip"
            archive.write_bytes(b"four")
            session = LargeSession()
            publisher = FeishuPublisher(FeishuConfig("id", "secret", "https://x.feishu.cn/wiki/token"), session)
            token = publisher._upload_large(archive, "block")
            self.assertEqual(token, "large-token")
            endpoints = [call[1] for call in session.calls]
            self.assertTrue(any(endpoint.endswith("upload_prepare") for endpoint in endpoints))
            self.assertEqual(sum(endpoint.endswith("upload_part") for endpoint in endpoints), 2)
            self.assertTrue(any(endpoint.endswith("upload_finish") for endpoint in endpoints))

    def test_remote_normalization_accepts_https_and_ssh(self):
        self.assertEqual(repository_from_remote("https://github.com/a/b.git"), "a/b")
        self.assertEqual(repository_from_remote("git@github.com:a/b.git"), "a/b")


if __name__ == "__main__":
    unittest.main()
