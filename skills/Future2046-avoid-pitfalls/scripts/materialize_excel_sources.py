#!/usr/bin/env python3
"""Materialize one Markdown source document per non-empty Excel copy row."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from pipeline_contract import workspace_path


TEXT_ALIASES = ("作品文案", "文案", "作品内容", "全文")
TEXT_ONLY_HEADERS = set(TEXT_ALIASES) | {"全文摘要", "内容摘要", "摘要"}
LINK_ALIASES = ("作品链接", "选题链接", "链接", "视频链接")
TITLE_ALIASES = ("作品标题", "标题", "选题")
SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".xlsm"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def canonical(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def text(value: Any) -> str:
    value = canonical(value)
    return "" if value is None else str(value).strip()


def safe_cell(value: Any) -> str:
    return text(value).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def header_index(headers: list[str], aliases: Iterable[str]) -> int | None:
    normalized = {h.strip(): i for i, h in enumerate(headers) if h.strip()}
    for alias in aliases:
        if alias in normalized:
            return normalized[alias]
    return None


def rows_from_xlsx(path: Path) -> list[tuple[str, list[str], list[list[Any]]]]:
    try:
        import openpyxl
    except ImportError as exc:
        raise RuntimeError("读取 .xlsx 需要 openpyxl") from exc
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result = []
    for sheet in book.worksheets:
        rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        if rows:
            result.append((sheet.title, [text(v) for v in rows[0]], rows[1:]))
    return result


def rows_from_xls(path: Path) -> list[tuple[str, list[str], list[list[Any]]]]:
    try:
        import xlrd
    except ImportError as exc:
        raise RuntimeError("读取旧式 .xls 需要 xlrd") from exc
    book = xlrd.open_workbook(str(path), on_demand=True)
    result = []
    for sheet in book.sheets():
        headers = [text(v) for v in sheet.row_values(0)] if sheet.nrows else []
        rows = [sheet.row_values(i) for i in range(1, sheet.nrows)]
        result.append((sheet.name, headers, rows))
    return result


def read_workbook(path: Path) -> list[tuple[str, list[str], list[list[Any]]]]:
    magic = path.read_bytes()[:8]
    if magic.startswith(b"PK"):
        return rows_from_xlsx(path)
    if magic.startswith(b"\xD0\xCF\x11\xE0"):
        return rows_from_xls(path)
    raise RuntimeError("不是可识别的 OOXML 或 OLE Excel 文件")


def existing_records(log_path: Path) -> dict[tuple[str, str, int], dict]:
    records: dict[tuple[str, str, int], dict] = {}
    if not log_path.exists():
        return records
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        key = (item.get("sourceExcel", ""), item.get("sheet", ""), int(item.get("sourceRow", 0)))
        records[key] = item
    return records


def next_ordinal(records: dict[tuple[str, str, int], dict], excel_rel: str) -> int:
    values = []
    for item in records.values():
        if item.get("sourceExcel") == excel_rel:
            match = re.search(r"（(\d+)）\.md$", item.get("generatedPath", ""))
            if match:
                values.append(int(match.group(1)))
    return max(values, default=0) + 1


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        else:
            rendered = json.dumps("" if value is None else str(value), ensure_ascii=False)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def markdown(excel_rel: str, sheet: str, row_number: int, row_index: int,
             fingerprint: str, headers: list[str], values: list[Any],
             link: str, title: str, copy: str) -> str:
    metadata = {
        "source_type": "excel_row",
        "source_excel": excel_rel,
        "source_sheet": sheet,
        "source_row": row_number,
        "source_row_index": row_index,
        "source_row_fingerprint": fingerprint,
        "source_link": link,
        "source_title": title,
        "text_field": "作品文案",
        "transcription_normalized": False,
    }
    table = ["## 来源字段", "", "| 字段 | 值 |", "|---|---|"]
    for i, header in enumerate(headers):
        if not header or header in TEXT_ONLY_HEADERS:
            continue
        value = values[i] if i < len(values) else ""
        table.append(f"| {safe_cell(header)} | {safe_cell(value)} |")
    return frontmatter(metadata) + "\n\n# " + (title or Path(excel_rel).stem) + "\n\n" + "\n".join(table) + "\n\n## 全文\n\n" + copy.rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--source-root", help="override source_root from workspace.yaml")
    parser.add_argument("--excel")
    parser.add_argument("--report")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    workspace = Path(args.workspace).resolve()
    root = (workspace / args.source_root).resolve() if args.source_root else workspace_path(workspace, "source_root")
    files = [workspace / args.excel.replace("/", "\\")] if args.excel else sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES)
    records_path = workspace_path(workspace, "record_root") / "excel-materialization-log.jsonl"
    previous = existing_records(records_path)
    events: list[dict] = []
    report = {"excelCount": len(files), "sheetCount": 0, "materializedCount": 0, "unchangedCount": 0, "changedCount": 0, "emptyTextRows": 0, "failedCount": 0, "conflictCount": 0, "unsupportedSheetCount": 0, "events": events}
    pending_writes: list[tuple[Path, bytes]] = []
    for path in files:
        try:
            excel_rel = path.relative_to(workspace).as_posix()
            sheets = read_workbook(path)
            report["sheetCount"] += len(sheets)
            ordinal = next_ordinal(previous, excel_rel)
            for sheet, headers, data_rows in sheets:
                text_col = header_index(headers, TEXT_ALIASES)
                link_col = header_index(headers, LINK_ALIASES)
                title_col = header_index(headers, TITLE_ALIASES)
                if text_col is None:
                    report["unsupportedSheetCount"] += 1
                    events.append({"sourceExcel": excel_rel, "sheet": sheet, "status": "unsupported_sheet"})
                    continue
                for row_index, values in enumerate(data_rows, 1):
                    row_number = row_index + 1
                    normalized = [canonical(v) for v in values]
                    copy = text(values[text_col] if text_col < len(values) else "")
                    key = (excel_rel, sheet, row_number)
                    if not copy:
                        report["emptyTextRows"] += 1
                        events.append({"sourceExcel": excel_rel, "sheet": sheet, "sourceRow": row_number, "status": "empty_text"})
                        continue
                    fingerprint = sha256_bytes(json.dumps({"sourceExcel": excel_rel, "sheet": sheet, "sourceRow": row_number, "values": normalized}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))
                    old = previous.get(key)
                    if old and old.get("rowFingerprint") == fingerprint and (workspace / old.get("generatedPath", "")).is_file():
                        report["unchangedCount"] += 1
                        event = dict(old); event.update({"status": "unchanged", "processedAt": datetime.now().astimezone().isoformat(timespec="seconds")}); events.append(event); continue
                    if old and old.get("generatedPath"):
                        generated = workspace / old["generatedPath"]
                        status = "changed"
                        report["changedCount"] += 1
                    else:
                        generated = path.parent / f"{path.stem}（{ordinal}）.md"
                        ordinal += 1
                        status = "materialized"
                        report["materializedCount"] += 1
                    if generated.exists() and (not old or old.get("generatedPath") != generated.relative_to(workspace).as_posix()):
                        report["conflictCount"] += 1
                        events.append({"sourceExcel": excel_rel, "sheet": sheet, "sourceRow": row_number, "status": "conflict", "generatedPath": generated.relative_to(workspace).as_posix()}); continue
                    link = text(values[link_col]) if link_col is not None and link_col < len(values) else ""
                    title = text(values[title_col]) if title_col is not None and title_col < len(values) else ""
                    body = markdown(excel_rel, sheet, row_number, row_index, fingerprint, headers, values, link, title, copy).encode("utf-8")
                    pending_writes.append((generated, body))
                    events.append({"sourceExcel": excel_rel, "sheet": sheet, "sourceRow": row_number, "generatedPath": generated.relative_to(workspace).as_posix(), "rowFingerprint": fingerprint, "sourceExcelSha256": sha256_bytes(path.read_bytes()), "status": status, "processedAt": datetime.now().astimezone().isoformat(timespec="seconds")})
        except Exception as exc:
            report["failedCount"] += 1
            events.append({"sourceExcel": str(path), "status": "failed", "error": str(exc)})
    if not args.dry_run:
        for path, body in pending_writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        records_path.parent.mkdir(parents=True, exist_ok=True)
        with records_path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    report_path = workspace / args.report.replace("/", "\\") if args.report else workspace_path(workspace, "record_root") / "excel-materialization-report.json"
    if not args.dry_run:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "events"}, ensure_ascii=False))
    return 1 if report["failedCount"] or report["conflictCount"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
