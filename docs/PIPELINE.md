# Pipeline and local files

Run commands from the checkout root. Keep each independent input/review set in a separate checkout: dataset versioning and automatic review migration are not implemented. Never reuse approval CSVs with changed media, timelines or draft identities.

## Inputs and FFmpeg

Place only authorized inputs in `data/input/` (ignored). Media manifests use project-relative paths; external absolute input paths are refused by the media helpers.

```powershell
python src/ass_parser.py --input data/input/authorized.ass
python src/extract_audio_clips.py --subtitle data/input/authorized.ass --video data/input/authorized.mp4
python src/extract_video_clips.py
```

Selection keeps non-overlapping dialogue entries within the duration limits. It does not establish that subtitles are correctly aligned to speech. The source video must contain an audio stream. Override `FFMPEG_BINARY` / `FFPROBE_BINARY` if necessary; do not commit machine-specific settings.

## Optional recognition

The core demo does not install or call recognition models. Use a separate optional environment if desired:

```powershell
python -m pip install -r requirements-asr.txt
python src/asr_smoke_test.py --model tiny --limit 3 --output data/parsed/asr_actual_tiny.json
```

Model calls use local caches by default. Missing caches fail or produce a diagnostic status. Add `--allow-download` only if you want the relevant third-party model downloaded into your local cache. Model licenses, downloads, hardware and package compatibility are separate from this repository's core demo.

To turn a **new** report into study data, use a fresh review set. The following commands target the current checkout and must not replace an existing review set without deliberate backup:

```powershell
python src/build_asr_draft.py --input data/parsed/asr_actual_tiny.json
python src/export_asr_review_sheet.py
python tools/rebuild_data.py
```

`export_asr_review_sheet.py` refuses to overwrite an existing review CSV. For the prepared demo, inspect ASR results separately instead of replacing its authored-fixture draft. In a real new input checkout these files do not exist yet.

`asr_quality_eval.py --models tiny,base` records outputs, timings and heuristic flags for comparison. Log probabilities and suspicious-phrase flags are triage hints, not accuracy scores.

## OCR

```powershell
python -m pip install -r requirements-ocr.txt
python src/hardsub_ocr_extract.py --backend manga_ocr
```

Backend choices: `none`, `manga_ocr`, `easyocr`. The default `none` still extracts/preprocesses crops but clearly records `ocr_skipped`. Sample ratios and normalized crop regions are configurable. The bottom-line presets and brightness/edge heuristic are source-layout assumptions, not learned detection.

Existing OCR review CSVs are protected against accidental replacement. To run another experiment alongside the demo:

```powershell
python src/hardsub_ocr_extract.py --backend manga_ocr --limit 1 --sample-ratios 0.4 --output data/parsed/ocr_trial.json --review-csv data/review/ocr_trial.csv --image-dir data/ocr_frames/trial
```

Alternate experiment files are not automatically selected by the review page. Its current inputs are `data/parsed/hardsub_ocr.json` and `data/review/hardsub_ocr_review.csv`. Use a separate checkout for a full independent OCR review set.

## Approval semantics

- ASR: `review_status=approved` plus non-empty `japanese_text_corrected`.
- OCR: `approved=yes` plus non-empty `corrected_japanese_text`.
- Blank, pending or problem edits never replace the selected text.
- Model confidence never approves an edit.
- Rebuild order: original draft → current ASR decisions → current OCR decisions → learning dataset → rule preview → web dataset.
- Unapproved draft text remains visible as a draft for comparison; visibility is not approval.

CSV update is protected with a process-local lock and atomic replacement. This supports this single-server prototype; it is not a multi-process database or multi-user review system. The server does not automatically rebuild the dataset after a save.

## Checks

```powershell
python -m unittest discover -s tests -v
node tests/review_ui_test.cjs
```

Node is optional for serving the app; it is used only for the UI regression check. Running the full generated-media demo also requires FFmpeg and a Japanese-capable font.
