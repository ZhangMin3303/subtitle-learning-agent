from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, NamedTuple

from PIL import Image, ImageEnhance, ImageFilter

from ass_parser import PROJECT_ROOT, save_json
from media_utils import executable, ms_to_ffmpeg_time, project_path


VIDEO_MANIFEST_INPUT = PROJECT_ROOT / "data" / "parsed" / "video_clip_manifest.json"
LEARNING_INPUT = PROJECT_ROOT / "data" / "parsed" / "asr_learning_dataset.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "hardsub_ocr.json"
DEFAULT_REVIEW_CSV = PROJECT_ROOT / "data" / "review" / "hardsub_ocr_review.csv"
DEFAULT_IMAGE_DIR = PROJECT_ROOT / "data" / "ocr_frames" / "demo"

JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fffー々〆〤]")
DEFAULT_SAMPLE_RATIOS = (0.05, 0.2, 0.4, 0.6, 0.8)
DEFAULT_REGIONS = {
    "bottom_japanese": (0.08, 0.91, 0.92, 0.995),
    "bottom_bilingual": (0.08, 0.855, 0.92, 0.995),
    "top_japanese": (0.08, 0.0, 0.92, 0.08),
}
_EASYOCR_READER = None
_MANGA_OCR_READER = None
ALLOW_DOWNLOAD = False


class Candidate(NamedTuple):
    """One sampled subtitle crop candidate."""

    score: float
    sample_ratio: float
    region_name: str
    frame: Image.Image
    crop: Image.Image
    processed: Image.Image


def find_ffmpeg() -> Path | None:
    """Find ffmpeg from PATH or the local media player bundle."""
    return Path(executable("ffmpeg"))


def load_json(path: Path) -> Any:
    """Load a UTF-8 JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def package_installed(name: str) -> bool:
    """Return whether a Python package is importable."""
    return importlib.util.find_spec(name) is not None


def extract_frame(ffmpeg: Path, clip_path: Path, offset_ms: int, output_path: Path) -> None:
    """Extract one representative frame from a short video clip."""
    command = [
        str(ffmpeg),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        ms_to_ffmpeg_time(offset_ms),
        "-i",
        str(clip_path),
        "-frames:v",
        "1",
        str(output_path),
    ]
    subprocess.run(command, check=True)


def time_to_ms(value: str) -> int:
    """Convert ASS-like H:MM:SS.CS time into milliseconds."""
    hours, minutes, seconds = value.strip().split(":")
    whole_seconds, _, fraction = seconds.partition(".")
    fraction_ms = int((fraction + "000")[:3]) if fraction else 0
    return (
        int(hours) * 60 * 60 * 1000
        + int(minutes) * 60 * 1000
        + int(whole_seconds) * 1000
        + fraction_ms
    )


def crop_subtitle_region(image: Image.Image, region: tuple[float, float, float, float]) -> Image.Image:
    """
    Crop the subtitle area using relative coordinates.

    The current hard-sub video places Chinese above Japanese near the bottom.
    The default region focuses on the lower Japanese line.
    """
    if len(region) != 4 or not (0 <= region[0] < region[2] <= 1 and 0 <= region[1] < region[3] <= 1):
        raise ValueError("Crop box must satisfy 0 <= left < right <= 1 and 0 <= top < bottom <= 1")
    width, height = image.size
    left = int(width * region[0])
    top = int(height * region[1])
    right = int(width * region[2])
    bottom = int(height * region[3])
    return image.crop((left, top, right, bottom))


def preprocess_for_ocr(image: Image.Image) -> Image.Image:
    """Make white subtitle text easier for OCR engines to read."""
    enlarged = image.resize((image.width * 3, image.height * 3), Image.Resampling.LANCZOS)
    gray = enlarged.convert("L")
    gray = ImageEnhance.Contrast(gray).enhance(2.2)
    gray = ImageEnhance.Sharpness(gray).enhance(1.8)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return gray


def clean_ocr_text(text: str) -> str:
    """Normalize OCR text while keeping Japanese punctuation."""
    text = text.replace(" ", "")
    text = text.replace("\n", "")
    text = text.replace("|", "ー")
    return text.strip()


def has_japanese(text: str) -> bool:
    """Return whether text contains Japanese-like characters."""
    return bool(JAPANESE_RE.search(text))


def subtitle_score(image: Image.Image) -> float:
    """
    Score how likely a crop contains white subtitle text.

    ASS/anime hard subtitles are usually bright glyphs with dark outlines, so a
    crop that has both bright pixels and edge detail is a good candidate.
    """
    gray = image.convert("L")
    width, height = gray.size
    pixels = list(gray.get_flattened_data())
    total = max(1, width * height)
    bright_ratio = sum(1 for value in pixels if value > 190) / total
    dark_ratio = sum(1 for value in pixels if value < 70) / total
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_ratio = sum(1 for value in edges.get_flattened_data() if value > 40) / total
    return bright_ratio * 2.0 + min(dark_ratio, 0.35) * 0.6 + edge_ratio * 1.2


def parse_sample_ratios(value: str) -> list[float]:
    """Parse comma-separated sample ratios."""
    ratios = [float(part.strip()) for part in value.split(",") if part.strip()]
    if not ratios or any(not 0 <= ratio <= 0.95 for ratio in ratios):
        raise ValueError("Provide sample ratios between 0 and 0.95")
    return ratios


def parse_regions(value: str) -> dict[str, tuple[float, float, float, float]]:
    """Parse named crop regions, or use a built-in preset."""
    if value == "auto":
        return DEFAULT_REGIONS

    regions: dict[str, tuple[float, float, float, float]] = {}
    for index, item in enumerate(value.split(";"), start=1):
        item = item.strip()
        if not item:
            continue
        if "=" in item:
            name, raw_box = item.split("=", 1)
            name = name.strip() or f"region_{index}"
        else:
            name = f"region_{index}"
            raw_box = item
        box = tuple(float(part.strip()) for part in raw_box.split(","))
        if len(box) != 4:
            raise ValueError("Each crop region must contain four comma-separated floats.")
        if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
            raise ValueError("Invalid normalized crop box")
        regions[name] = box  # type: ignore[assignment]
    if not regions:
        raise ValueError("No valid crop region was provided.")
    return regions


def choose_best_candidate(
    *,
    ffmpeg: Path,
    video_file: Path,
    duration_ms: int,
    sample_ratios: list[float],
    regions: dict[str, tuple[float, float, float, float]],
    temp_root: Path,
    index: int,
    base_start_ms: int = 0,
) -> Candidate:
    """Sample several frames and regions, then choose the most subtitle-like crop."""
    candidates: list[Candidate] = []

    for sample_ratio in sample_ratios:
        offset_ms = base_start_ms + max(0, min(duration_ms - 1, int(duration_ms * sample_ratio)))
        temp_frame = temp_root / f"clip_{index:04d}_{int(sample_ratio * 100):02d}.jpg"
        extract_frame(ffmpeg, video_file, offset_ms, temp_frame)
        frame = Image.open(temp_frame).convert("RGB")

        for region_name, region in regions.items():
            crop = crop_subtitle_region(frame, region)
            score = subtitle_score(crop)

            # Prefer the bottom Japanese line when it has enough text signal.
            if region_name == "bottom_japanese" and score > 0.05:
                score += 0.08
            elif region_name.startswith("bottom"):
                score += 0.03

            processed = preprocess_for_ocr(crop)
            candidate = Candidate(score, sample_ratio, region_name, frame, crop, processed)
            candidates.append(candidate)

    if not candidates:
        raise RuntimeError("No OCR frame candidate could be created.")

    # This project cares about Japanese learning text. In the current source,
    # the Japanese dialogue line is usually the small lower subtitle, while the
    # larger top text can be Chinese or unrelated overlay text. Prefer the lower
    # Japanese region whenever it has a real text signal.
    for preferred_name, threshold in (
        ("bottom_japanese", 0.12),
        ("bottom_bilingual", 0.18),
        ("top_japanese", 0.18),
    ):
        preferred = [candidate for candidate in candidates if candidate.region_name == preferred_name]
        if preferred:
            best_preferred = max(preferred, key=lambda candidate: candidate.score)
            if best_preferred.score >= threshold:
                return best_preferred

    return max(candidates, key=lambda candidate: candidate.score)


def easyocr_read(image_path: Path) -> tuple[str, float, list[dict[str, Any]]]:
    """Run EasyOCR if it is installed locally."""
    global _EASYOCR_READER

    import easyocr  # type: ignore
    import numpy as np

    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["ja"], gpu=False, verbose=False, download_enabled=ALLOW_DOWNLOAD)

    # OpenCV cannot reliably read non-ASCII Windows paths. Reading through PIL
    # and passing a numpy array keeps the project usable inside Chinese folders.
    image = Image.open(image_path).convert("RGB")
    raw_results = _EASYOCR_READER.readtext(np.array(image), detail=1, paragraph=False)
    pieces: list[str] = []
    confidences: list[float] = []
    details: list[dict[str, Any]] = []

    for box, text, confidence in raw_results:
        cleaned = clean_ocr_text(str(text))
        if cleaned:
            serializable_box = [
                [float(point[0]), float(point[1])]
                for point in box
            ]
            pieces.append(cleaned)
            confidences.append(float(confidence))
            details.append({"text": cleaned, "confidence": float(confidence), "box": serializable_box})

    merged_text = clean_ocr_text("".join(pieces))
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return merged_text, avg_confidence, details


def manga_ocr_read(image_path: Path) -> tuple[str, float, list[dict[str, Any]]]:
    """Run Manga OCR if it is installed locally."""
    global _MANGA_OCR_READER

    from manga_ocr import MangaOcr  # type: ignore

    if _MANGA_OCR_READER is None:
        from huggingface_hub import snapshot_download
        model_path = snapshot_download("kha-white/manga-ocr-base", local_files_only=not ALLOW_DOWNLOAD)
        _MANGA_OCR_READER = MangaOcr(pretrained_model_name_or_path=model_path, force_cpu=True)

    image = Image.open(image_path).convert("RGB")
    text = clean_ocr_text(_MANGA_OCR_READER(image))
    confidence = 0.0
    return text, confidence, [{"text": text, "confidence": confidence}]


def make_record(
    *,
    index: int,
    clip: dict,
    learning: dict,
    frame_path: Path,
    crop_path: Path,
    processed_path: Path,
    backend: str,
    ocr_text: str,
    confidence: float,
    raw_ocr: list[dict[str, Any]],
    status: str,
) -> dict:
    """Build one OCR result record."""
    return {
        "index": index,
        "start": learning.get("start", clip.get("start", "")),
        "end": learning.get("end", clip.get("end", "")),
        "chinese_text": learning.get("chinese_text", ""),
        "asr_japanese_text": learning.get("japanese_text", ""),
        "ocr_japanese_text": ocr_text,
        "ocr_confidence": round(confidence, 4),
        "ocr_backend": backend,
        "ocr_status": status,
        "needs_human_review": True,
        "frame_image": str(frame_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "crop_image": str(crop_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "processed_image": str(processed_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "video_file_name": clip.get("video_file_name", ""),
        "raw_ocr": raw_ocr,
    }


def write_review_csv(records: list[dict], output_path: Path) -> None:
    """Write a human-editable review sheet for OCR results."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "index",
        "start",
        "end",
        "ocr_japanese_text",
        "corrected_japanese_text",
        "approved",
        "ocr_confidence",
        "ocr_status",
        "chinese_text",
        "asr_japanese_text",
        "crop_image",
        "notes",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {field: record.get(field, "") for field in fields}
            row["corrected_japanese_text"] = record.get("ocr_japanese_text", "")
            row["approved"] = ""
            row["notes"] = ""
            writer.writerow(row)


def run_ocr(
    processed_path: Path,
    backend: str,
) -> tuple[str, float, list[dict[str, Any]], str]:
    """Run the selected OCR backend, or return a clear status if unavailable."""
    if backend == "none":
        return "", 0.0, [], "ocr_skipped"

    if backend == "easyocr":
        if not package_installed("easyocr"):
            return "", 0.0, [], "missing_easyocr"
        try:
            text, confidence, raw = easyocr_read(processed_path)
        except Exception as error:
            return "", 0.0, [{"error": str(error)}], "ocr_error"
        if not text:
            return "", confidence, raw, "empty_ocr"
        if not has_japanese(text):
            return text, confidence, raw, "no_japanese_signal"
        if confidence < 0.5:
            return text, confidence, raw, "low_confidence"
        return text, confidence, raw, "ok"

    if backend == "manga_ocr":
        if not package_installed("manga_ocr"):
            return "", 0.0, [], "missing_manga_ocr"
        try:
            text, confidence, raw = manga_ocr_read(processed_path)
        except Exception as error:
            return "", 0.0, [{"error": str(error)}], "ocr_error"
        if not text:
            return "", confidence, raw, "empty_ocr"
        if not has_japanese(text):
            return text, confidence, raw, "no_japanese_signal"
        return text, confidence, raw, "draft_no_confidence"

    raise ValueError(f"Unsupported OCR backend: {backend}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract Japanese hard subtitles from video clips with OCR.")
    parser.add_argument("--video-manifest", type=Path, default=VIDEO_MANIFEST_INPUT, help="Video clip manifest path.")
    parser.add_argument("--learning", type=Path, default=LEARNING_INPUT, help="Current learning dataset path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="OCR JSON output path.")
    parser.add_argument("--review-csv", type=Path, default=DEFAULT_REVIEW_CSV, help="Human review CSV output path.")
    parser.add_argument("--image-dir", type=Path, default=DEFAULT_IMAGE_DIR, help="Output directory for OCR images.")
    parser.add_argument("--backend", choices=["manga_ocr", "easyocr", "none"], default="none", help="OCR backend to use.")
    parser.add_argument(
        "--frame-source",
        choices=["source", "clip"],
        default="source",
        help="Extract OCR frames from the original hard-sub video or compressed web clips.",
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum clips to process.")
    parser.add_argument(
        "--sample-ratios",
        default=",".join(str(ratio) for ratio in DEFAULT_SAMPLE_RATIOS),
        help="Comma-separated frame sample ratios inside each clip.",
    )
    parser.add_argument(
        "--regions",
        default="auto",
        help="auto, or semicolon-separated named boxes like name=left,top,right,bottom.",
    )
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--overwrite-review", action="store_true", help="Explicitly discard existing OCR review edits.")
    args = parser.parse_args()
    for name in ("video_manifest", "learning", "output", "review_csv", "image_dir"):
        setattr(args, name, project_path(getattr(args, name)))
    global ALLOW_DOWNLOAD
    ALLOW_DOWNLOAD = args.allow_download
    if args.review_csv.exists() and not args.overwrite_review:
        raise FileExistsError("OCR review CSV already exists; choose a new output or explicitly discard edits.")

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise FileNotFoundError("ffmpeg was not found. Add FFmpeg to PATH.")

    sample_ratios = parse_sample_ratios(args.sample_ratios)
    regions = parse_regions(args.regions)

    video_manifest = load_json(args.video_manifest)
    clips = video_manifest.get("clips", [])[: args.limit]
    learning_records = load_json(args.learning)[: args.limit]
    learning_by_audio = {record.get("audio_file_name"): record for record in learning_records}
    source_video = project_path(video_manifest["source_video"])
    use_source_video = args.frame_source == "source" and source_video.is_file()

    args.image_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_root = Path(temp_dir)
        for clip in clips:
            index = int(clip["source_index"])
            video_file = source_video if use_source_video else project_path(clip["video_file"])
            learning = learning_by_audio.get(clip.get("audio_file_name"), {})
            base_start_ms = time_to_ms(str(clip["start"])) if use_source_video else 0
            frame_path = args.image_dir / f"clip_{index:04d}_frame.jpg"
            crop_path = args.image_dir / f"clip_{index:04d}_crop.png"
            processed_path = args.image_dir / f"clip_{index:04d}_processed.png"

            best = choose_best_candidate(
                ffmpeg=ffmpeg,
                video_file=video_file,
                duration_ms=int(clip.get("duration_ms", 0)),
                sample_ratios=sample_ratios,
                regions=regions,
                temp_root=temp_root,
                index=index,
                base_start_ms=base_start_ms,
            )

            best.frame.save(frame_path, quality=92)
            best.crop.save(crop_path)
            best.processed.save(processed_path)

            ocr_text, confidence, raw_ocr, status = run_ocr(processed_path, args.backend)
            records.append(
                make_record(
                    index=index,
                    clip=clip,
                    learning=learning,
                    frame_path=frame_path,
                    crop_path=crop_path,
                    processed_path=processed_path,
                    backend=args.backend,
                    ocr_text=ocr_text,
                    confidence=confidence,
                    raw_ocr=raw_ocr,
                    status=status,
                )
            )
            records[-1]["sample_ratio"] = best.sample_ratio
            records[-1]["region_name"] = best.region_name
            records[-1]["crop_score"] = round(best.score, 4)

    report = {
        "status": "ok",
        "source_video_kind": video_manifest.get("source_video_kind", ""),
        "frame_source": "source_video" if use_source_video else "video_clips",
        "ocr_backend": args.backend,
        "record_count": len(records),
        "sample_ratios": sample_ratios,
        "crop_regions": {name: list(box) for name, box in regions.items()},
        "note": "OCR results are draft text. Review the crop images before using them for serious study.",
        "records": records,
    }
    save_json(report, args.output)
    write_review_csv(records, args.review_csv)

    ok_count = sum(1 for record in records if record["ocr_status"] == "ok")
    print(f"Processed {len(records)} hard-subtitle clips.")
    print(f"OCR ok: {ok_count}/{len(records)}")
    print(f"Output JSON: {args.output}")
    print(f"Review CSV : {args.review_csv}")
    print(f"Images     : {args.image_dir}")


if __name__ == "__main__":
    main()
