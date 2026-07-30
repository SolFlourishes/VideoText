Frame Selection

Purpose

Find stable frames.

Input

Video

Output

CandidateFrames

Algorithm

(Current implementation)

Stable-frame detection using frame similarity.

Future Improvements

SSIM
Scene detection
OCR

Purpose

Extract text.

Input

CandidateFrame

Output

OCRLine

Current

PaddleOCR

Reading Order

Purpose

Determine reading sequence.

Input

OCRLine

Output

Ordered OCRLine

Paragraph Reconstruction

Purpose

Group related lines.

Input

Ordered lines

Output

Paragraphs

Slide Consolidation

Purpose

Combine multiple observations into one canonical slide.

Input

SlideBuilds

Output

Slide

Implementation Notes

Paragraph matching
Consensus selection
Duplicate removal

Future

OCR confidence
Voting
Spell checking
AI consensus