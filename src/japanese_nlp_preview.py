from __future__ import annotations

import argparse
import importlib.util
import json
import re
from pathlib import Path

from ass_parser import PROJECT_ROOT, save_json


DEFAULT_INPUT = PROJECT_ROOT / "data" / "parsed" / "asr_learning_dataset.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "japanese_nlp_preview.json"
DEFAULT_ENV_OUTPUT = PROJECT_ROOT / "data" / "parsed" / "japanese_nlp_environment.json"
LEXICON_INPUT = PROJECT_ROOT / "examples" / "glossary.json"

TOKEN_RE = re.compile(
    r"[\u4e00-\u9fff]+|[\u3040-\u309f]+|[\u30a0-\u30ffー]+|[A-Za-z]+|\d+|[^\s]",
)
PARTICLES = {
    "は",
    "が",
    "を",
    "に",
    "へ",
    "で",
    "と",
    "も",
    "の",
    "か",
    "ね",
    "よ",
    "から",
    "まで",
    "より",
}


def load_lexicon(path: Path) -> dict[str, str]:
    """Load a small local Japanese-to-Chinese token glossary."""
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def meaning_for(surface: str, lexicon: dict[str, str]) -> tuple[str, str]:
    """Return Chinese meaning and lookup status for a token."""
    if surface in lexicon:
        return lexicon[surface], "matched"
    if surface in PARTICLES:
        return "助词", "particle_fallback"
    if re.fullmatch(r"[^\w\s]", surface):
        return "标点", "punctuation"
    return "待查", "missing"


def package_installed(name: str) -> bool:
    """Return whether a Python package is importable."""
    return importlib.util.find_spec(name) is not None


def build_environment_report() -> dict:
    """Report Japanese NLP package availability."""
    packages = {
        "sudachipy": package_installed("sudachipy"),
        "sudachidict_core": package_installed("sudachidict_core"),
        "fugashi": package_installed("fugashi"),
        "unidic_lite": package_installed("unidic_lite"),
        "janome": package_installed("janome"),
    }
    has_sudachi = False  # Public baseline deliberately uses rule grouping; morphology remains unvalidated.
    return {
        "packages": packages,
        "selected_analyzer": "sudachipy" if has_sudachi else "fallback_script_grouping",
        "is_true_morphological_analysis": has_sudachi,
        "note": "Rule grouping is not Japanese morphology; glossary coverage is partial.",
    }


def script_type(surface: str) -> str:
    """Classify a token by rough Unicode script."""
    if re.fullmatch(r"[\u3040-\u309f]+", surface):
        return "hiragana"
    if re.fullmatch(r"[\u30a0-\u30ffー]+", surface):
        return "katakana"
    if re.fullmatch(r"[\u4e00-\u9fff]+", surface):
        return "kanji"
    if re.fullmatch(r"[A-Za-z]+", surface):
        return "latin"
    if re.fullmatch(r"\d+", surface):
        return "number"
    return "symbol"


def fallback_analyze(text: str, lexicon: dict[str, str]) -> list[dict]:
    """Create a transparent non-morphological token preview."""
    tokens = []
    for match in TOKEN_RE.finditer(text):
        surface = match.group(0)
        meaning, lookup_status = meaning_for(surface, lexicon)
        tokens.append(
            {
                "surface": surface,
                "dictionary_form": surface,
                "pos": "unknown",
                "script_type": script_type(surface),
                "is_particle_candidate": surface in PARTICLES,
                "meaning_zh": meaning,
                "lookup_status": lookup_status,
                "analysis_source": "fallback_script_grouping",
            }
        )
    return tokens


def analyze_text(text: str, use_sudachi: bool, lexicon: dict[str, str]) -> list[dict]:
    if use_sudachi:
        raise NotImplementedError("Morphological analysis is not a validated public capability.")
    return fallback_analyze(text, lexicon)


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview Japanese NLP records from ASR learning data.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="ASR learning dataset path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Japanese NLP preview output path.")
    parser.add_argument("--env-output", type=Path, default=DEFAULT_ENV_OUTPUT, help="NLP environment report path.")
    parser.add_argument("--lexicon", type=Path, default=LEXICON_INPUT, help="Japanese token glossary JSON path.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum records to analyze.")
    args = parser.parse_args()

    env_report = build_environment_report()
    use_sudachi = env_report["selected_analyzer"] == "sudachipy"
    lexicon = load_lexicon(args.lexicon)
    records = json.loads(args.input.read_text(encoding="utf-8"))[: args.limit]

    analyzed = []
    for record in records:
        text = str(record.get("japanese_text", "")).strip()
        analyzed.append(
            {
                "index": record["index"],
                "start": record["start"],
                "end": record["end"],
                "japanese_text": text,
                "chinese_text": record.get("chinese_text", ""),
                "source_type": record.get("source_type", ""),
                "source_quality": record.get("source_quality", ""),
                "nlp_reliability": record.get("nlp_reliability", ""),
                "analyzer": env_report["selected_analyzer"],
                "is_true_morphological_analysis": env_report["is_true_morphological_analysis"],
                "tokens": analyze_text(text, use_sudachi, lexicon) if text else [],
            }
        )

    env_report["lexicon_path"] = args.lexicon.name
    env_report["lexicon_entry_count"] = len(lexicon)
    save_json(env_report, args.env_output)
    save_json(analyzed, args.output)
    print(f"Analyzed {len(analyzed)} records.")
    print(f"Analyzer: {env_report['selected_analyzer']}")
    print(f"Output: {args.output}")
    print(f"Environment: {args.env_output}")


if __name__ == "__main__":
    main()
