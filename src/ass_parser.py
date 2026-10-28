from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = PROJECT_ROOT / "examples" / "self_authored.ass"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "ass_records.json"
DEFAULT_LEARNING_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "ass_learning_records.json"

ASS_TAG_RE = re.compile(r"\{[^{}]*\}")
HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff\uff66-\uff9f]")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
WHITESPACE_RE = re.compile(r"\s+")
DRAWING_TEXT_RE = re.compile(r"^(?:m|l|b|s|p|c|\d+|\s)+$", re.IGNORECASE)

SKIP_STYLES = {"staff", "ps", "遮罩"}
LYRIC_STYLES = {"opjp", "opcn", "edjp", "edcn"}
SCREEN_STYLES = {"screen"}


def read_text_with_fallback(path: Path) -> str:
    """Read subtitle text while tolerating common subtitle encodings."""
    encodings = ("utf-8-sig", "utf-8", "utf-16", "gb18030", "cp932")
    last_error: UnicodeDecodeError | None = None

    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            last_error = error

    raise UnicodeDecodeError(
        last_error.encoding if last_error else "unknown",
        last_error.object if last_error else b"",
        last_error.start if last_error else 0,
        last_error.end if last_error else 0,
        f"Could not decode {path} with common subtitle encodings.",
    )


def parse_format_line(line: str) -> list[str]:
    """Parse an ASS Format line into lower-case field names."""
    _, value = line.split(":", 1)
    return [field.strip().lower() for field in value.split(",")]


def split_ass_record(line: str, field_count: int) -> list[str]:
    """
    Split a Dialogue line according to the active ASS Format.

    ASS dialogue text itself may contain commas, so split only the first
    field_count - 1 commas and keep the rest as Text.
    """
    _, value = line.split(":", 1)
    parts = value.strip().split(",", field_count - 1)
    if len(parts) < field_count:
        parts.extend([""] * (field_count - len(parts)))
    return [part.strip() for part in parts]


def remove_ass_tags(text: str) -> str:
    r"""Remove common ASS override tags such as {\pos(...)} or {\fad(...)}."""
    return ASS_TAG_RE.sub("", text)


def normalize_ass_text(text: str) -> str:
    """Convert ASS escapes into plain text that is easier to read."""
    text = remove_ass_tags(text)
    text = text.replace(r"\N", " ")
    text = text.replace(r"\n", " ")
    text = text.replace(r"\h", " ")
    return WHITESPACE_RE.sub(" ", text).strip()


def split_text_parts(raw_text: str) -> list[str]:
    r"""
    Keep subtitle line breaks before flattening.

    Bilingual ASS subtitles often store Japanese and Chinese in separate visual
    lines, for example: Japanese\NChinese.
    """
    without_tags = remove_ass_tags(raw_text)
    parts = re.split(r"\\N|\\n", without_tags)
    return [
        WHITESPACE_RE.sub(" ", part.replace(r"\h", " ")).strip()
        for part in parts
        if part.strip()
    ]


def has_japanese_signal(text: str) -> bool:
    """Kana is the strongest simple signal that a text is Japanese."""
    return bool(HIRAGANA_KATAKANA_RE.search(text))


def has_chinese_signal(text: str) -> bool:
    """
    Treat CJK characters as Chinese only when there is no kana signal.

    This is a Phase 0.1 heuristic. A kanji-only Japanese sentence can be
    ambiguous; later Japanese NLP will handle that more accurately.
    """
    return bool(CJK_RE.search(text)) and not has_japanese_signal(text)


def classify_and_extract(raw_text: str, style: str) -> tuple[str, str, str]:
    """
    Return japanese_text, chinese_text, language_type for one subtitle event.

    Style names like OPJP/OPCN or Sub-CN are used as weak hints, because many
    ASS files separate languages by style.
    """
    parts = split_text_parts(raw_text)
    style_lower = style.lower()
    japanese_parts: list[str] = []
    chinese_parts: list[str] = []

    for part in parts:
        if has_japanese_signal(part) or style_lower.endswith("jp"):
            japanese_parts.append(part)
        elif has_chinese_signal(part) or "cn" in style_lower or style_lower.endswith("tc"):
            chinese_parts.append(part)

    japanese_text = " ".join(japanese_parts).strip()
    chinese_text = " ".join(chinese_parts).strip()

    if japanese_text and chinese_text:
        language_type = "bilingual"
    elif japanese_text:
        language_type = "japanese"
    elif chinese_text:
        language_type = "chinese"
    else:
        language_type = "unknown"

    return japanese_text, chinese_text, language_type


def parse_ass_file(input_path: Path) -> list[dict[str, str | int]]:
    """Parse the [Events] section of a standard ASS subtitle file."""
    content = read_text_with_fallback(input_path)
    in_events = False
    event_format: list[str] = []
    subtitles: list[dict[str, str | int]] = []

    for raw_line in content.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("[") and line.endswith("]"):
            in_events = line.lower() == "[events]"
            continue

        if not in_events:
            continue

        if line.lower().startswith("format:"):
            event_format = parse_format_line(line)
            continue

        if not line.lower().startswith("dialogue:"):
            continue

        if not event_format:
            raise ValueError("Found Dialogue before Events Format line.")

        values = split_ass_record(line, len(event_format))
        event = dict(zip(event_format, values))

        raw_text = event.get("text", "")
        style = event.get("style", "")
        japanese_text, chinese_text, language_type = classify_and_extract(raw_text, style)

        subtitles.append(
            {
                "index": len(subtitles) + 1,
                "start": event.get("start", ""),
                "end": event.get("end", ""),
                "style": style,
                "raw_text": raw_text,
                "cleaned_text": normalize_ass_text(raw_text),
                "japanese_text": japanese_text,
                "chinese_text": chinese_text,
                "language_type": language_type,
            }
        )

    return subtitles


def classify_content(styles: list[str], cleaned_text: str, language_type: str) -> tuple[str, bool, str]:
    """
    Classify a merged subtitle item for the later learning pipeline.

    The parser still keeps the text, but this marks whether a later Japanese
    NLP step should spend time on it.
    """
    style_names = {style.lower() for style in styles}
    text = cleaned_text.strip()

    if not text:
        return "empty", False, "empty_text"

    if style_names & SKIP_STYLES:
        return "note", False, "staff_or_translator_note"

    if DRAWING_TEXT_RE.fullmatch(text):
        return "drawing", False, "ass_vector_drawing"

    if language_type == "unknown":
        return "unknown", False, "unknown_language"

    if style_names & LYRIC_STYLES:
        return "lyrics", language_type in {"japanese", "bilingual"}, "song_lyrics"

    if style_names & SCREEN_STYLES:
        return "screen_text", language_type in {"japanese", "bilingual"}, "screen_text"

    return "dialogue", language_type in {"japanese", "bilingual"}, "main_dialogue"


def make_learning_records(records: list[dict[str, str | int]]) -> list[dict[str, str | int | bool | list[int] | list[str]]]:
    """
    Merge records that share the same time range into learning-friendly items.

    Some ASS files store bilingual subtitles as separate Dialogue rows with the
    same start/end time, for example OPJP and OPCN. The raw output keeps every
    Dialogue row, while this learning output combines those pairs.
    """
    grouped_records: dict[tuple[str, str], list[dict[str, str | int]]] = defaultdict(list)
    group_order: list[tuple[str, str]] = []

    for record in records:
        key = (str(record["start"]), str(record["end"]))
        if key not in grouped_records:
            group_order.append(key)
        grouped_records[key].append(record)

    learning_records: list[dict[str, str | int | bool | list[int] | list[str]]] = []

    for key in group_order:
        group = [
            record
            for record in grouped_records[key]
            if str(record.get("cleaned_text", "")).strip()
        ]

        if not group:
            continue

        japanese_parts = [str(record["japanese_text"]) for record in group if str(record["japanese_text"]).strip()]
        chinese_parts = [str(record["chinese_text"]) for record in group if str(record["chinese_text"]).strip()]
        cleaned_parts = [str(record["cleaned_text"]) for record in group if str(record["cleaned_text"]).strip()]

        japanese_text = " ".join(japanese_parts).strip()
        chinese_text = " ".join(chinese_parts).strip()

        if japanese_text and chinese_text:
            language_type = "bilingual"
        elif japanese_text:
            language_type = "japanese"
        elif chinese_text:
            language_type = "chinese"
        else:
            language_type = "unknown"

        styles = sorted({str(record.get("style", "")) for record in group})
        cleaned_text = " ".join(cleaned_parts).strip()
        content_type, should_analyze, analyze_reason = classify_content(styles, cleaned_text, language_type)

        learning_records.append(
            {
                "index": len(learning_records) + 1,
                "start": key[0],
                "end": key[1],
                "styles": styles,
                "source_indices": [int(record["index"]) for record in group],
                "raw_text": r"\N".join(str(record["raw_text"]) for record in group),
                "cleaned_text": cleaned_text,
                "japanese_text": japanese_text,
                "chinese_text": chinese_text,
                "language_type": language_type,
                "content_type": content_type,
                "should_analyze": should_analyze,
                "analyze_reason": analyze_reason,
            }
        )

    return learning_records


def save_json(records: object, output_path: Path) -> None:
    """Save parsed subtitle records as readable UTF-8 JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse ASS subtitles into learning-friendly JSON.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to the .ass subtitle file.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to the output .json file.")
    parser.add_argument(
        "--learning-output",
        type=Path,
        default=DEFAULT_LEARNING_OUTPUT,
        help="Path to the merged learning-friendly output .json file.",
    )
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Input subtitle file not found: {args.input}")

    records = parse_ass_file(args.input)
    learning_records = make_learning_records(records)
    save_json(records, args.output)
    save_json(learning_records, args.learning_output)
    print(f"Parsed {len(records)} dialogue lines.")
    print(f"Created {len(learning_records)} learning records.")
    print(f"Input : {args.input}")
    print(f"Raw output     : {args.output}")
    print(f"Learning output: {args.learning_output}")


if __name__ == "__main__":
    main()
