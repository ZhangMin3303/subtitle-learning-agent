from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ass_parser import PROJECT_ROOT


DEFAULT_INPUT = PROJECT_ROOT / "data" / "parsed" / "asr_draft_subtitles.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "review" / "asr_review.csv"


FIELDNAMES = [
    "index",
    "start",
    "end",
    "audio_file_name",
    "chinese_text",
    "japanese_text_asr",
    "japanese_text_corrected",
    "review_status",
    "quality_flags",
    "notes",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Export ASR draft subtitles to a review CSV.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="ASR draft subtitle JSON path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Review CSV output path.")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly discard an existing review CSV.")
    args = parser.parse_args()
    if args.output.exists() and not args.overwrite:
        raise FileExistsError("Review CSV already exists; use --overwrite only to discard its edits.")

    records = json.loads(args.input.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field, "") for field in FIELDNAMES}
            row["quality_flags"] = "|".join(record.get("quality_flags", []))
            writer.writerow(row)

    print(f"Exported {len(records)} review rows.")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
