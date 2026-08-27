# VideoText 1.7.2 — OCR Output Quality & Script Awareness

## What’s New

VideoText now distinguishes preserved OCR evidence from text promoted into the
readable Presentation. A conservative assessment can withhold weak fragments
only when multiple observable signals agree. Raw OCR, reconstructed evidence,
confidence values, and source checkpoints remain preserved.

The promotion layer protects compact content such as short labels, numbers,
years, percentages, and formulas. Recognized Unicode text outside the current
OCR script profile remains visible and can be marked Review Recommended. Script
observation describes writing systems in OCR output; it does not identify
language and is not a calibrated confidence score.

OCR diagnostics schema 1.1 records the selected text, disposition, reasons,
observed scripts, available context, source frame, and whether the paragraph
was included in readable output.

## Replay Compatibility

Fresh processing, reading-order replay, and Batch Translate Existing Results
use the same Presentation-promotion logic. A trusted preserved
`reading_order.pkl` can therefore benefit without rerunning OCR when it contains
sufficient evidence. Missing context in older checkpoints defaults
conservatively to preserving text.

## Real-Checkpoint Validation

Validation used two preserved VideoText reading-order checkpoints without
rerunning OCR, video processing, frame selection, or reading-order
reconstruction.

- A weak isolated one-letter fragment was withheld while its raw OCR remained
  available. Years and percentages remained promoted. Similar high-confidence,
  visually substantial fragments remained visible by conservative design.
- Long Latin gibberish produced from imagery containing another writing system
  remained promoted. The affected paragraphs were marked Review Recommended
  because of weak OCR evidence, and their raw evidence remained preserved.

These results reflect the intended boundary: VideoText removes only weak text
supported by multiple independent indicators rather than using risky lexical
or dictionary guesses.

## Optional Batch Name

Batch Translate Existing Results now includes an optional **Batch Name** used
to distinguish generated translation files. For example, `Mod 2` may produce:

```text
Mod 2 - Spanish.xlsx
Mod 2 - German.xlsx
Mod 2 - Translation.csv
Mod 2 - Translation.md
```

Blank input preserves previous filenames. Windows-invalid filename characters
are sanitized. Source result folder names, checkpoints, and evidence are never
renamed or modified.

## Limitations

- Long high-confidence Latin gibberish cannot safely be distinguished from
  legitimate Latin-script text using downstream text-only analysis.
- If OCR emits incorrect Latin characters for another visual writing system,
  Unicode inspection cannot recover the original visual script.
- Image-level script identification, automatic OCR-language/model selection,
  and multilingual source OCR configuration are not included.
- Chart and diagram relationships or semantics are not interpreted.
- High-confidence fragment-like text can remain visible when independent weak
  evidence is insufficient.
- No restore-withheld-content GUI is included. Diagnostics and raw evidence are
  the audit path.
- Existing translation provider, locale, model-pack, regional-localization,
  cloud/BYOK, and mandatory human-review limitations remain unchanged.
