"""Shared checks for source-bound, content-bearing stage artifacts."""
from __future__ import annotations

import hashlib
import json
import difflib
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


WORKSPACE_DEFAULTS = {
    "source_root": "01_源知识库",
    "card_root": "02_误区卡片",
    "record_root": "98_处理记录",
    "archive_root": "99_归档",
}

REQUIRED_WORKSPACE_KEYS = tuple(WORKSPACE_DEFAULTS) + ("technical_skill_name",)


def workspace_setting(root: Path, key: str, default=None):
    """Read a small scalar setting without turning workspace.yaml into a YAML dependency."""
    config = root.resolve() / "workspace.yaml"
    pattern = re.compile(rf"^{re.escape(key)}:\s*(?:\"([^\"]*)\"|'([^']*)'|([^#\s][^#]*?))\s*$")
    for raw in config.read_text(encoding="utf-8").splitlines():
        match = pattern.match(raw)
        if not match:
            continue
        value = next(part for part in match.groups() if part is not None).strip()
        if value.casefold() in {"true", "yes", "on"}:
            return True
        if value.casefold() in {"false", "no", "off"}:
            return False
        return value
    return default


def workspace_layout(root: Path) -> dict[str, str]:
    """Load and validate the portable workspace contract.

    Production commands must never silently treat an arbitrary directory as a
    workspace.  The marker file and all configured roots are therefore
    required before any command is allowed to create runtime state.
    """
    root = root.resolve()
    config = root / "workspace.yaml"
    if not config.is_file():
        raise ValueError(f"未找到有效工作区：{root}；请提供包含 workspace.yaml 的工作区根目录")
    layout = dict(WORKSPACE_DEFAULTS)
    values: dict[str, str] = {}
    for raw in config.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([a-z_]+):\s*(?:\"([^\"]*)\"|'([^']*)'|([^#\s][^#]*?))\s*$", raw)
        if not match:
            continue
        value = next(part for part in match.groups()[1:] if part is not None).strip()
        key = match.group(1)
        if key == "technical_skill_name":
            values[key] = value
            continue
        if key not in layout:
            continue
        candidate = Path(value)
        if not value or candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"invalid workspace path in workspace.yaml: {key}")
        layout[key] = value.replace("\\", "/")
        values[key] = value
    missing = [key for key in REQUIRED_WORKSPACE_KEYS if key not in values or not values[key]]
    if missing:
        raise ValueError(f"workspace.yaml 缺少必需字段：{', '.join(missing)}")
    for key, value in layout.items():
        if key == "record_root" and value.replace("\\", "/").strip("/") in {"98", "处理记录", "98/处理记录"}:
            raise ValueError("workspace.yaml 的 record_root 必须指向正式记录目录 98_处理记录，不能使用 98 或 处理记录")
        target = inside(root, value)
        if not target.is_dir():
            raise ValueError(f"工作区目录不存在：{target}（字段 {key}）")
    return layout


def workspace_path(root: Path, key: str) -> Path:
    if key not in WORKSPACE_DEFAULTS:
        raise ValueError(f"unknown workspace layout key: {key}")
    return inside(root, workspace_layout(root)[key])


def workspace_rel_path(root: Path, path: Path) -> str:
    """Return a canonical workspace-relative POSIX path for artifact metadata."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def record_path(root: Path, value: str, *, run_id: str | None = None,
                subdirectory: str | None = None) -> Path:
    """Resolve a production artifact path and reject every external path.

    Production inputs and outputs must be workspace-relative and must live in
    the configured record_root.  This is deliberately stricter than ``inside``
    so a helper cannot accidentally read/write a system Temp path or the repository root.
    """
    if not isinstance(value, str) or not value or "\\" in value or Path(value).is_absolute():
        raise ValueError("生产路径非法：必须使用工作区内的 POSIX 相对路径")
    root = root.resolve()
    target = inside(root, value)
    records = workspace_path(root, "record_root").resolve()
    if not target.is_relative_to(records):
        raise ValueError(f"生产路径非法：{target}；生产文件只能写入 {records}")
    if run_id is not None:
        run_dir = (records / "runs" / run_id).resolve()
        staging_dir = (records / "staging" / run_id).resolve()
        allowed = target.is_relative_to(run_dir) or target.is_relative_to(staging_dir)
        if subdirectory is not None:
            allowed = target.is_relative_to((run_dir / subdirectory).resolve())
        if not allowed:
            raise ValueError(f"生产路径非法：{target} 不属于当前 run {run_id}")
    return target


def digest(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"missing file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def inside(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or Path(value).is_absolute():
        raise ValueError("artifact path must be workspace-relative POSIX path")
    target = (root / value).resolve()
    if not target.is_relative_to(root.resolve()):
        raise ValueError("artifact escapes workspace")
    return target


def run_file(root: Path, run_id: str, value: str) -> Path:
    target = inside(root, value)
    records = workspace_path(root, "record_root")
    base = (records / "runs" / run_id).resolve()
    staging = (records / "staging" / run_id).resolve()
    if not target.is_relative_to(base) and not target.is_relative_to(staging):
        raise ValueError("artifact belongs to a different run")
    return target


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact must be a JSON object")
    return value


def prior_stage(root: Path, run: dict, name: str) -> dict:
    receipt = next((r for r in run.get("stageReceipts", []) if r.get("stage") == name), None)
    if receipt is None:
        raise ValueError(f"missing prior stage {name}")
    return read_json(run_file(root, run["runId"], receipt["evidence"]["artifactPath"]))


def markdown_paragraph_count(text: str) -> int:
    """Count readable paragraphs in the source's full-text section only."""
    body = text
    if body.startswith("---\n") and "\n---\n" in body[4:]:
        body = body[4:].split("\n---\n", 1)[1]
    headings = list(re.finditer(r"(?m)^##\s+.*$", body))
    if headings:
        body = body[headings[-1].end():]
    blocks = [b.strip() for b in re.split(r"\n\s*\n", body) if b.strip()]
    return sum(1 for block in blocks if not all(line.lstrip().startswith("|") for line in block.splitlines()))


def check_stage(root: Path, run: dict, stage: str, artifact: Path, previous_hash: str | None) -> dict:
    """Validate current artifact and return machine-calculated evidence."""
    data = read_json(artifact)
    if data.get("runId") != run["runId"] or data.get("sourcePath") != run["sourcePath"] or data.get("stage") != stage:
        raise ValueError("artifact run/source mismatch")
    if stage != "source_scan" and data.get("inputSha256") != previous_hash:
        raise ValueError("stage input is not the previous output")
    source = inside(root, run["sourcePath"])
    if stage == "source_scan":
        snapshot = run_file(root, run["runId"], data.get("sourceSnapshotPath", ""))
        if data.get("sourceSha256") != digest(snapshot):
            raise ValueError("source snapshot hash mismatch")
        output = digest(snapshot)
    elif stage == "transcription_normalization":
        corrected = run_file(root, run["runId"], data.get("correctedPath", ""))
        if not corrected.is_file() or not corrected.read_text(encoding="utf-8").strip():
            raise ValueError("corrected Markdown is missing")
        if not isinstance(data.get("changes"), list):
            raise ValueError("normalization change list missing")
        reflow = data.get("paragraphReflow")
        if not isinstance(reflow, dict):
            raise ValueError("paragraphReflow record missing")
        required_reflow = {"changed", "beforeParagraphCount", "afterParagraphCount", "paragraphs", "boundaries"}
        if set(reflow) < required_reflow or not isinstance(reflow.get("changed"), bool):
            raise ValueError("paragraphReflow fields missing")
        if any(not isinstance(reflow.get(k), int) or reflow[k] < 0 for k in ("beforeParagraphCount", "afterParagraphCount")):
            raise ValueError("paragraphReflow paragraph counts invalid")
        if not isinstance(reflow.get("boundaries"), list):
            raise ValueError("paragraphReflow boundaries invalid")
        paragraphs = reflow.get("paragraphs")
        if not isinstance(paragraphs, list) or len(paragraphs) != reflow["afterParagraphCount"]:
            raise ValueError("paragraphReflow paragraphs do not cover corrected Markdown")
        expected_numbers = list(range(1, len(paragraphs) + 1))
        actual_numbers = []
        for item in paragraphs:
            if not isinstance(item, dict) or not isinstance(item.get("paragraph"), int) or not item.get("role") or not item.get("boundary"):
                raise ValueError("paragraphReflow paragraph entry invalid")
            actual_numbers.append(item["paragraph"])
        if actual_numbers != expected_numbers:
            raise ValueError("paragraphReflow paragraph numbering is not sequential")
        if reflow["afterParagraphCount"] != markdown_paragraph_count(corrected.read_text(encoding="utf-8")):
            raise ValueError("paragraphReflow afterParagraphCount differs from corrected Markdown")
        corrected_text = corrected.read_text(encoding="utf-8")
        if run.get("paragraphQualityRequired") and len(corrected_text) >= 800 and reflow["afterParagraphCount"] < 2:
            justification = reflow.get("singleParagraphJustification")
            if not isinstance(justification, str) or not justification.strip():
                raise ValueError("long single-paragraph source requires paragraph reflow or explicit justification")
        if reflow["changed"] and not reflow["boundaries"]:
            raise ValueError("changed paragraph reflow requires boundaries")
        if not reflow["changed"] and reflow["boundaries"]:
            raise ValueError("unchanged paragraph reflow must have empty boundaries")
        if digest(corrected) != previous_hash and not data["changes"]:
            raise ValueError("corrected text changed without normalization diff")
        if digest(corrected) != previous_hash:
            source_artifact = prior_stage(root, run, "source_scan")
            snapshot = run_file(root, run["runId"], source_artifact["sourceSnapshotPath"])
            if source.suffix.lower() not in {".md", ".txt"}:
                snapshot = run_file(root, run["runId"], data.get("extractedTextPath", ""))
            diff = "".join(difflib.unified_diff(snapshot.read_text(encoding="utf-8").splitlines(keepends=True), corrected.read_text(encoding="utf-8").splitlines(keepends=True), fromfile="source", tofile="corrected"))
            diff_file = run_file(root, run["runId"], data.get("diffPath", ""))
            if diff_file.read_text(encoding="utf-8") != diff:
                raise ValueError("normalization diff does not match source and corrected bytes")
        if corrected.suffix.lower() != ".md":
            raise ValueError("corrected text must be Markdown")
        normalized = inside(root, data.get("normalizedSourcePath", run["sourcePath"]))
        if normalized.suffix.lower() != ".md":
            raise ValueError("normalized source must be Markdown")
        if not run.get("normalizationWritebackRequired"):
            if normalized != corrected and normalized != source:
                raise ValueError("without source writeback, normalized source must be the run-local corrected Markdown")
        elif normalized.parent != source.parent or normalized.stem != source.stem:
            raise ValueError("normalized source must be same-name Markdown beside original")
        if run.get("normalizationWritebackRequired"):
            if data.get("sourceWriteback") is not True or data.get("sourceWritebackPath") != run["sourcePath"]:
                raise ValueError("normalized source writeback evidence missing")
            if digest(source) != digest(corrected) or data.get("sourceWritebackSha256") != digest(source):
                raise ValueError("source writeback hash does not match corrected Markdown")
        output = digest(corrected)
    elif stage == "misconception_candidate_identification":
        candidates = data.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("candidate list missing")
        if run.get("candidateEnumerationRequired"):
            coverage = data.get("candidateCoverage")
            if not isinstance(coverage, dict) or coverage.get("exhaustiveScan") is not True or coverage.get("noMoreCandidatesConfirmed") is not True or not isinstance(coverage.get("reviewedSegments"), list) or not coverage.get("reviewedSegments"):
                raise ValueError("candidate enumeration coverage is incomplete")
        corrected = run_file(root, run["runId"], data.get("correctedPath", ""))
        if digest(corrected) != previous_hash:
            raise ValueError("candidate source is not current corrected text")
        body = corrected.read_text(encoding="utf-8")
        if len({c.get("candidateId") for c in candidates}) != len(candidates):
            raise ValueError("duplicate candidate IDs")
        for candidate in candidates:
            if not all(candidate.get(k) for k in ("candidateId", "mistakenBelief", "sourceEvidence", "problemEvidence", "sourceSpan")):
                raise ValueError("candidate lacks source-grounded judgment")
            if candidate["sourceEvidence"] not in body or candidate["problemEvidence"] not in body:
                raise ValueError("candidate evidence not found in corrected source")
            quality = candidate.get("viewpointQuality")
            evidence = candidate.get("sourceEvidenceMeta") or candidate.get("sourceEvidenceDetails")
            if not isinstance(quality, dict):
                raise ValueError("candidate viewpointQuality missing")
            required_quality = ("isMistakenBelief", "hasErrorObject", "hasErrorJudgment", "hasCausalDirection", "semanticComplete", "sourceClose", "tooCompressed", "isCorrectionConclusion", "sentenceCount", "commaCount", "characterCount")
            if any(key not in quality for key in required_quality):
                raise ValueError("candidate viewpointQuality incomplete")
            if not all(quality[key] is True for key in ("isMistakenBelief", "hasErrorObject", "hasErrorJudgment", "hasCausalDirection", "semanticComplete", "sourceClose")) or quality["tooCompressed"] is not False or quality["isCorrectionConclusion"] is not False or quality["sentenceCount"] != 1 or quality["characterCount"] > 24:
                raise ValueError("candidate viewpointQuality failed")
            if run.get("viewpointPatternRequired"):
                allowed_patterns = {"把A当成B", "以为A就能B", "只要A就会B", "A本身就等于B", "做了A就不需要B", "把短期结果当长期方法", "否定性错误判断", "条件错配判断", "因果倒置判断", "主体归因错误"}
                if candidate.get("viewpointPattern") not in allowed_patterns or not candidate.get("patternSelectionReason"):
                    raise ValueError("viewpoint pattern selection is missing")
            if not isinstance(evidence, dict) or not evidence.get("isContinuous") or not evidence.get("contextComplete"):
                raise ValueError("candidate sourceEvidence continuity or context completeness missing")
            roles = evidence.get("roles")
            if not isinstance(roles, dict) or roles.get("cognitive") is not True or roles.get("problem") is not True:
                raise ValueError("candidate sourceEvidence must cover cognitive and problem evidence")
            if run.get("evidenceSpanRequired"):
                spans = evidence.get("evidenceSpans")
                if not isinstance(spans, list) or len(spans) < 2:
                    raise ValueError("candidate evidence spans missing")
                expected = {"sourceEvidence": candidate["sourceEvidence"], "problemEvidence": candidate["problemEvidence"]}
                actual = []
                for span in spans:
                    if not isinstance(span, dict) or span.get("kind") not in expected:
                        raise ValueError("candidate evidence span kind invalid")
                    start, end = span.get("start"), span.get("end")
                    if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(body):
                        raise ValueError("candidate evidence span bounds invalid")
                    if body[start:end] != expected[span["kind"]]:
                        raise ValueError("candidate evidence span text mismatch")
                    actual.append((start, end, span["kind"]))
                if {kind for _, _, kind in actual} != set(expected) or actual != sorted(actual):
                    raise ValueError("candidate evidence spans are not ordered")
                if actual[0][1] > actual[1][0]:
                    raise ValueError("candidate evidence spans overlap")
        output = digest(artifact)
    elif stage == "five_gate_judgment":
        results = data.get("results")
        if not isinstance(results, list) or not all(isinstance(r.get("gates"), dict) and set(r["gates"]) == {"errorObject", "errorContent", "errorScene", "internalCorrection", "independentCard"} and all(isinstance(v, bool) for v in r["gates"].values()) for r in results):
            raise ValueError("five-gate results missing")
        candidate_file = run_file(root, run["runId"], data.get("candidatesPath", ""))
        candidates = read_json(candidate_file).get("candidates", [])
        if digest(candidate_file) != previous_hash:
            raise ValueError("five gates not bound to current candidates")
        if {r.get("candidateId") for r in results} != {c.get("candidateId") for c in candidates}:
            raise ValueError("five-gate coverage differs from candidates")
        output = digest(artifact)
    elif stage == "intra_document_deduplication":
        if not isinstance(data.get("results"), list) or not data.get("judgmentPath"):
            raise ValueError("intra-document comparison missing")
        if digest(run_file(root, run["runId"], data["judgmentPath"])) != previous_hash:
            raise ValueError("intra-document comparison not bound to judgments")
        passed = {r["candidateId"] for r in prior_stage(root, run, "five_gate_judgment")["results"] if all(r["gates"].values())}
        if {r.get("candidateId") for r in data["results"]} != passed:
            raise ValueError("intra-document results must cover passed candidates")
        if any(r.get("disposition") not in {"keep", "merge", "reject"} for r in data["results"]):
            raise ValueError("invalid intra-document disposition")
        output = digest(artifact)
    elif stage in {"global_deduplication_pre", "global_deduplication_final"}:
        index = run_file(root, run["runId"], data.get("indexSnapshotPath", ""))
        if data.get("indexSha256") != digest(index) or not isinstance(data.get("results"), list):
            raise ValueError("global dedup index snapshot or comparisons missing")
        if any(r.get("dedupStatus") == "uncertain" for r in data["results"]):
            raise ValueError("uncertain deduplication requires pause")
        if any(r.get("dedupStatus") not in {"new", "related", "duplicate"} or not r.get("candidateId") or not r.get("reason") for r in data["results"]):
            raise ValueError("global deduplication results incomplete")
        if stage == "global_deduplication_pre":
            kept = {r["candidateId"] for r in prior_stage(root, run, "intra_document_deduplication")["results"] if r["disposition"] == "keep"}
            if {r["candidateId"] for r in data["results"]} != kept:
                raise ValueError("global pre-dedup does not cover kept candidates")
        if stage == "global_deduplication_final" and data.get("result") != "passed":
            raise ValueError("final deduplication not passed")
        if stage == "global_deduplication_final":
            review = prior_stage(root, run, "independent_review")
            if review.get("reviewStatus") != "approved" or any(c.get("decision") != "approved" for c in review.get("cards", [])):
                raise ValueError("final deduplication cannot proceed after a rejected or partial review")
            accepted = {r["candidateId"] for r in prior_stage(root, run, "global_deduplication_pre")["results"] if r["dedupStatus"] in {"new", "related"}}
            if {r["candidateId"] for r in data["results"]} != accepted or any(r["dedupStatus"] == "duplicate" for r in data["results"]):
                raise ValueError("final deduplication does not clear all submitted candidates")
        output = digest(artifact)
    elif stage == "card_draft_generation":
        if data.get("generatedFrom") != "source_and_candidates":
            raise ValueError("draft provenance missing")
        cards = data.get("cards")
        if not isinstance(cards, list) or any(digest(run_file(root, run["runId"], c["path"])) != c.get("sha256") for c in cards):
            raise ValueError("draft card hash mismatch")
        allowed = {r["candidateId"] for r in prior_stage(root, run, "global_deduplication_pre")["results"] if r["dedupStatus"] in {"new", "related"}}
        if {c.get("candidateId") for c in cards} != allowed or len(cards) != len(allowed):
            raise ValueError("draft cards do not match accepted candidates")
        for c in cards:
            if "/staging/" in c.get("path", ""):
                raise ValueError("draft cards must be stored in a run-local draft directory; staging is reserved for reviewed polished output")
            old = inside(root, c.get("oldCardPath", "")) if c.get("oldCardPath") else None
            if old and old.exists() and digest(old) == c["sha256"]:
                raise ValueError("draft identical to old card; regenerated draft required")
        output = digest(artifact)
    elif stage == "oral_polish":
        cards = data.get("cards")
        if not isinstance(cards, list):
            raise ValueError("polished cards missing")
        drafts = {c["path"] for c in prior_stage(root, run, "card_draft_generation")["cards"]}
        if {c.get("draftPath") for c in cards} != drafts or len(cards) != len(drafts):
            raise ValueError("polish does not cover draft cards")
        for card in cards:
            draft = run_file(root, run["runId"], card["draftPath"])
            polished = run_file(root, run["runId"], card["polishedPath"])
            if draft == polished or draft.parent == polished.parent:
                raise ValueError("polished card must be an independent output")
            if "/staging/" in card.get("draftPath", "") or "/staging/" in card.get("polishedPath", ""):
                raise ValueError("draft and polished must remain run-local; staging is reserved for reviewed polished output")
            if digest(draft) != card.get("draftSha256") or digest(polished) != card.get("polishedSha256"):
                raise ValueError("polish card hash mismatch")
            a, b = draft.read_text(encoding="utf-8"), polished.read_text(encoding="utf-8")
            if "## 误区场景\n" not in a or "## 原文依据\n" not in a or "## 误区场景\n" not in b or "## 原文依据\n" not in b:
                raise ValueError("card sections missing")
            a_head, a_tail = a.split("## 误区场景\n", 1); b_head, b_tail = b.split("## 误区场景\n", 1)
            if a_head != b_head or a_tail.split("## 原文依据\n", 1)[1] != b_tail.split("## 原文依据\n", 1)[1]:
                raise ValueError("polish altered frozen card fields")
            if a == b and not card.get("unchangedReason"):
                raise ValueError("unchanged polish lacks reason for reviewer")
            if a != b and card.get("unchangedReason"):
                raise ValueError("changed polish cannot claim unchanged")
            if a != b and not card.get("changeExplanation"):
                raise ValueError("polish change explanation missing")
            if run.get("oralPolishContract") == "dialogue-v2":
                quality = card.get("oralPolishQuality") or data.get("oralPolishQuality")
                if not isinstance(quality, dict):
                    raise ValueError("dialogue-v2 oralPolishQuality missing")
                required = ("changed", "directAddress", "dialogueFeeling", "naturalConnectors", "sentenceRhythmVaried", "reportToneRemoved", "paragraphCount")
                if any(key not in quality for key in required):
                    raise ValueError("dialogue-v2 oralPolishQuality fields missing")
                if a != b and quality.get("changed") is not True:
                    raise ValueError("dialogue-v2 polish must declare an actual rewrite")
                if a == b and not (quality.get("unchangedApproved") is True and card.get("unchangedReason")):
                    raise ValueError("dialogue-v2 unchanged polish requires explicit reviewer approval")
                if any(quality.get(key) is not True for key in ("directAddress", "dialogueFeeling", "naturalConnectors", "sentenceRhythmVaried", "reportToneRemoved")):
                    raise ValueError("dialogue-v2 oral quality gate failed")
                if not isinstance(quality.get("paragraphCount"), int) or not 2 <= quality["paragraphCount"] <= 4:
                    raise ValueError("dialogue-v2 polished scene must contain 2-4 paragraphs")
        output = digest(artifact)
    elif stage == "independent_review":
        request = run_file(root, run["runId"], data.get("reviewRequestPath", ""))
        if digest(request) != data.get("reviewRequestSha256"):
            raise ValueError("frozen review request missing or changed")
        request_data = read_json(request)
        polish_cards = prior_stage(root, run, "oral_polish")["cards"]
        requested = {c.get("path"): c.get("sha256") for c in request_data.get("cards", [])}
        if request_data.get("runId") != run["runId"] or request_data.get("sourcePath") != run["sourcePath"] or request_data.get("correctedSha256") != next(r["evidence"]["outputSha256"] for r in run["stageReceipts"] if r["stage"] == "transcription_normalization") or requested != {c["polishedPath"]: c["polishedSha256"] for c in polish_cards}:
            raise ValueError("review request does not freeze current source and polished cards")
        if data.get("reviewStatus") not in {"approved", "rejected", "partial"} or data.get("reviewMode") not in {"subagent", "fresh_context"} or not data.get("reviewerInvocationId") or not data.get("reviewerId") or data.get("reviewerId") == run.get("producerId"):
            raise ValueError("independent review provenance missing")
        if data.get("reviewTool") not in {"multi_agent_v1", "isolated_context_runner"}:
            raise ValueError("review must identify an isolated reviewer tool")
        transcript = run_file(root, run["runId"], data.get("reviewerTranscriptPath", ""))
        if digest(transcript) != data.get("reviewerTranscriptSha256") or data["reviewerInvocationId"] not in transcript.read_text(encoding="utf-8"):
            raise ValueError("reviewer response transcript is missing or changed")
        transcript_data = read_json(transcript)
        invocation = transcript_data.get("invocation")
        if not isinstance(invocation, dict):
            raise ValueError("reviewer transcript lacks runtime invocation envelope")
        if invocation.get("id") != data["reviewerInvocationId"] or invocation.get("tool") != data["reviewTool"]:
            raise ValueError("reviewer invocation envelope does not match review report")
        if invocation.get("requestSha256") != digest(request):
            raise ValueError("reviewer invocation is not bound to the frozen request")
        response_hash = hashlib.sha256(json.dumps(transcript_data.get("response", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest().upper()
        if invocation.get("responseSha256") != response_hash:
            raise ValueError("reviewer invocation response hash is invalid")
        if not invocation.get("startedAt") or not invocation.get("completedAt"):
            raise ValueError("reviewer invocation timestamps are missing")
        response = transcript_data.get("response", {})
        if transcript_data.get("agentId") != data["reviewerInvocationId"] or transcript_data.get("tool") != data["reviewTool"] or response.get("reviewStatus") != data["reviewStatus"] or response.get("cards") != data.get("cards"):
            raise ValueError("review report differs from reviewer tool response")
        if not isinstance(data.get("cards"), list):
            raise ValueError("per-card review missing")
        polished_paths = {c["polishedPath"] for c in prior_stage(root, run, "oral_polish")["cards"]}
        if {c.get("polishedPath") for c in data["cards"]} != polished_paths or len(data["cards"]) != len(polished_paths):
            raise ValueError("review does not cover all polished cards")
        expected_decision = "approved" if data.get("reviewStatus") == "approved" else None
        decisions = []
        for card in data["cards"]:
            path = run_file(root, run["runId"], card["polishedPath"])
            if not card.get("cardId") or digest(path) != card.get("reviewedCardSha256") or card.get("decision") not in {"approved", "rejected"} or (expected_decision and card.get("decision") != expected_decision) or not card.get("reason") or not card.get("sourceEvidenceSpan"):
                raise ValueError("reviewed card hash or judgment invalid")
            decisions.append(card.get("decision"))
            if card.get("unchangedPolish") and not card.get("unchangedPolishAccepted"):
                raise ValueError("unchanged polish lacks reviewer acceptance")
            if run.get("oralPolishContract") == "dialogue-v2":
                evidence = card.get("oralSceneEvidence") or data.get("oralSceneEvidence")
                if not isinstance(evidence, dict):
                    raise ValueError("dialogue-v2 oralSceneEvidence missing")
                required = ("directAddress", "dialogueFeeling", "naturalConnectors", "sentenceRhythmVaried", "reportToneRemoved", "meaningPreserved", "actualRewriteCompleted")
                if any(key not in evidence or not isinstance(evidence.get(key), bool) for key in required):
                    raise ValueError("dialogue-v2 oral scene review evidence is incomplete")
        if data.get("reviewStatus") == "approved" and any(decision != "approved" for decision in decisions):
            raise ValueError("approved review cannot contain rejected cards")
        if data.get("reviewStatus") == "rejected" and (not decisions or any(decision != "rejected" for decision in decisions)):
            raise ValueError("rejected review must reject every reviewed card")
        if data.get("reviewStatus") == "partial" and not decisions:
            raise ValueError("partial review must contain card decisions")
        if not data["cards"] and not data.get("zeroCardReason"):
            raise ValueError("zero-card review reason missing")
        output = digest(artifact)
    else:
        raise ValueError(f"unsupported stage: {stage}")
    return {"artifactPath": artifact.relative_to(root).as_posix(), "artifactSha256": digest(artifact), "inputSha256": previous_hash, "outputSha256": output}
