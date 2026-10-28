"""Rebuild from draft + current review CSVs; no model is called here."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
STEPS=["apply_asr_corrections.py","apply_hardsub_ocr_corrections.py",
       "build_asr_learning_dataset.py","japanese_nlp_preview.py","build_study_app_dataset.py"]
def main():
    for name in STEPS:
        subprocess.run([sys.executable,"-X","utf8",str(ROOT/"src"/name)],cwd=ROOT,check=True)
    print("Rebuilt from current ASR and OCR review decisions.")
if __name__=="__main__":
    main()
