# VideoText Architectural Decisions

This record captures the durable design choices that guide VideoText. It is an
engineering reference, not a replacement for the detailed pipeline description
in [Architecture](02-Architecture.md).

## Evidence first

### Preserve raw OCR evidence

VideoText retains the OCR regions returned for each candidate frame before
confidence filtering or reconstruction. Raw text, confidence, and geometry are
evidence: later stages can interpret them, but must not silently erase the
record of what the engine observed. This supports diagnostics, replay,
confidence reporting, benchmark work, and informed human review.

### Confidence informs review; it does not rewrite text

Confidence is a descriptive property of an OCR observation, not proof that a
different spelling is correct. The centralized `MIN_CONFIDENCE` threshold may
exclude a region from working reconstruction, while raw evidence remains
available for inspection and document-level statistics. VideoText does not use
confidence to invent, correct, or replace extracted text.

## OCR architecture

### Use canonical `OCRResult` objects

Every OCR engine adapter returns the same canonical text, confidence, and
axis-aligned bounding-box representation. The processing pipeline, reading
order, reconstruction, diagnostics, and checkpoints therefore depend on a
stable VideoText model rather than a vendor response format.

### Isolate OCR vendors behind adapters

Engine-specific imports, model initialization, inference calls, and response
parsing belong in the corresponding adapter. This preserves lazy model loading
and lets the rest of the application remain engine-neutral. PaddleOCR is the
only registered and default production engine; RapidOCR is evaluation-only and
is deliberately outside normal discovery, processing, packaging, and GUI
selection.

## Replay and checkpoints

### Keep checkpoints for deterministic replay

Candidate-frame, OCR-result, and reading-order checkpoints let users repeat
later processing and export stages without re-running the expensive earlier
stages. This makes formatting, reconstruction, and diagnostic work fast and
repeatable.

### Store canonical data, never backend objects

Checkpoints contain VideoText candidate frames and canonical OCR evidence, not
Paddle or other backend objects. Canonical checkpoint data is more portable,
keeps replay independent of an OCR vendor's object lifecycle, and protects
downstream processing from adapter implementation details.

## Engine evaluation

### Separate evaluation from production

Engine comparison runs use saved frames, shared preprocessing, reconstruction,
normalization, and scoring. They are isolated from the production registry and
normal workflow so an experimental adapter cannot change a user's extraction
by accident.

### Run one engine in normal processing

Normal processing runs one selected production engine once. Running multiple
engines would multiply processing time and create an ambiguous consensus policy.
Multi-engine execution belongs only in explicit evaluation work with documented
inputs and results.

## Translation and review

### Translation is downstream from OCR

OCR/reconstructed text is the source evidence. Translation is a separate,
later transformation for review and editing; it must not overwrite source OCR
content or alter the deterministic extraction pipeline.

### Preserve provenance through human review

Human verification, translation edits, and future review annotations are
layers associated with the source evidence. They record who reviewed or changed
what without replacing raw OCR observations, reconstructed source text, or
their provenance.

## Accessibility

Accessibility is a review and transformation layer, not another OCR pass. Its
purpose is to communicate the instructional information in accessible formats
while retaining traceability to the reconstructed source. Accessibility
annotations and remediation therefore complement, rather than rewrite, OCR
evidence.

## Enduring principles

- **Accuracy over automation:** do not guess missing content or hide uncertainty.
- **Human in the loop:** automation prepares evidence; people make consequential judgments.
- **Accessibility by design:** exported information should be usable, editable, and reviewable.
- **Deterministic processing:** equivalent inputs and settings should produce traceable, repeatable results.
- **Preserve evidence:** later stages enrich earlier observations instead of destroying them.
- **AI augments rather than replaces human judgment:** any future AI capability remains downstream, attributable, and reviewable.

## Related references

- [Architecture](02-Architecture.md)
- [Data Model](03-Data-Model.md)
- [Algorithms](04-Algorithms.md)
- [OCR Engine Evaluation](ocr-engine-evaluation.md)
- [OCR Engine Evaluation Report v1](ocr-engine-evaluation-report-v1.md)
