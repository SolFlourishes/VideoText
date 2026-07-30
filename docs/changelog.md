Version 1.2.0 – OCR Accuracy and Reconstruction Release

New Features

Reusable CER/WER accuracy benchmarking and expanded OCR diagnostic exports.
Manifest-driven preprocessing validation across 9 representative frames, 7 variants, and 63 successful OCR runs.

Enhancements

Improved geometry-based OCR text reconstruction and reading order.
Safer edge-aware duplicate suppression, including correction of the regression that removed legitimate interior words.
Punctuation-aware joining of OCR regions.

Production Decision

Original preprocessing remains the production default. No experimental preprocessing variant consistently improved overall accuracy across the multi-frame benchmark.
Preprocessing variants remain diagnostic and experimental only.

Known Limitations

OCR recognition errors have not been eliminated; exported text should continue to be reviewed where accuracy is important.

Version 0.4.0 – Reconstruction Engine Complete

New Features

Complete OCR reconstruction workflow from candidate frames to semantic paragraphs.
Improved line reconstruction using bounding-box overlap rather than center-point grouping.
Reading-order reconstruction for complex slide layouts.
Paragraph reconstruction with support for wrapped numbered items.
Automatic inference of missing bullet lists when OCR omits bullet glyphs.
Inferred bullet classification as BULLET for downstream exporters.
Improved handling of multi-line numbered and bulleted content.

Enhancements

More robust geometric heuristics for layout interpretation.
Better preservation of author intent through semantic reconstruction.
Stable paragraph typing for export workflows.

Known Limitations

Decorative layouts may require future refinement.
Complex tables and SmartArt are not fully reconstructed.
Multi-column layouts are supported on a best-effort basis.

Next Milestone

Slide Consolidation: merge multiple observations of the same slide into a single canonical representation.
