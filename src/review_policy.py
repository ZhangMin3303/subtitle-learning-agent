"""A non-empty edit and explicit approval are both required for promotion."""
from __future__ import annotations
import csv
from pathlib import Path
APPROVAL_VALUES = {"approved", "yes", "true", "1"}

def review_rows(path: Path) -> dict[int, dict]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for row in rows:
        index = int(row["index"])
        if index in result:
            raise ValueError(f"Duplicate review index: {index}")
        result[index] = row
    return result

def approved(value: object, text: object) -> bool:
    return str(value).strip().lower() in APPROVAL_VALUES and bool(str(text or "").strip())

def apply_asr(records: list[dict], rows: dict[int, dict]) -> list[dict]:
    output = []
    for original in records:
        record = dict(original)
        row = rows.get(int(record["index"]), {})
        corrected = str(row.get("japanese_text_corrected", "")).strip()
        ok = approved(row.get("review_status"), corrected)
        record.update(japanese_text_corrected=corrected,
            japanese_text_final=corrected if ok else str(record.get("japanese_text_asr", "")),
            review_status="approved" if ok else "pending", needs_human_review=not ok,
            review_notes=str(row.get("notes", "")), review_source="asr" if ok else "")
        output.append(record)
    return output

def apply_ocr(records: list[dict], rows: dict[int, dict]) -> list[dict]:
    # Always rebuild from the fresh ASR review output, never from a previous OCR output.
    output = []
    for original in records:
        record = dict(original)
        row = rows.get(int(record["index"]), {})
        corrected = str(row.get("corrected_japanese_text", "")).strip()
        record["ocr_edit_draft"] = corrected
        if approved(row.get("approved"), corrected):
            record.update(japanese_text_final=corrected, japanese_text_corrected=corrected,
                source_type="hardsub_ocr_reviewed", review_source="ocr",
                review_status="approved", needs_human_review=False,
                ocr_review_notes=str(row.get("notes", "")))
        output.append(record)
    return output
