from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))

from workspace_discovery import discover_workspaces


class WorkspaceDiscoveryTests(unittest.TestCase):
    def make_workspace(self, root: Path, name: str) -> Path:
        workspace = root / "workspaces" / name
        (workspace / "01_source").mkdir(parents=True)
        (workspace / "02_output").mkdir()
        (workspace / "98_处理记录").mkdir()
        (workspace / "workspace.yaml").write_text(
            "workspace_name: Demo\ntechnical_skill_name: future2046-demo\nsource_root: 01_source\noutput_root: 02_output\nrecord_root: 98_处理记录\n",
            encoding="utf-8",
        )
        return workspace

    def test_discovers_all_first_level_workspaces(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_workspace(root, "one")
            self.make_workspace(root, "two")
            names = [item.directory for item in discover_workspaces(root)]
            self.assertEqual(names, ["one", "two"])

    def test_missing_workspace_yaml_blocks_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_workspace(root, "valid")
            (root / "workspaces" / "broken").mkdir()
            with self.assertRaisesRegex(FileNotFoundError, "workspace.yaml"):
                discover_workspaces(root)

    def test_formal_root_missing_blocks_discovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = self.make_workspace(root, "broken")
            (workspace / "02_output").rmdir()
            with self.assertRaisesRegex(FileNotFoundError, "workspace root missing"):
                discover_workspaces(root)


if __name__ == "__main__":
    unittest.main()
