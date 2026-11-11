#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SkillMakerBoundaryTests(unittest.TestCase):
    def test_validator_accepts_minimum_package(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "Future2046-example"
            (package / "agents").mkdir(parents=True)
            (package / "SKILL.md").write_text("---\nname: example\ndescription: test\n---\n\n# Test\n", encoding="utf-8")
            (package / "skill.yaml").write_text("package_directory: Future2046-example\n", encoding="utf-8")
            (package / "README.md").write_text("# Test\n", encoding="utf-8")
            (package / "agents" / "openai.yaml").write_text("interface:\n  display_name: Test\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_skill_project.py"), str(package)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_validator_rejects_missing_entrypoint(self):
        with tempfile.TemporaryDirectory() as temp:
            package = Path(temp) / "Future2046-example"
            package.mkdir()
            result = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_skill_project.py"), str(package)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
