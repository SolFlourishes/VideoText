# Changelog

## 1.7.1

### Batch Translate Existing Results

### Added

- A dedicated workflow for translating multiple completed VideoText result
  folders from their preserved `cache/reading_order.pkl` checkpoints
- Entry points in the File menu and the main Batch Processing area
- Existing Local Translation and OpenAI Cloud choices, multiple target locales,
  all existing output grouping modes, and existing review intelligence
- Ordered validation with clear invalid/duplicate reporting and explicit
  confirmation before mixed valid/invalid selections continue

### Behavior and limitations

- OCR and video processing are not rerun, and source result folders remain
  unchanged. New translation artifacts use a separate uniquely named workspace.
- Partial translation failures remain visible and do not abort all remaining
  sources or target locales.
- Reading-order caches use Python pickle and should only be reused from trusted
  VideoText runs. Arbitrary historical cache compatibility and cache migration
  are not provided.
- Translation cancellation and reviewed-workbook import are not included.

## 1.7.0

### Translation Review

### Added

- Human review states: Unreviewed, Accepted, Edited / Verified, and Flagged
- Separate Verified Translation and Reviewer Notes fields without replacing
  source OCR or the original AI translation
- An 11-column Excel review table with editable human-review fields, protected
  evidence/provenance fields, filtering, and data validation
- Central reviewed-translation resolution that uses a valid human edit only for
  Edited / Verified results; Translation Failed remains failed

### Changed

- Translation Review Workbooks expose source OCR, original AI translation,
  verified translation, human and automated review states, review reasons,
  notes, target language, provider, and model
- Provider changes now deselect unsupported target locales while preserving
  selections valid for the newly selected provider

### Compatibility and limitations

- Normal Review, Review Recommended, Translation Failed, their observable
  warning reasons, and all existing workbook grouping modes remain supported.
- Review signals prioritize inspection; they are not calibrated translation
  confidence and do not establish correctness.
- OCR workflows and existing CSV/Markdown translation behavior remain
  compatible. Local/cloud provider architecture is unchanged.
- Reviewed-workbook import, persistent review projects, and a dedicated review
  GUI remain future work.
- The local M2M100 model uses generic language tokens and does not guarantee
  regional localization.

## 1.6.0

### Translation Foundation

### Added

- Optional Local Translation using the separately distributed M2M100 pack,
  with offline operation and no API key or cloud fallback
- Optional OpenAI Cloud translation using a user-supplied, session-only API key
- Multiple target locales and deterministic multi-video/multi-language jobs
- Evidence-preserving Translation Review Workbooks plus translation CSV and
  Markdown exports
- Deterministic review intelligence with Normal Review, Review Recommended,
  and Translation Failed textual statuses
- Keyboard-accessible locale selection and dedicated Accessibility Help

### Changed

- Translation artifacts are saved in a `translations/` directory beneath their
  originating single-video run (or beneath the batch output root)
- The GUI distinguishes canonical OCR Outputs from Translation Outputs and uses
  a compact keyboard-accessible target-locale selector
- Completion summaries present OCR Quality, Translation, and Translation Outputs
  as separate sections, with human-readable target locale lists

### Notes

- OCR remains canonical; translation is an optional downstream layer and never
  overwrites OCR evidence.
- All machine translations require human review and are never automatically
  marked verified.
- The local M2M100 runtime uses generic Spanish and Portuguese tokens. VideoText
  preserves requested locale provenance but does not guarantee regional wording.
- OpenAI Cloud requires internet access, a user-provided key, and may incur API
  charges. Video and image data are not sent by the translation provider.

## 1.5.0

### Added

- Isolated RapidOCR feasibility, accuracy, performance, and confidence evidence
- Versioned human-verified nine-frame OCR-engine benchmark corpus and reproducible reports
- Formal [OCR Engine Evaluation Report v1](ocr-engine-evaluation-report-v1.md)

### Notes

- PaddleOCR remains the only production/default engine.
- RapidOCR remains evaluation-only pending broader accuracy, physical offline,
  PyInstaller, and model-license validation.
- The verified v2 corpus now provides the authoritative Version 1.5 accuracy
  baseline: PaddleOCR remains the default after lower reconstructed CER/WER.
- JSON, CSV, and Markdown authoritative reports now include accuracy,
  performance, confidence distribution, recommendation, and limitation sections.

## 1.4.0

### Added

- Engine-neutral OCR contract and PaddleOCR adapter
- Deterministic OCR engine registration and discovery with Paddle as the only
  built-in default
- Shared OCR contract for preprocessing experiments and benchmarks
- VideoText Windows application icon

### Notes

- Version 1.4 does not add user-facing engine selection or a second OCR engine.
- The manual Paddle probe remains a developer diagnostic for raw PaddleOCR
  responses. Engine comparison work is planned for Version 1.5.

## 1.3.0

### Added

- Preserved raw OCR evidence for every candidate frame
- Frame-level and document-level OCR confidence statistics
- Document-level OCR confidence fields in CSV exports
- OCR Quality details in the processing-complete dialog

### Notes

- Confidence statistics are descriptive and use the original OCR evidence, including regions excluded by confidence filtering.
- Low-confidence regions do not alter OCR recognition, reconstruction, or exported text.

## 1.2.1

### Added

- Translation workflow workbook
- Initial AI Translation column
- Modified Translation column
- Verification workflow
- Protected Excel workbook

### Improved

- OCR reconstruction
- Boundary stitching
- Paragraph reconstruction
- Excel formatting

### Fixed

- Artificial continuation bullets
- Duplicate OCR boundaries
- Workbook protection issue
