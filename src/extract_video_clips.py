from __future__ import annotations
import argparse
import json
import subprocess
from pathlib import Path
from ass_parser import PROJECT_ROOT, save_json
from media_utils import executable, project_path, relative_path, ms_to_ffmpeg_time

def extract_video(manifest: dict, output_dir: Path, video: Path | None = None) -> dict:
    source = project_path(video or manifest["video_path"])
    output_dir = project_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for clip in manifest["clips"]:
        path = output_dir / (Path(clip["audio_file_name"]).stem + ".mp4")
        subprocess.run([executable("ffmpeg"), "-nostdin", "-y", "-loglevel", "error",
            "-ss", ms_to_ffmpeg_time(clip["start_ms"]), "-i", str(source),
            "-t", ms_to_ffmpeg_time(clip["duration_ms"]), "-vf", "scale=640:-2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(path)], check=True)
        if not path.is_file() or path.stat().st_size < 100:
            raise RuntimeError("FFmpeg produced an empty video clip")
        clips.append({**clip, "video_file": relative_path(path), "video_file_name": path.name})
    return {"status": "ok", "source_video": relative_path(source), "source_video_kind": "user_supplied", "clips": clips}

def main() -> None:
    p = argparse.ArgumentParser(description="Extract H.264/AAC browser video clips.")
    p.add_argument("--manifest", type=Path, default=PROJECT_ROOT/"data/parsed/audio_clip_manifest.json")
    p.add_argument("--video", type=Path)
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT/"data/video_clips/demo")
    p.add_argument("--output", type=Path, default=PROJECT_ROOT/"data/parsed/video_clip_manifest.json")
    a = p.parse_args()
    report = extract_video(json.loads(project_path(a.manifest).read_text(encoding="utf-8")), a.output_dir, a.video)
    save_json(report, project_path(a.output))
    print(f"Extracted {len(report['clips'])} video clips.")
if __name__ == "__main__":
    main()
