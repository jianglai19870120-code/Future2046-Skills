"""Regression tests for rejecting arbitrary directories as workspaces."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


class WorkspaceSafetyTests(unittest.TestCase):
    def test_missing_marker_fails_without_creating_record_root(self):
        with tempfile.TemporaryDirectory(prefix="workspace-safety-") as temp:
            root = Path(temp)
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "source_queue.py"), "scan", "--write", "--workspace", str(root)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse((root / "98_处理记录").exists())

    def test_renamed_workspace_with_valid_contract_is_accepted(self):
        with tempfile.TemporaryDirectory(prefix="workspace-safety-") as temp:
            root = Path(temp)
            for folder in ("01_源知识库", "02_误区卡片", "98_处理记录", "99_归档"):
                (root / folder).mkdir()
            (root / "workspace.yaml").write_text(
                'source_root: "01_源知识库"\n'
                'card_root: "02_误区卡片"\n'
                'record_root: "98_处理记录"\n'
                'archive_root: "99_归档"\n'
                'technical_skill_name: "Future2046-avoid-pitfalls"\n',
                encoding="utf-8",
            )
            (root / "01_源知识库" / "sample.md").write_text("sample", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPTS / "source_queue.py"), "scan", "--write", "--workspace", str(root)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((root / "98_处理记录" / "source-queue.json").is_file())


if __name__ == "__main__":
    unittest.main()
