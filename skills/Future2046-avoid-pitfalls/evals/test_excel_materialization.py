"""Regression tests for Excel row materialization and idempotency."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize_excel_sources.py"


class ExcelMaterializationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="excel-materialize-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "workspace.yaml").write_text(
            'source_root: "01_源知识库"\ncard_root: "02_误区卡片"\nrecord_root: "98_处理记录"\narchive_root: "99_归档"\ntechnical_skill_name: "Future2046-avoid-pitfalls"\n', encoding="utf-8"
        )
        self.source = self.root / "01_源知识库" / "视频文稿"
        self.source.mkdir(parents=True)
        self.records = self.root / "98_处理记录"
        self.records.mkdir()
        (self.root / "02_误区卡片").mkdir()
        (self.root / "99_归档").mkdir()
        self.book = self.source / "测试.xlsx"
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "作品"
        sheet.append(["作品链接", "作品标题", "作品文案", "点赞数"])
        sheet.append(["https://example.test/1", "第一条", "第一段\n第二段", 8])
        sheet.append(["", "第二条", "", 0])
        sheet.append(["https://example.test/3", "第三条", "第三段", 3])
        book.save(self.book)

    def execute_materializer(self):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--workspace", str(self.root)],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def test_materializes_non_empty_rows_and_preserves_full_text(self):
        result = self.execute_materializer()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["materializedCount"], 2)
        self.assertEqual(report["emptyTextRows"], 1)
        first = self.source / "测试（1）.md"
        self.assertTrue(first.exists())
        text = first.read_text(encoding="utf-8")
        self.assertIn("## 全文\n\n第一段\n第二段", text)
        self.assertNotIn("| 作品文案 |", text)
        self.assertIn("| 点赞数 | 8 |", text)
        self.assertIn('source_link: "https://example.test/1"', text)

    def test_second_run_is_idempotent_and_changed_row_is_updated(self):
        first = self.execute_materializer()
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.execute_materializer()
        self.assertEqual(second.returncode, 0, second.stderr)
        report = json.loads(second.stdout)
        self.assertEqual(report["unchangedCount"], 2)
        self.assertEqual(report["materializedCount"], 0)
        book = openpyxl.load_workbook(self.book)
        book.active["C2"] = "第一条已更新"
        book.save(self.book)
        third = self.execute_materializer()
        self.assertEqual(third.returncode, 0, third.stderr)
        report = json.loads(third.stdout)
        self.assertEqual(report["changedCount"], 1)
        self.assertIn("第一条已更新", (self.source / "测试（1）.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
