#!/usr/bin/env python3
"""Check portable candidate discovery and routing invariants."""
from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
ROUTER = ROOT / "skills" / "Future2046-router"
spec = importlib.util.spec_from_file_location("future2046_discovery", ROUTER / "scripts" / "discover_skills.py")
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class DiscoveryTests(unittest.TestCase):
    def test_registered_installed_skill(self):
        result = module.discover(ROUTER)
        self.assertIn("future2046-avoid-pitfalls", [entry["id"] for entry in result["available"]])
        self.assertNotIn("future2046", [entry["id"] for entry in result["available"]])

    def test_missing_and_modified_skills_are_not_executable(self):
        with tempfile.TemporaryDirectory(prefix="future2046-discovery-") as temp:
            root = Path(temp)
            router = root / "Future2046-router"
            (router / "references").mkdir(parents=True)
            shutil.copy2(ROUTER / "references" / "skill-catalog.json", router / "references" / "skill-catalog.json")
            result = module.discover(router)
            self.assertEqual(result["available"], [])
            self.assertEqual(result["unavailable"][0]["reason"], "not_installed")
            leaf = root / "Future2046-avoid-pitfalls"
            leaf.mkdir()
            source = ROOT / "skills" / "Future2046-avoid-pitfalls" / "SKILL.md"
            shutil.copy2(source, leaf / "SKILL.md")
            self.assertEqual(len(module.discover(router)["available"]), 1)
            (leaf / "SKILL.md").write_text("---\nname: wrong\n---\n", encoding="utf-8")
            self.assertEqual(module.discover(router)["unavailable"][0]["reason"], "definition_mismatch")
            (leaf / "SKILL.md").write_text(source.read_text(encoding="utf-8") + "\nLocal change\n", encoding="utf-8")
            self.assertEqual(module.discover(router)["unavailable"][0]["reason"], "definition_mismatch")
            extra = root / "Future2046-unregistered"
            extra.mkdir()
            (extra / "SKILL.md").write_text("---\nname: future2046-unregistered\n---\n", encoding="utf-8")
            self.assertEqual(len(module.discover(router)["available"]), 0)

    def test_router_requires_full_member_execution(self):
        rules = (ROUTER / "SKILL.md").read_text(encoding="utf-8")
        for marker in ("完整读取", "当前对话", "不能代替少走弯路", "只报告实际执行过的 Skill"):
            self.assertIn(marker, rules)


if __name__ == "__main__":
    unittest.main()
