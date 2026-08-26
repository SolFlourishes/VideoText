# VideoText 1.7.0 — Translation Review

## What's New

VideoText 1.7 adds the minimum evidence-preserving foundation for human
translation review. Source OCR, the original AI translation, and any verified
translation remain separate. Human review states are **Unreviewed**,
**Accepted**, **Edited / Verified**, and **Flagged**. A failed provider result
remains **Translation Failed** and cannot become valid through review metadata.

## Review Intelligence

**Normal Review**, **Review Recommended**, and **Translation Failed** remain
separate from human review status. Observable reasons can identify translation
failure, source-copy similarity, numeric preservation concerns, structure loss,
and related defensible warning signals. These signals prioritize inspection;
they are not calibrated translation confidence and do not determine correctness.

## Excel Review Workbook

The filterable review table contains:

1. Slide
2. Source OCR Text
3. Original AI Translation
4. Verified Translation
5. Human Review Status
6. Translation Review Status
7. Review Reasons
8. Reviewer Notes
9. Target Language
10. Provider
11. Model

Source OCR, original AI translation, automated review evidence, language, and
provider/model provenance are protected. Verified Translation, Human Review
Status, and Reviewer Notes remain editable with status validation. Existing
BY_LANGUAGE, BY_SOURCE, COMBINED, and SEPARATE grouping modes are preserved.

## Provider Selection

When the translation provider changes, VideoText now deselects target locales
unsupported by the new provider while preserving selections that remain valid.
Returning to a provider makes its locales available again without automatically
reselecting them.

## Compatibility

Existing OCR workflows are unchanged. Translation remains downstream of OCR,
and CSV/Markdown behavior, grouping modes, and the local/cloud provider
architecture remain compatible.

## Not Included

Version 1.7 does not add reviewed-workbook import, persistent review projects,
a dedicated review GUI, batch translation of existing OCR results, automatic
model improvement from edits, or calibrated translation confidence. The local
M2M100 model uses generic language tokens and does not guarantee true regional
localization.
