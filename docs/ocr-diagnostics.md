# OCR Diagnostic Exports

OCR diagnostics export stage evidence for a selected VideoText run. They are
for investigation, not an OCR-improvement feature: the exports show where text
or ordering changes, but do not automatically prove why they changed.

## Running diagnostics

Run normal processing and export every candidate frame:

```powershell
python tools/export_ocr_diagnostics.py `
  --video sample_videos/sample2.mp4 `
  --output-dir diagnostics/sample2 `
  --all-candidates
```

Or use a compatible checkpoint and choose a resume mode:

```powershell
python tools/export_ocr_diagnostics.py `
  --checkpoint output/sample2/cache/ocr_results.pkl `
  --mode ocr_results `
  --output-dir diagnostics/sample2 `
  --frames 0,25,50,71
```

Use `--slides 1,2` when final slide mapping is desired, `--overwrite` to
replace an existing diagnostic directory, and `--strict` to make unavailable
requested frames or diagnostic write failures return a nonzero exit code.
The default low-confidence threshold is `0.80`; use
`--low-confidence-threshold` to change reporting only. No text is discarded.

## Output structure

```
diagnostics/sample2/
    run.json
    summary.md
    frames/frame_000025/
        original.png
        ocr_input.png
        regions.png
        reading_order.png
        regions.json
        raw_text.txt
        ordered_text.txt
        reconstructed_text.txt
    slides/slide_0006/
        slide.json
        pre_consolidation.txt
        final_text.txt
```

`original.png` is the exact candidate frame retained by VideoText.
`ocr_input.png` is the exact image passed to OCR. The current pipeline sends
that candidate image unchanged, so these files are presently identical.
`regions.png` labels original OCR regions and confidence; `reading_order.png`
labels the post-reading-order positions. `regions.json` preserves original OCR
sequence, reading order, coordinates, text, confidence, flags, reconstructed
lines, and paragraphs.

OCR sequence is the order returned by OCR. Reading order is the existing
VideoText ordering after confidence filtering; it may differ. A
`reading_order.pkl` replay does not preserve the original OCR sequence, and
the diagnostic report states that limitation instead of reconstructing it.

## Confidence and benchmark use

Low confidence does not always mean incorrect text, and high confidence does
not guarantee correct text. Compare selected diagnostic frame text with the
Task 32A accuracy-benchmark per-slide results to locate the stage where
evidence differs. CER/WER and diagnostics still do not by themselves identify
whether the cause is recognition, reading order, reconstruction, or
consolidation.

## OCR Quality summary

The normal VideoText completion dialog and processing CSV provide a
document-level OCR Quality summary. They preserve the original OCR regions
before reading-order confidence filtering, then report the region count,
minimum, maximum, mean, median, count and proportion below threshold, and the
active threshold. The CSV appends these eight fields:
`ocr_region_count`, `ocr_confidence_minimum`, `ocr_confidence_maximum`,
`ocr_confidence_mean`, `ocr_confidence_median`,
`ocr_below_threshold_count`, `ocr_below_threshold_proportion`, and
`ocr_confidence_threshold`.

The active processing threshold is 60%. A region below 60% is counted in the
summary even if it is later excluded from reconstruction. These statistics are
descriptive only: VideoText does not rewrite or correct OCR text. Review
low-confidence regions against the source video when exact wording matters.

The diagnostics command's separate default reporting threshold of 0.80 is
only for diagnostic flags and does not change processing or exported text.

## Privacy

Diagnostics export source-frame images and recognized text. Those artifacts
may contain sensitive presentation material, names, or client information.
Store them in an appropriate protected location and do not share them without
review.
