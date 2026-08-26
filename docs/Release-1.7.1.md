# VideoText 1.7.1 — Batch Translate Existing Results

## What's New

VideoText 1.7.1 adds a dedicated workflow for translating multiple previously
completed VideoText runs without repeating video processing or OCR:

```text
Completed VideoText result folders
→ cache/reading_order.pkl
→ reconstructed Presentation
→ existing translation pipeline
→ translation outputs
```

Open **File → Batch Translate Existing Results...**, or select **Batch
Processing** and choose **Translate Existing Results...**. Add completed result
folders, choose a separate output root, and select the provider, target locales,
grouping, and output formats.

## Preserved Behavior

- Local Translation and OpenAI Cloud use their existing availability, BYOK, and
  preflight rules.
- Multiple target locales and BY_LANGUAGE, BY_SOURCE, COMBINED, and SEPARATE
  grouping remain available.
- Existing translation provenance, Normal Review, Review Recommended,
  Translation Failed, and their warning reasons remain intact.
- Partial translation failures remain visible while later work continues.
- Source OCR and original AI translation evidence are never overwritten.

## Source Safety

The workflow reads the preserved `cache/reading_order.pkl` checkpoint and does
not rerun OCR or silently fall back to video processing. Source result folders
remain unchanged. New files are written beneath a unique
`translation-existing-results` workspace in the selected output root.

Python pickle caches should only be opened from trusted VideoText runs created
on a trusted computer.

## Compatibility and Limitations

VideoText validates the selected reading-order checkpoints but does not promise
compatibility with arbitrary historical cache schemas and does not provide
cache migration. Translation cancellation and reviewed-workbook import are not
included. Local-model regional localization and supported locales are unchanged
from 1.7.0.
