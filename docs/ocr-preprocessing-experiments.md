# OCR preprocessing experiments

This opt-in developer tool compares conservative image variants without changing VideoText's production OCR defaults. It is intended to measure a suspected OCR problem before any production change is considered.

Supported variants are `original`, `grayscale`, `contrast`, `sharpen`, `threshold`, `upscale`, and `upscale_sharpen`. `original` is always run exactly once as the baseline.

Run one image with a verified reference:

```text
python tools/run_preprocessing_experiments.py --input-image diagnostics/sample2/frames/frame_003314/original.png --output-directory output/preprocessing-experiment --reference-text-inline "Verified text" --variants grayscale contrast sharpen threshold upscale upscale_sharpen
```

For a directory, use a UTF-8 JSON map from each image filename to its verified text. Inputs are processed by filename in deterministic order. The output contains per-image/per-variant `preprocessed.png`, raw OCR regions and text, reconstructed text, and metrics; image and root CSV, JSON, and Markdown summaries are also written.

CER is total character edit distance divided by verified reference characters. WER uses the equivalent word edit distance and word count. For multiple images, aggregate rates use total edits divided by total reference length; they are not averages of percentages.

The experiment runner sends OCR regions through VideoText's existing confidence filtering, reading order, and line reconstruction. It does not alter PaddleOCR configuration or production processing. To add a variant safely, add it to `src/ocr_preprocessing.py`, add deterministic tests, then compare it with `original` on manually verified frames before proposing any production change.

## Task 32E multi-frame result

The sample2 validation used nine manually verified diagnostic frames and all seven variants, for 63 completed OCR runs. Aggregate rates were calculated from summed edit counts rather than averages of frame percentages.

| Variant | Aggregate CER | Aggregate WER | Frames improved / worsened / unchanged | Runtime relative to original |
| --- | ---: | ---: | ---: | ---: |
| original | 2.36% | 5.62% | 0 / 0 / 9 | 1.00x |
| grayscale | 10.40% | 12.27% | 3 / 4 / 2 | 0.94x |
| contrast | 10.63% | 10.90% | 1 / 4 / 4 | 1.04x |
| sharpen | 4.57% | 6.98% | 3 / 3 / 3 | 1.02x |
| threshold | 3.93% | 4.43% | 4 / 2 / 3 | 0.90x |
| upscale | 2.39% | 5.62% | 3 / 3 / 3 | 1.85x |
| upscale_sharpen | 3.00% | 7.33% | 2 / 5 / 2 | 1.80x |

Threshold improved aggregate WER, improved more frames than it worsened, did not severely regress nearly-perfect frames, ran within the original runtime, and was not dependent on one poor frame. It failed the aggregate-CER criterion and the no-recurring-new-corruption criterion. Observed threshold regressions included missing section content, duplicated tokens (`p problems`, `a all`), an inserted underscore (`try_`), and character substitutions such as `l` for `1` and `andr` for `and`.

The production decision is to retain `original` preprocessing. All other variants, including threshold, remain experimental diagnostic tools only. No Task 32D or Task 32E result changes PaddleOCR configuration, preprocessing defaults, OCR recognition, or any production processing behavior.
