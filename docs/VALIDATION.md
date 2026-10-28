# Validation scope — 28–29 October 2026

This records small integration checks, not a product benchmark. No accuracy, WER/CER, AUC, performance improvement or general reliability claim follows from these results.

## Separate evidence sets

| Evidence set | Actual scope | Interpretation |
| --- | --- | --- |
| Historical private trial | 607 raw ASS records, 524 merged, 20 audiovisual samples; all draft; zero approved OCR corrections at source audit | Original local project evidence; source media and learning records are not distributed. |
| Historical tiny/base inspection | Five private audio clips, manual output/timing comparison | No gold-standard accuracy evaluation. Not reproduced here on the excluded source material. |
| New public-demo fixtures | Six newly authored JP/CN ASS lines, three merged study items | Text fixtures are explicitly marked; they are not recognizer output. |
| New generated speech/cards | Three 4.5-second cards with locally synthesized Japanese speech; FFmpeg clips contain H.264 video and AAC audio | Integration fixtures only. Default cross-platform demo uses a test tone instead of speech. |

## Actual recognition smoke tests

The existing local optional-model environment ran CPU inference from previously cached models:

- faster-whisper `tiny`, `int8`, Japanese, beam 1: three synthetic-speech clips produced draft transcripts.
- manga-ocr: one generated subtitle crop produced `今回はいまでの、` for the authored line `今日はいい天気ですね。`. This visible mismatch is retained as a limitation, not hidden behind a success status.
- EasyOCR Japanese: one generated crop produced `今日はいい天気ですね。`. The `ok` processing label and confidence do not approve the text; `needs_human_review` remains true.

There was no held-out corpus, formal annotation protocol, WER/CER calculation, noise/speaker/layout coverage or model-quality benchmark. A single matching EasyOCR example does not establish accuracy. Recognition outputs, confidence values, crops and weights are not in the publication package.

The demo study page continues to use clearly labelled authored fixtures. Optional recognition results are kept separate to prevent mixing fixtures and model output.

## Runtime and dependency scope

Core: a fresh Python 3.13 virtual environment installed only the pinned Pillow dependency; FFmpeg/ffprobe were supplied by the local system. Demo generation, clipping, cropping and data rebuild were exercised.

Optional model tests used the existing environment: faster-whisper 1.2.1, CTranslate2 4.8.1, manga-ocr 0.1.14, EasyOCR 1.7.2, transformers 5.7.0 and torch 2.13.0. This is not a fresh optional-dependency installation or a complete dependency lock. Other platforms, GPUs, Python versions and package combinations remain unverified.

No model was downloaded for these checks. New users may need compatible packages and separately licensed cached/downloaded models.

## Automated and browser checks

Regression scope includes ASS merging/tag cleaning/content heuristics, timestamps/crop input limits, non-empty explicit approval gates in both correction paths, stable IDs, approval revocation through a fresh rebuild, model-status separation, atomic-write failure, concurrent local CSV updates and HTTP payload validation.

A separate Node regression check simulates failed approval save, empty text and successful recovery. Browser checks exercised the actual local pages with self-authored fixtures: playback, search, study-state persistence, note persistence, CSV export, rejection of empty approval, CSV-confirmed approval, rebuild and revocation.

All approval-flow checks were synthetic actions by the assistant. They do not count as human-approved Japanese text. At handoff the three demo records are pending again; the original private project's zero OCR approvals remains unchanged.

## Not validated

Full ASR/OCR accuracy, robust hard-subtitle detection, automatic timeline alignment, morphology, full translation, JLPT labels, RAG, autonomous agent behaviour, multi-user deployment and production service security are not validated or delivered by these checks.
