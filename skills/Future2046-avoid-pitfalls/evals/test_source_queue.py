"""Regression tests for stable source ordering and next-source selection."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "source_queue.py"


class SourceQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="source-queue-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "workspace.yaml").write_text(
            'source_root: "01_源知识库"\ncard_root: "02_误区卡片"\nrecord_root: "98_处理记录"\narchive_root: "99_归档"\ntechnical_skill_name: "Future2046-avoid-pitfalls"\n', encoding="utf-8"
        )
        (self.root / "01_源知识库").mkdir()
        (self.root / "02_误区卡片").mkdir()
        (self.root / "98_处理记录").mkdir()
        (self.root / "99_归档").mkdir()
        (self.root / "01_源知识库" / "b.md").write_text("b", encoding="utf-8")
        (self.root / "01_源知识库" / "a.md").write_text("a", encoding="utf-8")
        (self.root / "01_源知识库" / "raw.xlsx").write_bytes(b"not queued directly")

    def command(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--workspace", str(self.root)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )

    def test_queue_preserves_order_and_selects_next(self):
        result = self.command("scan", "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        queue = json.loads((self.root / "98_处理记录" / "source-queue.json").read_text(encoding="utf-8"))
        self.assertEqual([item["sourcePath"] for item in queue["sources"]], ["01_源知识库/a.md", "01_源知识库/b.md"])
        (self.root / "98_处理记录" / "processing-log.jsonl").write_text(
            json.dumps({"sourcePath": "01_源知识库/a.md", "status": "completed", "queuePosition": 1}) + "\n",
            encoding="utf-8",
        )
        result = self.command("next")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["sourcePath"], "01_源知识库/b.md")

    def test_new_source_is_appended_after_existing_queue(self):
        self.assertEqual(self.command("scan", "--write").returncode, 0)
        (self.root / "01_源知识库" / "c.md").write_text("c", encoding="utf-8")
        self.assertEqual(self.command("scan", "--write").returncode, 0)
        queue = json.loads((self.root / "98_处理记录" / "source-queue.json").read_text(encoding="utf-8"))
        positions = {item["sourcePath"]: item["queuePosition"] for item in queue["sources"]}
        self.assertEqual(positions["01_源知识库/c.md"], 3)

    def test_numeric_source_names_use_natural_order(self):
        (self.root / "01_源知识库" / "安先生（2）.md").write_text("2", encoding="utf-8")
        (self.root / "01_源知识库" / "安先生（10）.md").write_text("10", encoding="utf-8")
        result = self.command("scan", "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        queue = json.loads((self.root / "98_处理记录" / "source-queue.json").read_text(encoding="utf-8"))
        names = [item["sourcePath"] for item in queue["sources"]]
        self.assertLess(names.index("01_源知识库/安先生（2）.md"), names.index("01_源知识库/安先生（10）.md"))


if __name__ == "__main__":
    unittest.main()
