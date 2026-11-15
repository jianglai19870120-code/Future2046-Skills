#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "skills" / "Future2046-toolbox-publisher" / "scripts" / "build_member_package.py"


class MemberPackageTests(unittest.TestCase):
    def make_workspace(self, root: Path) -> Path:
        workspace = root / "demo-workspace"
        (workspace / "01_source").mkdir(parents=True)
        (workspace / "02_output").mkdir()
        (workspace / "98_records").mkdir()
        (workspace / "99_archive").mkdir()
        (workspace / "tests").mkdir()
        (workspace / "workspace.yaml").write_text(
            "workspace_name: Demo\ntechnical_skill_name: demo\nsource_root: 01_source\noutput_root: 02_output\nrecord_root: 98_records\narchive_root: 99_archive\n",
            encoding="utf-8",
        )
        (workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
        (workspace / "01_source" / "raw.md").write_text("raw\n", encoding="utf-8")
        (workspace / "02_output" / "formal.md").write_text("formal\n", encoding="utf-8")
        (workspace / "98_records" / "run.json").write_text("record\n", encoding="utf-8")
        (workspace / "99_archive" / "old.md").write_text("archive\n", encoding="utf-8")
        (workspace / "tests" / "test.md").write_text("test\n", encoding="utf-8")
        return workspace

    def test_package_contains_only_source_and_formal_output(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = self.make_workspace(Path(temp))
            output = Path(temp) / "member.zip"
            result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(workspace), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertEqual(names, {"workspace.yaml", "README.md", "01_source/raw.md", "02_output/formal.md"})
            manifest = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["file_count"], 4)
            self.assertEqual({item["path"] for item in manifest["files"]}, names)

    def test_missing_source_root_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "demo"
            workspace.mkdir()
            (workspace / "workspace.yaml").write_text("source_root: missing\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(workspace), "--output", str(Path(temp) / "x.zip")], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)

    def test_repository_mode_discovers_registered_stable_skill_and_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "tools").mkdir()
            (root / "skills" / "demo").mkdir(parents=True)
            (root / "shared").mkdir()
            (root / "VERSION").write_text("9.9.9\n", encoding="utf-8")
            (root / "README.md").write_text("root\n", encoding="utf-8")
            (root / "skills" / "demo" / "SKILL.md").write_text("demo\n", encoding="utf-8")
            (root / "shared" / "skill-registry.yaml").write_text(
                "skills:\n  - id: demo\n    package_path: skills/demo\n    distribution: public\n    status: stable\n",
                encoding="utf-8",
            )
            (root / "tools" / "check_skill_registry.py").write_text(
                "import yaml\nfrom pathlib import Path\ndef registry(root): return yaml.safe_load((Path(root)/'shared/skill-registry.yaml').read_text())\n",
                encoding="utf-8",
            )
            output = root / "member.zip"
            result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
            self.assertIn("skills/demo/SKILL.md", names)
            manifest = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["skills"], ["demo"])
            self.assertEqual({item["path"] for item in manifest["files"]}, names)


if __name__ == "__main__":
    unittest.main()
