from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path
from ass_parser import PROJECT_ROOT, parse_ass_file, make_learning_records, save_json
from media_utils import ass_time_to_ms, ms_to_ffmpeg_time, executable, project_path, relative_path

def extract_clip(ffmpeg: str, video: Path, output: Path, start_ms: int, duration_ms: int) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg, "-nostdin", "-y", "-loglevel", "error", "-ss", ms_to_ffmpeg_time(start_ms),
        "-i", str(video), "-t", ms_to_ffmpeg_time(duration_ms), "-vn", "-ac", "1", "-ar", "16000", str(output)], check=True)

def extract(subtitle: Path, video: Path, output_dir: Path, limit: int = 20,
            start_after_ms: int = 0, min_duration_ms: int = 500, max_duration_ms: int = 10000) -> dict:
    if limit < 1 or min_duration_ms < 1 or max_duration_ms < min_duration_ms:
        raise ValueError("Invalid clip limits")
    subtitle, video, output_dir = map(project_path, (subtitle, video, output_dir))
    if not video.is_file():
        raise FileNotFoundError(video)
    ffmpeg = executable("ffmpeg")
    probe = json.loads(subprocess.check_output([executable("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)], text=True, encoding="utf-8"))
    source_ms = round(float(probe["format"]["duration"]) * 1000)
    clips = []
    last_end = -1
    for record in make_learning_records(parse_ass_file(subtitle)):
        if record["content_type"] != "dialogue":
            continue
        start, end = ass_time_to_ms(record["start"]), ass_time_to_ms(record["end"])
        if start < start_after_ms or not min_duration_ms <= end-start <= max_duration_ms or start < last_end:
            continue
        if end > source_ms + 80:
            raise ValueError("Subtitle end exceeds the source duration; timeline correction is not implemented.")
        path = output_dir / f"clip_{record['index']:04d}.wav"
        extract_clip(ffmpeg, video, path, start, end-start)
        if not path.is_file() or path.stat().st_size <= 44:
            raise RuntimeError("FFmpeg produced an empty audio clip")
        clips.append({"index": record["index"], "source_index": record["index"], "start": record["start"],
            "end": record["end"], "start_ms": start, "duration_ms": end-start,
            "chinese_text": record["chinese_text"], "audio_file": relative_path(path), "audio_file_name": path.name})
        last_end = end
        if len(clips) == limit:
            break
    if not clips:
        raise ValueError("No dialogue clips met the selection limits")
    return {"status": "ok", "video_path": relative_path(video), "subtitle_path": relative_path(subtitle), "clips": clips}

def main() -> None:
    p = argparse.ArgumentParser(description="Extract non-overlapping dialogue audio from an ASS timeline.")
    p.add_argument("--subtitle", type=Path, required=True)
    p.add_argument("--video", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT/"data/audio_clips/demo")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT/"data/parsed/audio_clip_manifest.json")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--start-after-ms", type=int, default=0)
    p.add_argument("--min-duration-ms", type=int, default=500)
    p.add_argument("--max-duration-ms", type=int, default=10000)
    a = p.parse_args()
    report = extract(a.subtitle, a.video, a.output_dir, a.limit, a.start_after_ms, a.min_duration_ms, a.max_duration_ms)
    save_json(report, project_path(a.output))
    print(f"Extracted {len(report['clips'])} audio clips.")
if __name__ == "__main__":
    main()
