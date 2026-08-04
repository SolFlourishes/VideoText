# VideoText OCR Engine Benchmark v1

This curated, human-verified initial corpus contains four saved frames from
`sample_videos/packaged_ocr_smoke.avi`. The exact source text was transcribed
by visually reviewing the saved source frames, not copied from OCR output.

The corpus covers a title, numbered/body layout, multi-line continuation text,
and compact labels. It intentionally does not yet represent low contrast,
tables, charts, diagram labels, text over graphics, or compression artifacts;
those require separately reviewed references before inclusion.

Scoring uses Unicode NFC. Windows, Unix, and legacy Mac line endings are
normalized, then all whitespace is collapsed to one space. Case, punctuation,
and bullet characters remain significant. Empty reference text has undefined
CER/WER (`null`); empty candidate text is scored normally against a non-empty
reference. Both engines receive the exact same saved BGR image and results are
recorded before and after the accepted geometry-based line reconstruction.
