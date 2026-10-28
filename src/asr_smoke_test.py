from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ass_parser import PROJECT_ROOT, save_json
from media_utils import project_path, relative_path


MANIFEST_INPUT = PROJECT_ROOT / "data" / "parsed" / "audio_clip_manifest.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "asr_smoke_test.json"


def load_manifest(path: Path) -> dict:
    """Load audio clip metadata produced by extract_audio_clips.py."""
    return json.loads(path.read_text(encoding="utf-8"))


def transcribe_clip(model, clip: dict, language: str, beam_size: int) -> dict:
    """Run ASR for one short audio clip and return structured metadata."""
    start_time = time.perf_counter()
    segments, info = model.transcribe(
        str(project_path(clip["audio_file"])),
        language=language,
        beam_size=beam_size,
        vad_filter=False,
    )
    segment_list = [
        {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
            "avg_logprob": segment.avg_logprob,
            "no_speech_prob": segment.no_speech_prob,
        }
        for segment in segments
    ]
    elapsed = time.perf_counter() - start_time
    text = "".join(segment["text"] for segment in segment_list).strip()

    return {
        "source_index": clip["source_index"],
        "audio_file_name": clip["audio_file_name"],
        "start": clip["start"],
        "end": clip["end"],
        "duration_ms": clip["duration_ms"],
        "chinese_text": clip["chinese_text"],
        "asr_text": text,
        "segments": segment_list,
        "detected_language": info.language,
        "language_probability": info.language_probability,
        "transcribe_seconds": round(elapsed, 3),
        "source_type": "asr",
        "needs_human_review": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a tiny faster-whisper ASR smoke test on short clips.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_INPUT, help="Audio clip manifest path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="ASR result JSON path.")
    parser.add_argument("--model", default="tiny", help="faster-whisper model size or local model path.")
    parser.add_argument("--device", default="cpu", help="Model device, usually cpu or cuda.")
    parser.add_argument("--compute-type", default="int8", help="Compute type, for example int8 or float16.")
    parser.add_argument("--language", default="ja", help="Expected spoken language.")
    parser.add_argument("--beam-size", type=int, default=1, help="Beam size for decoding.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of clips to transcribe.")
    parser.add_argument("--allow-download", action="store_true", help="Allow model download; otherwise use the local cache only.")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    clips = manifest.get("clips", [])[: args.limit]
    if not clips:
        report = {
            "status": "missing_clips",
            "manifest": relative_path(args.manifest),
            "results": [],
        }
        save_json(report, args.output)
        print("ASR smoke test skipped: no clips found.")
        return

    import_start = time.perf_counter()
    from faster_whisper import WhisperModel

    import_seconds = time.perf_counter() - import_start

    load_start = time.perf_counter()
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type, local_files_only=not args.allow_download)
    model_load_seconds = time.perf_counter() - load_start

    results = [transcribe_clip(model, clip, args.language, args.beam_size) for clip in clips]
    report = {
        "status": "ok",
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "language": args.language,
        "beam_size": args.beam_size,
        "clip_count": len(results),
        "import_seconds": round(import_seconds, 3),
        "model_load_seconds": round(model_load_seconds, 3),
        "source_manifest": relative_path(args.manifest),
        "results": results,
        "note": "ASR output is a draft transcript and should be reviewed by a human.",
    }
    save_json(report, args.output)
    print(f"Transcribed {len(results)} clips.")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
