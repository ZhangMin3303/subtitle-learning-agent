from __future__ import annotations

import argparse
import json
from pathlib import Path

from ass_parser import PROJECT_ROOT, save_json


DEFAULT_INPUT = PROJECT_ROOT / "data" / "parsed" / "asr_smoke_test.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "asr_draft_subtitles.json"


def load_asr_report(path: Path) -> dict:
    """Load an ASR quality/evaluation report."""
    return json.loads(path.read_text(encoding="utf-8"))


def pick_model_report(report: dict, model_name: str | None) -> dict:
    """Pick one model report from an ASR evaluation file."""
    model_reports = report.get("model_reports", [report] if "results" in report else [])
    if not model_reports:
        raise ValueError("No model_reports found in ASR report.")

    if model_name is None:
        return model_reports[0]

    for model_report in model_reports:
        if model_report.get("model") == model_name:
            return model_report

    raise ValueError(f"Model not found in report: {model_name}")


def build_draft_records(report: dict, model_name: str | None) -> list[dict]:
    """Convert ASR evaluation results into draft subtitle records."""
    model_report = pick_model_report(report, model_name)
    records = []

    for result in model_report.get("results", []):
        records.append(
            {
                "index": int(result["source_index"]),
                "start": result["start"],
                "end": result["end"],
                "duration_ms": result["duration_ms"],
                "japanese_text_asr": result["asr_text"],
                "japanese_text_corrected": "",
                "chinese_text": result["chinese_text"],
                "audio_file_name": result["audio_file_name"],
                "source_index": result["source_index"],
                "source_type": "asr",
                "asr_model": model_report.get("model"),
                "asr_device": model_report.get("device"),
                "asr_compute_type": model_report.get("compute_type"),
                "mean_avg_logprob": result.get("mean_avg_logprob"),
                "max_no_speech_prob": result.get("max_no_speech_prob"),
                "quality_flags": result.get("quality_flags", []),
                "review_status": "pending",
                "needs_human_review": True,
                "notes": "",
            }
        )

    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Build draft Japanese subtitles from ASR output.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="ASR report JSON path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Draft subtitle JSON path.")
    parser.add_argument("--model", default=None, help="Model name to extract from the ASR report.")
    args = parser.parse_args()

    report = load_asr_report(args.input)
    draft_records = build_draft_records(report, args.model)
    save_json(draft_records, args.output)
    print(f"Built {len(draft_records)} ASR draft subtitle records.")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
