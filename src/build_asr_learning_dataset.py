from __future__ import annotations
import argparse
import json
from collections import Counter
from pathlib import Path
from ass_parser import PROJECT_ROOT, save_json
from review_policy import approved
def build_learning_dataset(records: list[dict]) -> list[dict]:
    dataset=[]
    for record in records:
        reviewed=approved(record.get("review_status"), record.get("japanese_text_corrected"))
        fixture=record.get("source_type") == "demo_fixture"
        quality="human_reviewed" if reviewed else ("demo_fixture" if fixture else "asr_draft")
        dataset.append({**record, "index": int(record["index"]),
            "japanese_text": str(record.get("japanese_text_final", "")),
            "language_type": "bilingual_preview", "content_type": "dialogue",
            "source_type": record.get("source_type", "asr"), "source_quality": quality,
            "review_status": "approved" if reviewed else "pending", "needs_human_review": not reviewed,
            "ready_for_nlp": bool(record.get("japanese_text_final")),
            "nlp_reliability": "reviewed_text_only" if reviewed else "draft"})
    return dataset
def build_summary(dataset: list[dict]) -> dict:
    return {"record_count": len(dataset),
        "source_quality_counts": dict(Counter(r["source_quality"] for r in dataset)),
        "review_status_counts": dict(Counter(r["review_status"] for r in dataset)),
        "needs_human_review_count": sum(r["needs_human_review"] for r in dataset),
        "note": "Human-reviewed describes the selected text only, not model or NLP accuracy."}
def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=PROJECT_ROOT/"data/parsed/reviewed_subtitles.json")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT/"data/parsed/asr_learning_dataset.json")
    p.add_argument("--summary", type=Path, default=PROJECT_ROOT/"data/parsed/asr_learning_summary.json")
    a=p.parse_args()
    dataset=build_learning_dataset(json.loads(a.input.read_text(encoding="utf-8")))
    save_json(dataset,a.output); save_json(build_summary(dataset),a.summary)
if __name__ == "__main__":
    main()
