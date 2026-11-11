"""Isolated behavior tests for the v4 artifact gate; run with unittest."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SOURCE = "01_源知识库/经纬 (1).md"
BODY = "有人认为努力就一定成功。现实里努力也可能失败。"
CARD = "# 努力就一定成功\n## 误区观点\n努力就一定成功\n## 误区场景\n认为努力必定成功。\n## 原文依据\n有人认为努力就一定成功。\n"

ORAL_QUALITY = {"changed": True, "directAddress": True, "dialogueFeeling": True,
                "naturalConnectors": True, "sentenceRhythmVaried": True,
                "reportToneRemoved": True, "paragraphCount": 2}
ORAL_UNCHANGED_QUALITY = {"changed": False, "unchangedApproved": True,
                          "directAddress": True, "dialogueFeeling": True,
                          "naturalConnectors": True, "sentenceRhythmVaried": True,
                          "reportToneRemoved": True, "paragraphCount": 2}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class PipelineV4Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="v4-gate-", dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "workspace.yaml").write_text(
            'source_root: "01_源知识库"\ncard_root: "02_误区卡片"\nrecord_root: "98_处理记录"\narchive_root: "99_归档"\ntechnical_skill_name: "Future2046-avoid-pitfalls"\n',
            encoding="utf-8",
        )
        (self.root / SOURCE).parent.mkdir(parents=True)
        (self.root / "02_误区卡片").mkdir()
        (self.root / SOURCE).write_text(BODY, encoding="utf-8")
        self.records = self.root / "98_处理记录"
        self.records.mkdir()
        (self.root / "99_归档").mkdir()
        (self.records / "card-index.jsonl").write_text("", encoding="utf-8")
        (self.records / "processing-log.jsonl").write_text("", encoding="utf-8")
        self.run_id = "test-run-1"

    def cli(self, script, *args, ok=True):
        arguments = list(map(str, args))
        if script == "stage_receipt.py":
            arguments.insert(1, "--workspace")
            arguments.insert(2, str(self.root))
        else:
            arguments[:0] = ["--workspace", str(self.root)]
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / script), *arguments],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def start(self, run_id=None, source=SOURCE, position=1, batch="batch-a", ok=True):
        return self.cli("stage_receipt.py", "start", "--source", source, "--run-id",
                        run_id or self.run_id, "--position", position, "--producer-id", "writer",
                        "--batch-id", batch, "--batch-start-position", 1, ok=ok)

    def run_state(self):
        return json.loads((self.records / "runs" / self.run_id / "run.json").read_text(encoding="utf-8"))

    def artifact(self, stage, data):
        rel = f"98_处理记录/runs/{self.run_id}/{stage}.json"
        path = self.root / rel
        path.write_text(json.dumps({"runId": self.run_id, "sourcePath": SOURCE,
                                    "stage": stage, **data}, ensure_ascii=False), encoding="utf-8")
        return rel

    def put(self, name, content):
        rel = f"98_处理记录/runs/{self.run_id}/{name}"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return rel

    def record(self, stage, data, ok=True):
        rel = self.artifact(stage, data)
        result = self.cli("stage_receipt.py", "record", "--run-id", self.run_id,
                          "--stage", stage, "--artifact", rel, ok=ok)
        return rel, result

    def previous(self):
        return self.run_state()["stageReceipts"][-1]["evidence"]["outputSha256"]

    def through(self, target):
        self.start()
        snapshot = self.put("source.md", BODY)
        self.record("source_scan", {"sourceSnapshotPath": snapshot, "sourceSha256": sha(self.root / SOURCE)})
        if target == "source_scan": return
        corrected = self.put("corrected.md", BODY)
        self.record("transcription_normalization", {"inputSha256": self.previous(), "correctedPath": corrected, "changes": [],
                                                    "paragraphReflow": {"changed": False, "beforeParagraphCount": 1,
                                                                        "afterParagraphCount": 1,
                                                                        "paragraphs": [{"paragraph": 1, "role": "body", "boundary": "full"}],
                                                                        "boundaries": []},
                                                    "sourceWriteback": True, "sourceWritebackPath": SOURCE,
                                                    "sourceWritebackSha256": sha(self.root / SOURCE),
                                                    "normalizedSourcePath": SOURCE})
        if target == "transcription_normalization": return
        candidate = {"candidateId": "c1", "mistakenBelief": "努力就一定成功", "sourceEvidence": "有人认为努力就一定成功。",
                     "problemEvidence": "努力也可能失败。", "sourceSpan": "1",
                     "viewpointQuality": {"isMistakenBelief": True, "hasErrorObject": True,
                                          "hasErrorJudgment": True, "hasCausalDirection": True,
                                          "semanticComplete": True, "sourceClose": True,
                                          "tooCompressed": False, "isCorrectionConclusion": False,
                                          "sentenceCount": 1, "commaCount": 0, "characterCount": 8},
                     "sourceEvidenceMeta": {"paragraphIds": [1], "startSentence": 1,
                                            "endSentence": 2, "roles": {"cognitive": True,
                                            "problem": True, "correction": False},
                                            "isContinuous": True, "contextComplete": True,
                                            "evidenceSpans": [
                                                {"kind": "sourceEvidence", "start": BODY.index("有人认为努力就一定成功。"), "end": BODY.index("有人认为努力就一定成功。") + len("有人认为努力就一定成功。")},
                                                {"kind": "problemEvidence", "start": BODY.index("努力也可能失败。"), "end": BODY.index("努力也可能失败。") + len("努力也可能失败。")},
                                            ]},
                     "viewpointPattern": "以为A就能B", "patternSelectionReason": "原文把努力直接当成成功的充分条件"}
        candidates, _ = self.record("misconception_candidate_identification", {"inputSha256": self.previous(), "correctedPath": corrected, "candidates": [candidate], "candidateCoverage": {"exhaustiveScan": True, "reviewedSegments": ["p1"], "themesReviewed": ["努力与结果"], "noMoreCandidatesConfirmed": True, "rejectedOrMergedCount": 0}})
        if target == "misconception_candidate_identification": return
        gates = dict.fromkeys(("errorObject", "errorContent", "errorScene", "internalCorrection", "independentCard"), True)
        judgment, _ = self.record("five_gate_judgment", {"inputSha256": self.previous(), "candidatesPath": candidates,
                                                        "results": [{"candidateId": "c1", "gates": gates}]})
        if target == "five_gate_judgment": return
        self.record("intra_document_deduplication", {"inputSha256": self.previous(), "judgmentPath": judgment, "results": [{"candidateId": "c1", "disposition": "keep"}]})
        if target == "intra_document_deduplication": return
        index = self.put("index-snapshot.jsonl", "")
        self.record("global_deduplication_pre", {"inputSha256": self.previous(), "indexSnapshotPath": index,
                                                 "indexSha256": sha(self.root / index), "results": [{"candidateId": "c1", "dedupStatus": "new", "reason": "no historic cards"}]})
        if target == "global_deduplication_pre": return
        draft = self.put("draft/draft.md", CARD)
        self.draft = draft
        self.record("card_draft_generation", {"inputSha256": self.previous(), "generatedFrom": "source_and_candidates",
                                              "cards": [{"candidateId": "c1", "path": draft, "sha256": sha(self.root / draft)}]})
        if target == "card_draft_generation": return

    def test_placeholder_hash_rejected_without_receipt(self):
        self.through("source_scan")
        corrected = self.put("corrected.md", BODY)
        self.record("transcription_normalization", {"inputSha256": "0" * 64, "correctedPath": corrected, "changes": [],
                                                    "paragraphReflow": {"changed": False, "beforeParagraphCount": 1,
                                                                        "afterParagraphCount": 1,
                                                                        "paragraphs": [{"paragraph": 1, "role": "body", "boundary": "full"}],
                                                                        "boundaries": []}}, ok=False)
        self.assertEqual(len(self.run_state()["stageReceipts"]), 1)

    def test_missing_stage_rejected(self):
        self.through("source_scan")
        self.record("five_gate_judgment", {"inputSha256": self.previous(), "results": []}, ok=False)
        self.assertEqual(len(self.run_state()["stageReceipts"]), 1)

    def test_record_batch_preserves_stage_order_and_receipts(self):
        self.through("source_scan")
        corrected = self.put("corrected.md", BODY)
        artifact = self.artifact("transcription_normalization", {
            "inputSha256": self.previous(),
            "correctedPath": corrected,
            "changes": [],
            "paragraphReflow": {
                "changed": False,
                "beforeParagraphCount": 1,
                "afterParagraphCount": 1,
                "paragraphs": [{"paragraph": 1, "role": "body", "boundary": "full"}],
                "boundaries": [],
            },
            "sourceWriteback": True,
            "sourceWritebackPath": SOURCE,
            "sourceWritebackSha256": sha(self.root / SOURCE),
            "normalizedSourcePath": SOURCE,
        })
        manifest = self.records / "stages.json"
        manifest.write_text(json.dumps([{"stage": "transcription_normalization", "artifact": artifact}], ensure_ascii=False), encoding="utf-8")
        self.cli("stage_receipt.py", "record-batch", "--run-id", self.run_id, "--stages-json", "98_处理记录/stages.json")
        state = self.run_state()
        self.assertEqual([r["stage"] for r in state["stageReceipts"]], ["source_scan", "transcription_normalization"])

    def test_copy_of_old_card_rejected(self):
        self.through("global_deduplication_pre")
        old = self.root / "02_误区卡片/old.md"
        old.write_text(CARD, encoding="utf-8")
        draft = self.put("draft/draft.md", CARD)
        self.record("card_draft_generation", {"inputSha256": self.previous(), "generatedFrom": "source_and_candidates",
                                              "cards": [{"candidateId": "c1", "path": draft, "sha256": sha(old), "oldCardPath": "02_误区卡片/old.md"}]}, ok=False)

    def test_polish_changed_frozen_fields_rejected(self):
        self.through("card_draft_generation")
        polished = self.put("polished/polished.md", CARD.replace("有人认为努力就一定成功。", "别的依据。"))
        self.record("oral_polish", {"inputSha256": self.previous(), "cards": [{"draftPath": self.draft,
            "draftSha256": sha(self.root / self.draft), "polishedPath": polished,
            "polishedSha256": sha(self.root / polished), "changeExplanation": "改写",
            "oralPolishQuality": ORAL_QUALITY}]}, ok=False)

    def test_unchanged_polish_requires_reason(self):
        self.through("card_draft_generation")
        polished = self.put("polished/polished.md", CARD)
        card = {"draftPath": self.draft, "draftSha256": sha(self.root / self.draft),
                "polishedPath": polished, "polishedSha256": sha(self.root / polished),
                "oralPolishQuality": ORAL_UNCHANGED_QUALITY}
        self.record("oral_polish", {"inputSha256": self.previous(), "cards": [card]}, ok=False)
        self.record("oral_polish", {"inputSha256": self.previous(), "cards": [{**card, "unchangedReason": "无需调整"}]})

    def test_fake_fresh_context_and_invalid_review_rejected(self):
        self.through("card_draft_generation")
        polished = self.put("polished/polished.md", CARD)
        self.record("oral_polish", {"inputSha256": self.previous(), "cards": [{"draftPath": self.draft,
            "draftSha256": sha(self.root / self.draft), "polishedPath": polished,
            "polishedSha256": sha(self.root / polished), "unchangedReason": "无需调整",
            "oralPolishQuality": ORAL_UNCHANGED_QUALITY}]})
        card = {"polishedPath": polished, "reviewedCardSha256": sha(self.root / polished),
                "decision": "approved", "reason": "依据充分", "sourceEvidenceSpan": "1",
                "unchangedPolish": True, "unchangedPolishAccepted": True}
        base = {"inputSha256": self.previous(), "reviewStatus": "approved", "reviewMode": "fresh_context",
                "reviewerInvocationId": "inv-1", "reviewerId": "writer", "reviewTool": "isolated_context_runner", "cards": [card]}
        self.record("independent_review", base, ok=False)
        self.record("independent_review", {**base, "reviewerId": "reviewer", "reviewTool": "claimed_tool"}, ok=False)
        self.record("independent_review", {**base, "reviewerId": "reviewer", "cards": [{**card, "decision": "rejected"}]}, ok=False)
        self.record("independent_review", {**base, "reviewerId": "reviewer", "cards": [{**card, "unchangedPolishAccepted": False}]}, ok=False)
        self.assertEqual(len(self.run_state()["stageReceipts"]), 8)

    def test_serial_lock_and_interruption_retains_staging(self):
        self.start()
        (self.root / "01_源知识库/经纬 (2).md").write_text(BODY, encoding="utf-8")
        second = "01_源知识库/经纬 (2).md"
        self.start(run_id="test-run-2", source=second, position=2, ok=False)
        staged = self.records / "staging" / self.run_id / "cards" / "unfinished.md"
        staged.write_text("unfinished", encoding="utf-8")
        self.cli("recover_run.py", "--pause")
        self.assertEqual(staged.read_text(encoding="utf-8"), "unfinished")
        self.assertTrue((self.records / "pipeline.lock").exists())
        self.assertTrue((self.records / "active-run.json").exists())
        self.assertEqual(self.run_state()["status"], "paused")
        self.start(run_id="test-run-2", source=second, position=2, ok=False)

    def test_v4_full_run_validator_rejects_incomplete_chain(self):
        self.start()
        record = self.run_state()
        record.update(status="completed", fullRun=True)
        with (self.records / "processing-log.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
        result = self.cli("validate_pipeline.py", "--source", SOURCE, "--require-full-run", ok=False)
        self.assertIn("incomplete or unordered v4 stage chain", result.stdout)

    def test_zero_card_cannot_skip_independent_review(self):
        self.start()
        snapshot = self.put("source.md", BODY)
        self.record("source_scan", {"sourceSnapshotPath": snapshot, "sourceSha256": sha(self.root / SOURCE)})
        corrected = self.put("corrected.md", BODY)
        self.record("transcription_normalization", {"inputSha256": self.previous(), "correctedPath": corrected, "changes": [],
                                                    "paragraphReflow": {"changed": False, "beforeParagraphCount": 1,
                                                                        "afterParagraphCount": 1,
                                                                        "paragraphs": [{"paragraph": 1, "role": "body", "boundary": "full"}],
                                                                        "boundaries": []},
                                                    "sourceWriteback": True, "sourceWritebackPath": SOURCE,
                                                    "sourceWritebackSha256": sha(self.root / SOURCE),
                                                    "normalizedSourcePath": SOURCE})
        candidates, _ = self.record("misconception_candidate_identification", {
            "inputSha256": self.previous(), "correctedPath": corrected, "candidates": [],
            "candidateCoverage": {"exhaustiveScan": True, "reviewedSegments": ["p1"], "themesReviewed": ["全文"], "noMoreCandidatesConfirmed": True, "rejectedOrMergedCount": 0}})
        judgment, _ = self.record("five_gate_judgment", {"inputSha256": self.previous(),
            "candidatesPath": candidates, "results": []})
        self.record("intra_document_deduplication", {"inputSha256": self.previous(),
            "judgmentPath": judgment, "results": []})
        index = self.put("index-snapshot.jsonl", "")
        self.record("global_deduplication_pre", {"inputSha256": self.previous(),
            "indexSnapshotPath": index, "indexSha256": sha(self.root / index), "results": []})
        self.record("card_draft_generation", {"inputSha256": self.previous(),
            "generatedFrom": "source_and_candidates", "cards": []})
        self.record("oral_polish", {"inputSha256": self.previous(), "cards": []})
        self.record("global_deduplication_final", {"inputSha256": self.previous(),
            "indexSnapshotPath": index, "indexSha256": sha(self.root / index),
            "results": [], "result": "passed"}, ok=False)
        index_records = self.root / "index-records.json"
        index_records.write_text("[]", encoding="utf-8")
        self.cli("commit_run.py", "--run-id", self.run_id, "--index-records", index_records, ok=False)
        self.assertFalse(any((self.root / "02_误区卡片").iterdir()))


if __name__ == "__main__":
    unittest.main()

