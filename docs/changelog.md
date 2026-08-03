# Changelog

## 1.3.0

### Added

- Preserved raw OCR evidence for every candidate frame
- Frame-level and document-level OCR confidence statistics
- Document-level OCR confidence fields in CSV exports
- OCR Quality details in the processing-complete dialog

### Notes

- Confidence statistics are descriptive and use the original OCR evidence, including regions excluded by confidence filtering.
- Low-confidence regions do not alter OCR recognition, reconstruction, or exported text.

## 1.2.1

### Added

- Translation workflow workbook
- Initial AI Translation column
- Modified Translation column
- Verification workflow
- Protected Excel workbook

### Improved

- OCR reconstruction
- Boundary stitching
- Paragraph reconstruction
- Excel formatting

### Fixed

- Artificial continuation bullets
- Duplicate OCR boundaries
- Workbook protection issue
