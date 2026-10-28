from __future__ import annotations
import argparse
import json
from pathlib import Path
from ass_parser import PROJECT_ROOT, save_json
from review_policy import review_rows, apply_ocr
def main() -> None:
    p=argparse.ArgumentParser(description="Apply approved OCR edits to a freshly rebuilt ASR review output.")
    p.add_argument("--input", type=Path, default=PROJECT_ROOT/"data/parsed/asr_reviewed_subtitles.json")
    p.add_argument("--review", type=Path, default=PROJECT_ROOT/"data/review/hardsub_ocr_review.csv")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT/"data/parsed/reviewed_subtitles.json")
    a=p.parse_args()
    if a.input.resolve() == a.output.resolve():
        p.error("Keep ASR review input separate; rebuild both stages to revoke an OCR approval.")
    save_json(apply_ocr(json.loads(a.input.read_text(encoding="utf-8")), review_rows(a.review)), a.output)
if __name__ == "__main__":
    main()
