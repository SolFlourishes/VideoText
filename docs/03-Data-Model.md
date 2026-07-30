CandidateFrame
Purpose

Represents one stable frame selected from the video.

Created By

Frame Selection

Consumed By

OCR

Contains
timestamp
image
metadata
OCRLine

Purpose

Represents one OCR detection.

Contains

text
confidence
bounding box
TextParagraph

Purpose

Represents one paragraph reconstructed from OCR lines within a single frame.

Contains

ordered text
location
source lines
SlideBuild

Purpose

Represents one observation of a slide.

Contains

timestamp
paragraphs
metadata
Slide

Purpose

Represents the canonical reconstruction of one slide.

Contains

slide number
canonical paragraphs
timing
Presentation (NEW)

Purpose

Represents the complete reconstructed presentation.

Contains

Presentation

metadata

slides[]

statistics

This becomes the object every exporter receives.