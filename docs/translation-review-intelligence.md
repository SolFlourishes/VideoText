# Translation Review Intelligence

All AI-generated translations require human review. VideoText 1.6 adds a
deterministic, provider-neutral review-prioritization layer; it does not score
translation confidence or determine whether a translation is correct.

Each completed result receives the stable `translation-review-v1` assessment:

- **Normal Review** means no implemented warning signal was observed. It does
  not mean verified or correct.
- **Review Recommended** means one or more observable signals warrant
  particular human attention. It does not necessarily mean the translation is
  incorrect.
- **Translation Failed** means no usable provider translation was produced.

The currently implemented warnings are provider failure, substantial
source-copy similarity, numeric-token mismatch, and substantial line/list
structure loss. The source-copy heuristic requires at least four words, twenty
alphabetic characters, and 0.96 normalized similarity. Structure loss is
considered only for three or more source lines or lists with two or more
bullets. These are deterministic review heuristics, not calibrated measures of
translation quality.

Source-OCR-low-confidence warnings are deferred. Translation records do not
currently retain a direct frame/region confidence link, and VideoText will not
duplicate or infer OCR-quality statistics at the translation boundary.

Review status is visible in the Translation Workbook and stored with stable
warning codes and compact context in its hidden `_VideoText_Metadata` sheet.
Translation CSV adds `Review Status` and `Review Warnings`; Markdown shows
flagged statuses and concise reasons. None of these outputs rewrites provider
text, OCR evidence, human edits, or verification fields.
