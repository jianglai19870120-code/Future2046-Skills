"""Recoverable commit behavior in an isolated temporary workspace."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "recover_run.py"
sys.path.insert(0, str(SCRIPT.parent))
from commit_run import PRE, validate_pre


def sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest().upper()


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v4-recover-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "workspace.yaml").write_text(
            'source_root: "01_源知识库"\ncard_root: "02_误区卡片"\nrecord_root: "98_处理记录"\narchive_root: "99_归档"\ntechnical_skill_name: "Future2046-avoid-pitfalls"\n',
            encoding="utf-8",
        )
        self.records = self.root / "98_处理记录"
        (self.root / "01_源知识库").mkdir()
        (self.root / "99_归档").mkdir()
        self.run = self.records / "runs" / "run-1"
        self.backup = self.run / "rollback"
        self.backup.mkdir(parents=True)
        self.card = self.root / "02_误区卡片" / "one.md"
        self.card.parent.mkdir()
        self.old_card, self.new_card = b"old card", b"new card"
        self.card.write_bytes(self.new_card)
        self.old_index, self.new_index = b'{"cardId":"old"}\n', b'{"cardId":"new"}\n'
        self.old_log, self.new_log = b'{"runId":"old"}\n', b'{"runId":"old"}\n{"runId":"run-1","status":"completed"}\n'
        (self.records / "card-index.jsonl").write_bytes(self.new_index)
        (self.records / "processing-log.jsonl").write_bytes(self.new_log)
        for name, body in (("card-0.bin", self.old_card), ("index.bin", self.old_index),
                           ("log.bin", self.old_log), ("run.bin", b'{"status":"in_progress"}\n')):
            (self.backup / name).write_bytes(body)
        (self.run / "run.json").write_bytes(b'{"status":"completed"}\n')
        for name in ("active-run.json", "pipeline.lock"):
            (self.records / name).write_text('{"runId":"run-1","sourcePath":"one.md"}', encoding="utf-8")
        self.journal = {"runId": "run-1", "status": "index_written", "cards": [
            {"target": "02_误区卡片/one.md", "oldSha256": sha(self.old_card),
             "newSha256": sha(self.new_card), "backupPath": "98_处理记录/runs/run-1/rollback/card-0.bin"}],
            "indexOldSha256": sha(self.old_index), "indexNewSha256": sha(self.new_index),
            "logOldSha256": sha(self.old_log), "batchPath": None, "source": None}
        (self.run / "commit-journal.json").write_text(json.dumps(self.journal), encoding="utf-8")

    def execute(self):
        return subprocess.run([sys.executable, str(SCRIPT), "--workspace", str(self.root), "--rollback"],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_partial_commit_rolls_back_and_retains_lock(self):
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.card.read_bytes(), self.old_card)
        self.assertEqual((self.records / "card-index.jsonl").read_bytes(), self.old_index)
        self.assertEqual((self.records / "processing-log.jsonl").read_bytes(), self.old_log)
        self.assertEqual((self.run / "run.json").read_bytes(), b'{"status":"in_progress"}\n')
        self.assertTrue((self.records / "pipeline.lock").exists())
        self.assertFalse((self.run / "commit-journal.json").exists())
        self.assertEqual(len(list(self.run.glob("commit-journal-rolled-back-*.json"))), 1)

    def test_external_card_change_blocks_rollback(self):
        self.card.write_bytes(b"third party edit")
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.card.read_bytes(), b"third party edit")
        self.assertTrue((self.records / "pipeline.lock").exists())

    def test_index_changed_after_final_dedup_blocks_commit(self):
        (self.records / "card-index.jsonl").write_bytes(self.new_index)
        (self.root / "source.md").write_bytes(b"source")
        receipts = []
        for i, stage in enumerate(PRE):
            path = self.run / f"{stage}.json"
            payload = {"cards": []} if stage in ("independent_review", "oral_polish") else {}
            if stage == "global_deduplication_final":
                payload["indexSha256"] = sha(self.old_index)
            path.write_text(json.dumps(payload), encoding="utf-8")
            receipts.append({"stage": stage, "status": "completed", "evidence": {
                "artifactPath": path.relative_to(self.root).as_posix(),
                "inputSha256": str(i), "outputSha256": str(i+1)}})
        run = {"runId": "run-1", "sourcePath": "source.md", "pipelineVersion": "v4-artifact",
               "status": "in_progress", "stageReceipts": receipts}
        receipts[0]["evidence"]["outputSha256"] = sha(b"source")
        def verified(root, run_arg, stage, artifact, previous):
            return receipts[PRE.index(stage)]["evidence"]
        with patch("commit_run.check_stage", side_effect=verified):
            with self.assertRaisesRegex(ValueError, "index changed after final deduplication"):
                validate_pre(self.root, run, [])


if __name__ == "__main__":
    unittest.main()
