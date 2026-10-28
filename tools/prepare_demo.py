"""Create original subtitle cards and a local demo; no film or model is bundled."""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ass_parser import parse_ass_file, make_learning_records, save_json
from media_utils import executable
from extract_audio_clips import extract
from extract_video_clips import extract_video

def font_path(selected):
    if selected:
        return Path(selected)
    candidates=[]
    if os.environ.get("WINDIR"):
        candidates += [Path(os.environ["WINDIR"])/"Fonts"/n for n in ("meiryo.ttc","msgothic.ttc")]
    candidates += list(Path("/usr/share/fonts").glob("**/NotoSansCJK*.ttc"))
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("Pass --font pointing to an installed Japanese-capable font. Fonts are not redistributed.")

def make_speech(text: str, path: Path):
    if os.name!="nt":
        raise RuntimeError("--speech currently uses a local Windows SAPI Japanese voice.")
    # UTF-8 files and environment arguments avoid quoting user text into PowerShell.
    text_file=path.with_suffix(".txt")
    text_file.write_text(text,encoding="utf-8")
    script=(
        "$voice=New-Object -ComObject SAPI.SpVoice; "
        "$jp=@($voice.GetVoices() | Where-Object { $_.GetAttribute('Language') -match '(^|;)411(;|$)' }); "
        "if ($jp.Count -eq 0) { throw 'No Japanese SAPI voice installed' }; "
        "$voice.Voice=$jp[0]; $voice.Rate=-1; "
        "$stream=New-Object -ComObject SAPI.SpFileStream; "
        "$stream.Open($env:DEMO_SPEECH_OUTPUT,3,$false); "
        "try { $voice.AudioOutputStream=$stream; "
        "$text=Get-Content -LiteralPath $env:DEMO_SPEECH_TEXT -Raw -Encoding UTF8; "
        "$null=$voice.Speak($text) } finally { $stream.Close() }"
    )
    env={**os.environ,"DEMO_SPEECH_TEXT":str(text_file),"DEMO_SPEECH_OUTPUT":str(path)}
    subprocess.run(["powershell","-NoProfile","-NonInteractive","-Command",script],env=env,check=True,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    text_file.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--font",help="Installed Japanese font file (used locally only).")
    p.add_argument("--speech",action="store_true",help="Generate local Windows SAPI Japanese speech; default is a test tone.")
    a=p.parse_args()
    # Never reset existing review decisions or personal progress.
    if (ROOT/"data/parsed/study_app_dataset.json").exists() or (ROOT/"data/review").exists() or (ROOT/"data/input/demo.mp4").exists():
        raise FileExistsError("Demo data already exists. Use a fresh checkout to regenerate; review files are never silently reset.")
    font=font_path(a.font)
    work=ROOT/"data/input";work.mkdir(parents=True,exist_ok=True)
    raw=parse_ass_file(ROOT/"examples/self_authored.ass")
    merged=make_learning_records(raw)
    save_json(raw,ROOT/"data/parsed/ass_records.json")
    save_json(merged,ROOT/"data/parsed/ass_learning_records.json")
    ffmpeg=executable("ffmpeg")
    parts=[]
    for index,record in enumerate(merged,start=1):
        image=Image.new("RGB",(640,360),(19,27,43));draw=ImageDraw.Draw(image)
        draw.text((24,24),"SELF-AUTHORED TEST CARD",font=ImageFont.load_default(size=22),fill=(166,206,238))
        draw.text((24,62),"Synthetic speech" if a.speech else "Test tone (not speech)",font=ImageFont.load_default(size=18),fill="white")
        draw.text((320,290),record["chinese_text"],font=ImageFont.truetype(str(font),22),anchor="mt",fill=(183,200,213))
        draw.text((320,328),record["japanese_text"],font=ImageFont.truetype(str(font),20),anchor="mt",fill="white")
        card=work/f"card_{index}.png";image.save(card)
        audio_args=["-f","lavfi","-i",f"sine=frequency={360+index*70}:sample_rate=16000"]
        if a.speech:
            wav=work/f"speech_{index}.wav";make_speech(record["japanese_text"],wav)
            audio_args=["-i",str(wav)]
        part=work/f"part_{index}.mp4"
        subprocess.run([ffmpeg,"-nostdin","-y","-loglevel","error","-loop","1","-framerate","25","-i",str(card),
            *audio_args,"-af","apad","-t","4.5","-c:v","libx264","-pix_fmt","yuv420p",
            "-c:a","aac","-ar","16000","-movflags","+faststart",str(part)],check=True)
        parts.append(part.name)
    concat=work/"concat.txt"
    concat.write_text("".join(f"file '{name}'\n" for name in parts),encoding="utf-8")
    video=work/"demo.mp4"
    subprocess.run([ffmpeg,"-nostdin","-y","-loglevel","error","-f","concat","-safe","1",
        "-i",str(concat),"-c","copy","-movflags","+faststart",str(video)],check=True)
    audio=extract(ROOT/"examples/self_authored.ass",video,ROOT/"data/audio_clips/demo")
    videos=extract_video(audio,ROOT/"data/video_clips/demo")
    save_json(audio,ROOT/"data/parsed/audio_clip_manifest.json")
    save_json(videos,ROOT/"data/parsed/video_clip_manifest.json")
    draft=[]
    for record,clip in zip(merged,audio["clips"]):
        draft.append({**record,"japanese_text_asr":record["japanese_text"],
            "japanese_text_corrected":"","audio_file_name":clip["audio_file_name"],
            "source_type":"demo_fixture","asr_model":None,"review_status":"pending",
            "needs_human_review":True,"quality_flags":["authored_fixture_not_asr"]})
    save_json(draft,ROOT/"data/parsed/asr_draft_subtitles.json")
    save_json({"text_source":"self-authored fixture, not ASR",
        "audio_source":"Windows Japanese SAPI synthetic voice" if a.speech else "generated test tones",
        "record_count":len(draft),"accuracy_evaluation":False},ROOT/"data/parsed/demo_provenance.json")
    subprocess.run([sys.executable,"-X","utf8",str(ROOT/"src/export_asr_review_sheet.py")],cwd=ROOT,check=True)
    subprocess.run([sys.executable,"-X","utf8",str(ROOT/"tools/rebuild_data.py")],cwd=ROOT,check=True)
    # Crops are generated independently from authored text; no OCR model is used by default.
    subprocess.run([sys.executable,"-X","utf8",str(ROOT/"src/hardsub_ocr_extract.py"),"--backend","none",
        "--sample-ratios","0.4"],cwd=ROOT,check=True)
    print("Demo ready: 6 authored ASS lines -> 3 merged items; all remain pending. No ASR or OCR inference has been claimed.")
if __name__=="__main__":
    main()
