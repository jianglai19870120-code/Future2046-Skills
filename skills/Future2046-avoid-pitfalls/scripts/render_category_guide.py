"""Render a staged category guide for visual QA without promoting it."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def record_root(workspace: Path) -> Path:
    for line in (workspace / "workspace.yaml").read_text(encoding="utf-8").splitlines():
        if line.startswith("record_root:"):
            return workspace / line.split(":", 1)[1].strip().strip('"\'')
    raise SystemExit("workspace.yaml 缺少 record_root")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--guide-run-id", required=True)
    args = parser.parse_args()
    ws = Path(args.workspace).resolve()
    root = record_root(ws) / "guides"
    staging = root / "staging" / args.category / args.guide_run_id
    source = staging / f"{args.category}避坑指南.docx"
    output = root / "render" / args.category / args.guide_run_id
    output.mkdir(parents=True, exist_ok=True)
    result = {"category": args.category, "startedAt": datetime.now(timezone.utc).isoformat(), "status": "pending", "errors": []}
    if not source.is_file():
        result["status"] = "fail"
        result["errors"].append("staging DOCX 不存在")
    else:
        soffice = shutil.which("soffice.exe") or shutil.which("soffice")
        if not soffice:
            result["errors"].append("未找到 LibreOffice soffice.exe")
        else:
            completed = subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(output), str(source)], capture_output=True, text=True)
            pdf = output / source.with_suffix(".pdf").name
            if completed.returncode != 0 or not pdf.is_file():
                result["status"] = "fail"
                result["errors"].append((completed.stderr or completed.stdout or "LibreOffice 转换失败").strip())
            else:
                pdftoppm = shutil.which("pdftoppm")
                if pdftoppm:
                    completed = subprocess.run([pdftoppm, "-png", str(pdf), str(output / "page")], capture_output=True, text=True)
                pngs = list(output.glob("*.png"))
                if pngs:
                    result["status"] = "rendered"
                    result["pageCount"] = len(pngs)
                else:
                    result["errors"].append("已生成 PDF，但未找到 PNG 页面")
    (output / "render.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "rendered" else 2


if __name__ == "__main__":
    raise SystemExit(main())
