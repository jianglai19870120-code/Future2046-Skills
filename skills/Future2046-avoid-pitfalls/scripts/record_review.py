#!/usr/bin/env python3
"""Persist an isolated reviewer response inside the current run only."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline_contract import digest, read_json, record_path, run_file, workspace_path, workspace_rel_path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def stamp() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="microseconds")


def dump(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest().upper()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--review-json", required=True,
                    help="当前 run review/ 下的审核响应 JSON")
    args = ap.parse_args()
    try:
        root = Path(args.workspace).resolve()
        records = workspace_path(root, "record_root")
        run_dir = records / "runs" / args.run_id
        run = read_json(run_dir / "run.json")
        if run.get("status") != "in_progress":
            raise ValueError("当前 run 不是 in_progress")
        incoming = record_path(root, args.review_json, run_id=args.run_id, subdirectory="review")
        response_envelope = read_json(incoming)
        oral_receipt = next(r for r in run["stageReceipts"] if r["stage"] == "oral_polish")
        norm_receipt = next(r for r in run["stageReceipts"] if r["stage"] == "transcription_normalization")
        oral = read_json(run_file(root, args.run_id, oral_receipt["evidence"]["artifactPath"]))
        request = {"runId": args.run_id, "sourcePath": run["sourcePath"],
                   "correctedSha256": norm_receipt["evidence"]["outputSha256"],
                   "cards":[{"cardId": c["cardId"], "path": c["polishedPath"],
                             "sha256": c["polishedSha256"]} for c in oral["cards"]]}
        review_dir = run_dir / "review"
        review_dir.mkdir(parents=True, exist_ok=True)
        request_path = review_dir / "review-request.json"
        dump(request_path, request)
        request_sha = digest(request_path)
        response = response_envelope.get("response", response_envelope)
        invocation = dict(response_envelope.get("invocation") or {})
        invocation.setdefault("id", response_envelope.get("reviewerInvocationId"))
        invocation.setdefault("tool", response_envelope.get("reviewTool"))
        invocation.setdefault("requestSha256", request_sha)
        invocation.setdefault("responseSha256", canonical_hash(response))
        invocation.setdefault("startedAt", stamp())
        invocation.setdefault("completedAt", stamp())
        transcript = {"runId": args.run_id, "sourcePath": run["sourcePath"],
                      "reviewerId": response_envelope.get("reviewerId"),
                      "agentId": response_envelope.get("reviewerInvocationId") or response_envelope.get("reviewerId"),
                      "tool": response_envelope.get("reviewTool"),
                      "invocation": invocation,
                      "response": response,
                      "sourceOfReview": "independent subagent review recorded by record_review.py"}
        transcript_path = review_dir / "reviewer-transcript.json"
        dump(transcript_path, transcript)
        transcript_sha = digest(transcript_path)
        oral_path = run_file(root, args.run_id, oral_receipt["evidence"]["artifactPath"])
        report = {"runId": args.run_id, "sourcePath": run["sourcePath"],
                  "stage": "independent_review", "pipelineVersion": "v4-artifact",
                  "inputSha256": digest(oral_path),
                  "reviewRequestPath": workspace_rel_path(root, request_path),
                  "reviewRequestSha256": request_sha,
                  "reviewerTranscriptPath": workspace_rel_path(root, transcript_path),
                  "reviewerTranscriptSha256": transcript_sha,
                  "reviewTool": response_envelope.get("reviewTool"),
                  "reviewerInvocationId": response_envelope.get("reviewerInvocationId"),
                  "reviewerId": response_envelope.get("reviewerId"),
                  "reviewMode": response_envelope.get("reviewMode"),
                  "reviewStatus": response.get("reviewStatus"),
                  "reviewAttempts": response_envelope.get("reviewAttempts", 1),
                  "cards": response.get("cards", []),
                  "zeroCardReason": response.get("zeroCardReason", ""),
                  "overallDecision": response.get("overallDecision")}
        report_path = review_dir / "independent_review.json"
        dump(report_path, report)
        stage_script = Path(__file__).with_name("stage_receipt.py")
        result = subprocess.run([sys.executable, "-B", str(stage_script), "record",
                                 "--workspace", str(root), "--run-id", args.run_id,
                                 "--stage", "independent_review", "--status", "completed",
                                 "--artifact", workspace_rel_path(root, report_path)],
                                check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result.returncode:
            raise RuntimeError((result.stderr or "").strip() or (result.stdout or "").strip())
        print(result.stdout.strip())
        return 0
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
