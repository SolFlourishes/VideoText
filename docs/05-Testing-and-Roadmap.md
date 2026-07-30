Benchmark Videos

Manual OCR diagnostic

Automated tests do not require the full OCR runtime. To inspect PaddleOCR
output for a saved candidate-frame PNG, run:

    python tools/manual_ocr_probe.py --image <candidate-frame.png>

The manual probe requires OpenCV, PaddleOCR, and PaddlePaddle. It can also
select a PNG from a candidate-frame directory with
``--candidate-frames-dir <directory> --index 8``.

Video A

Expected:

12 slides

Video B

Expected:

TBD
Metrics

Measure

Slides detected
Duplicate paragraphs
OCR errors
Missing slides
Release Plan
Version 1.0 (This Week)

Must complete:

Markdown export
Presentation model
Consolidation
Test on two videos
Version 1.1
DOCX
Images
Better consensus
Version 2.0
AI cleanup
Translation
PPTX export

Current work - 7-22
Sprint 1 (Version 1.0)

Our sprint backlog is now fixed.

Story 1

Create the Presentation model

Priority: P1

Definition of Done:

Presentation class exists.
Contains metadata and slides.
Existing pipeline compiles.
No behavioral changes.
Story 2

Refactor Markdown exporter

Priority: P1

Definition of Done:

Exporter accepts Presentation.
Markdown output is identical.
Existing tests pass.
Story 3

Improve Slide Consolidation

Priority: P1

Definition of Done:

Duplicate OCR paragraphs significantly reduced.
No regression in slide ordering.
Video A output improves.
Story 4

Run Benchmark Video B

Priority: P1

Definition of Done:

Entire pipeline runs.
Markdown generated.
Record findings only.
No immediate coding based on one failure.
