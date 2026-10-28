from __future__ import annotations
import argparse
import json
from pathlib import Path
from ass_parser import PROJECT_ROOT, save_json
from media_utils import relative_path
def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))
def build_dataset(learning: list[dict], nlp: list[dict], video_manifest: dict) -> dict:
    tokens={int(r["index"]): r for r in nlp}
    media={int(r["source_index"]): r for r in video_manifest["clips"]}
    items=[]
    for record in learning:
        index=int(record["index"]); clip=media.get(index,{})
        analysis=tokens.get(index,{})
        items.append({**record, "id": f"study_{index:04d}",
            "audio_src": relative_path(clip["audio_file"]) if clip.get("audio_file") else "",
            "video_src": relative_path(clip["video_file"]) if clip.get("video_file") else "",
            "analyzer": analysis.get("analyzer",""), "is_true_morphological_analysis": False,
            "tokens": analysis.get("tokens",[])})
    return {"title": "Subtitle Learning Agent — local prototype", "record_count": len(items),
        "source_note": "demo_fixture = authored test text, not model output. ASR/OCR remain drafts until explicit human approval. Token preview uses rules and a small glossary.",
        "items": items}
def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--learning",type=Path,default=PROJECT_ROOT/"data/parsed/asr_learning_dataset.json")
    p.add_argument("--nlp",type=Path,default=PROJECT_ROOT/"data/parsed/japanese_nlp_preview.json")
    p.add_argument("--video-manifest",type=Path,default=PROJECT_ROOT/"data/parsed/video_clip_manifest.json")
    p.add_argument("--output",type=Path,default=PROJECT_ROOT/"data/parsed/study_app_dataset.json")
    a=p.parse_args()
    save_json(build_dataset(load_json(a.learning),load_json(a.nlp),load_json(a.video_manifest)),a.output)
if __name__ == "__main__":
    main()
