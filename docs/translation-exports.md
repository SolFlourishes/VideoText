# Translation Exports

The Translation Workbook remains VideoText's primary human-review artifact.
Its five columns retain source evidence, Initial AI Translation, and separate
editable human-review fields.

CSV and Markdown are downstream consumable views of the same completed,
immutable translation evidence. They do not select OCR source text or call a
provider. Records are ordered by job source order, target-language order, then
upstream row order. CSV has one row per source/language result and retains
structured provenance. Markdown groups records by source and target language
and presents useful provenance with each entry.

For Version 1.6 automated evidence, a successful result exports only its exact
Initial AI Translation. A failed result exports a blank translation and safe
failure information. Original text is never substituted. Modified and verified
translations are not yet imported from reviewed workbooks, so they are neither
invented nor marked as verified.

The common export façade delegates Excel directly to the 38F2 Translation
Workbook writer; it does not create a competing `.xlsx` layout. All destinations
are explicit and new-file-only. Existing export files cause a clear failure
rather than being overwritten. Reviewed-workbook import and re-export remain
future work.

For one video, translation files are placed in `<run-output>/translations/`.
For a batch-level translation job, they are placed beneath the selected batch
output root's `translations/` directory. This is intentionally separate from
the canonical OCR export table while remaining adjacent to the evidence run.

All AI-generated translations require human review. Translation Review
Intelligence adds deterministic, provider-neutral prioritization: Normal Review,
Review Recommended, or Translation Failed. Normal Review is not verification.
CSV appends stable `Review Status` and `Review Warnings` fields, Markdown shows
flagged statuses and reasons, and the workbook preserves the same assessment in
its visible review-status field and hidden metadata. See
`translation-review-intelligence.md` for current signals and limitations.
