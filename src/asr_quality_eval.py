from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from asr_smoke_test import load_manifest, transcribe_clip
from ass_parser import PROJECT_ROOT, save_json
from media_utils import relative_path


MANIFEST_INPUT = PROJECT_ROOT / "data" / "parsed" / "audio_clip_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "asr_quality_eval.json"
SUSPICIOUS_PHRASES = [
    "ご視聴ありがとうございました",
    "ありがとうございました",
]


def parse_models(value: str) -> list[str]:
    """Parse comma-separated model names."""
    return [item.strip() for item in value.split(",") if item.strip()]


def score_result(result: dict) -> dict:
    """
    Add lightweight quality flags.

    This is not a true accuracy score because we do not have Japanese ground
    truth yet. It only highlights outputs that deserve human review first.
    """
    text = str(result.get("asr_text", "")).strip()
    segments = result.get("segments", [])
    avg_logprobs = [segment.get("avg_logprob") for segment in segments if segment.get("avg_logprob") is not None]
    no_speech_probs = [segment.get("no_speech_prob") for segment in segments if segment.get("no_speech_prob") is not None]
    mean_logprob = sum(avg_logprobs) / len(avg_logprobs) if avg_logprobs else None
    max_no_speech = max(no_speech_probs) if no_speech_probs else None

    flags = []
    if not text:
        flags.append("empty_text")
    if any(phrase in text for phrase in SUSPICIOUS_PHRASES):
        flags.append("common_asr_hallucination_phrase")
    if mean_logprob is not None and mean_logprob < -1.0:
        flags.append("low_avg_logprob")
    if max_no_speech is not None and max_no_speech > 0.6:
        flags.append("high_no_speech_prob")

    return {
        "mean_avg_logprob": mean_logprob,
        "max_no_speech_prob": max_no_speech,
        "quality_flags": flags,
        "needs_human_review": True,
    }


def transcribe_with_model(model_name: str, clips: list[dict], device: str, compute_type: str, language: str, beam_size: int, allow_download: bool = False) -> dict:
    """Run one model over all clips and return a structured report."""
    from faster_whisper import WhisperModel

    load_start = time.perf_counter()
    model = WhisperModel(model_name, device=device, compute_type=compute_type, local_files_only=not allow_download)
    model_load_seconds = time.perf_counter() - load_start

    results = []
    for clip in clips:
        result = transcribe_clip(model, clip, language, beam_size)
        result.update(score_result(result))
        results.append(result)

    return {
        "model": model_name,
        "device": device,
        "compute_type": compute_type,
        "model_load_seconds": round(model_load_seconds, 3),
        "clip_count": len(results),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare faster-whisper models on the same short audio clips.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_INPUT, help="Audio clip manifest path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="ASR quality report JSON path.")
    parser.add_argument("--models", default="tiny,base", help="Comma-separated faster-whisper model names.")
    parser.add_argument("--device", default="cpu", help="Model device, usually cpu or cuda.")
    parser.add_argument("--compute-type", default="int8", help="Compute type, for example int8 or float16.")
    parser.add_argument("--language", default="ja", help="Expected spoken language.")
    parser.add_argument("--beam-size", type=int, default=1, help="Beam size for decoding.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of clips to evaluate.")
    parser.add_argument("--allow-download", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    clips = manifest.get("clips", [])[: args.limit]
    models = parse_models(args.models)

    started = time.perf_counter()
    model_reports = [
        transcribe_with_model(model_name, clips, args.device, args.compute_type, args.language, args.beam_size, args.allow_download)
        for model_name in models
    ]
    elapsed = time.perf_counter() - started

    report = {
        "status": "ok",
        "source_manifest": relative_path(args.manifest),
        "models": models,
        "device": args.device,
        "compute_type": args.compute_type,
        "language": args.language,
        "beam_size": args.beam_size,
        "clip_count": len(clips),
        "total_seconds": round(elapsed, 3),
        "model_reports": model_reports,
        "note": "This is a no-ground-truth quality review. Human listening is still required.",
    }
    save_json(report, args.output)
    print(f"Evaluated {len(models)} models on {len(clips)} clips.")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
