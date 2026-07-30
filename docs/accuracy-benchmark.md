# OCR Accuracy Benchmark

VideoText's accuracy benchmark compares reconstructed slide text with manually
corrected reference text. It creates repeatable evidence before an OCR,
reading-order, paragraph-reconstruction, or consolidation change is considered.

## Reference format

References are UTF-8 JSON files:

```json
{
  "video": "sample2.mp4",
  "slides": [
    {
      "slide_id": "1",
      "frame_index": 0,
      "reference_text": "Mobilizing Spiritual Systems of Belief",
      "notes": "Optional reviewer note"
    }
  ]
}
```

`slide_id` is required and must be a string. `frame_index` is an optional
integer or `null`. `reference_text` is required. `notes` is optional. Unicode
is preserved.

Candidate JSON uses the same shape, replacing `reference_text` with
`candidate_text`. The tool also accepts VideoText's existing CSV export. It
groups paragraph rows by `Slide Number` in CSV order and joins that slide's
paragraph text with line breaks. CSV does not carry frame indices.

## Metrics and normalization

- **CER** is `(substitutions + deletions + insertions) / reference characters`.
- **WER** uses the same operation counts over whitespace-separated words.
- Exact normalized matching normalizes line endings, trims outer whitespace,
  and collapses repeated internal whitespace. It deliberately does not
  lowercase text.

An empty reference has no CER/WER denominator, so its rate is reported as
`null` in JSON and `n/a` in Markdown rather than causing a division error.

## Slide alignment

The benchmark aligns slides deterministically:

1. Match a slide when its `slide_id` is unique in both datasets.
2. For still-unmatched slides, match the same `frame_index` only when it is
   unambiguous in both datasets.
3. Leave all other slides unmatched.

Duplicate IDs are reported explicitly. They are not silently discarded or
arbitrarily matched; a unique frame index can still resolve them in step 2.

## Running a benchmark

```powershell
python tools/run_accuracy_benchmark.py `
  --reference benchmarks/sample2/reference.json `
  --candidate benchmarks/sample2/candidate.json `
  --output-dir benchmark-results/sample2
```

The command writes `report.json` for tools and `report.md` for review. The
Markdown report includes aggregate metrics, coverage, per-slide metrics,
worst-performing slides, and duplicate/alignment warnings.

## Interpretation

CER and WER measure textual differences, not their cause. A difference may
come from OCR recognition, reading order, paragraph reconstruction, slide
consolidation, or a combination of those stages. Use the per-slide results and
the original run artifacts to identify the responsible stage before changing
pipeline behavior.
