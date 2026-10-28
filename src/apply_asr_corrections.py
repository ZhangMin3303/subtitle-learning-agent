from __future__ import annotations
import argparse
import json
from pathlib import Path
from ass_parser import PROJECT_ROOT, save_json
from review_policy import review_rows, apply_asr
def main() -> None:
    p=argparse.ArgumentParser(description="Promote explicitly approved, non-empty ASR edits.")
    p.add_argument("--input", type=Path, default=PROJECT_ROOT/"data/parsed/asr_draft_subtitles.json")
    p.add_argument("--review", type=Path, default=PROJECT_ROOT/"data/review/asr_review.csv")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT/"data/parsed/asr_reviewed_subtitles.json")
    a=p.parse_args()
    if a.input.resolve() == a.output.resolve():
        p.error("Keep the draft input separate from reviewed output.")
    save_json(apply_asr(json.loads(a.input.read_text(encoding="utf-8")), review_rows(a.review)), a.output)
if __name__ == "__main__":
    main()
