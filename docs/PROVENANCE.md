# Provenance and contribution boundaries

This is a personal learning prototype developed with substantial AI-assisted coding. The project owner's role includes identifying the Japanese-study need, defining requirements, selecting local materials, running the workflow and providing feedback. AI assistance contributed implementation, debugging, documentation and the publication refactor. This repository is not evidence that every line was independently authored without assistance.

## Original prototype

The copied starting point contained 14 Python scripts and five HTML/CSS/JavaScript files. It included the ASS parsing heuristics, FFmpeg clipping, faster-whisper integration, OCR sampling/preprocessing/backends, rule token/glossary preview, study UI, review UI and a local CSV-saving service.

The private original experiment's 607 raw / 524 merged / 20 sample counts and five-clip tiny/base inspection are historical local evidence. The source media and personal records are excluded. None of those counts describes the three-item public demo.

## Later publication preparation (October 2026)

The later, AI-assisted candidate makes these changes visible rather than presenting them as historical results:

- Removes source-specific titles and machine paths; uses generic project-relative manifests and explicit FFmpeg configuration.
- Reworks clipping and web dataset assembly for the newly authored demo and stable record indices.
- Adds `media_utils.py` and `review_policy.py`, consistent non-empty approval gates, separate ASR/OCR outputs and rebuild-from-draft revocation semantics.
- Changes the HTTP service to validate JSON booleans, reject empty approvals and atomically save CSV under a process-local lock.
- Fixes review-page failure handling: failed CSV saves cannot become approved browser records or advance the approval workflow.
- Restores the notes panel on short screens, separates public-demo localStorage keys, and labels fixture/model provenance.
- Adds self-authored fixtures, an asset-generation script, dependency groups, regression tests and explicit validation documentation.

These changes are publication-maintenance work on a copied prototype. They do not add a mature autonomous agent, RAG, trained model, reliable Japanese morphology, full translation or proven recognition accuracy.

## Third-party components

FFmpeg/ffprobe, faster-whisper and its underlying pretrained models, Pillow, manga-ocr/EasyOCR and their dependencies are external components. No model weights, third-party source trees, font files or source audiovisual works are bundled. Optional packages/models retain their separate licenses. A project-wide license is pending owner selection.

Generated demonstration cards and text fixtures were newly prepared with AI assistance for this candidate. Optional speech uses an installed local Windows SAPI Japanese voice; generated media are kept out of the publication package.
