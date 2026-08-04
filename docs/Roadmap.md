# VideoText Roadmap

**Project:** VideoText

**Current Release:** Version 1.4.0

**Mission**

VideoText transforms visual instructional content into accurate, accessible, and human-verifiable documents that support translation, accessibility, preservation, and reuse while preserving the integrity of the original content.

---

# Vision

VideoText began as a tool for extracting text from presentation videos. It has evolved into a modular platform for transforming visual instructional content into structured, reusable, and accessible documents.

The processing pipeline is intentionally deterministic.

Each stage produces evidence for the next stage while preserving prior evidence. Downstream stages enrich information without modifying the original source evidence.

---

# Guiding Principles

1. Accuracy over automation
   - Never invent or rewrite content.
   - Preserve original meaning.

2. Human-in-the-loop
   - AI assists.
   - Humans approve.

3. Accessibility by design
   - Outputs support accessibility rather than reproducing appearance.

4. Deterministic processing
   - Improvements are measurable.
   - Behavior is benchmarkable.
   - Avoid generative "magic fixes."

---

# Current Capabilities (Version 1.4)

## OCR

- Geometry-aware reading order
- Paragraph reconstruction
- Duplicate suppression
- Boundary stitching
- OCR confidence preservation
- Raw OCR evidence preservation
- OCR quality statistics

## OCR Architecture

- Engine abstraction
- PaddleOCR adapter
- Engine registration
- Engine discovery
- Shared OCR contract
- Replay compatibility

## Export

- Markdown
- CSV
- Excel Translation Workbook

## Diagnostics

- OCR diagnostics
- CER/WER benchmarking
- Confidence statistics
- OCR preprocessing experiments

---

# Upcoming Releases

# Version 1.5

## Theme

OCR Engine Evaluation

### Release Goal

Evaluate multiple OCR engines using the framework established in Version 1.4.

### Planned Features

- Additional OCR engine adapters
- Side-by-side engine comparison
- CER benchmarking
- WER benchmarking
- Performance benchmarking
- Accuracy summaries
- Engine evaluation reports

### Evaluation status

- PaddleOCR and RapidOCR now have isolated adapter, accuracy, and performance
  evidence; see [OCR Engine Evaluation Report v1](ocr-engine-evaluation-report-v1.md).
- Paddle remains the only production/default engine. Broader corpus coverage,
  RapidOCR model-license verification, physical offline validation, and an
  isolated packaging proof are required before any user-facing selection.

### Out of Scope

- OCR correction
- GUI engine selection
- Automatic engine selection
- Cloud OCR

---

# Version 1.6

## Theme

Translation Foundation

### Release Goal

Add AI translation as a downstream transformation while preserving original OCR evidence.

### Planned Features

- Translation abstraction
- Translation provider interface
- Source and target language selection
- Translation stored separately from OCR
- Translation provenance
- Initial provider/local model
- Translation export
- Basic GUI controls

---

# Version 1.7

## Theme

Translation Workflow

### Planned Features

- Multiple translation providers
- Batch translation
- Glossaries
- Preferred terminology
- Translation notes
- Re-translation
- Quality review workflow

---

### Version 1.8

### Theme

AI Assisted Understanding

### Goal

Augment OCR evidence using AI while preserving the deterministic OCR pipeline.

### Features

- Vision providers
- Local vision models
- Cloud vision models
- Structured slide understanding
- Diagram detection
- Figure descriptions
- Equation recognition
- Accessibility annotations
- Optional AI summaries

### Out of Scope

- Replacing OCR
- Automatic rewriting
- Mandatory cloud services

---

# Version 2.0

## Theme

Accessibility Edition

### Planned Features

- Accessible Word export
- Heading structure
- Accessible tables
- Lists
- Logical reading order
- Screen-reader optimization
- WCAG / Section 508 / ADA support

---

# Version 2.1

## Theme

Accessible Multimedia Transcript

### Planned Features

- Speech-to-text
- Speaker identification
- Slide timing
- Visual notes
- Combined accessible transcript

---

# Version 2.2

## Theme

Accessibility Workflow

### Planned Features

- Accessibility review
- Reviewer notes
- Version tracking
- Reading-order validation
- Accessibility reports

---

# Future Milestones

## Portable Deployment Experience

- Portable ZIP deployment
- No administrator rights
- No installer required
- First-run experience
- Environment validation
- OCR model verification
- Output-folder creation
- Update notification

---

## GUI Workflow & Usability

- Graceful Stop Processing
- Safe Exit During Processing
- Processing state management
- Improved progress reporting
- Remember last settings
- Keyboard shortcuts
- Optional session recovery

---

## Developer Platform

- OCR plugins
- Translation plugins
- Export plugins
- Accessibility plugins
- Custom processing workflows

---

# Long-Term Vision (3.x)

VideoText becomes a complete accessibility and instructional-content transformation platform supporting:

- OCR
- Translation
- Accessibility remediation
- Accessible document generation
- Multimedia transcripts
- Multiple export formats
- Compliance reporting

---

# Design Principles

Every feature should be:

- Deterministic
- Measurable
- Benchmarkable
- Human-verifiable
- Accessible
- Modular
- Maintainable
- Backward compatible whenever practical

---

# Success Metric

Every proposed feature should answer one question:

> **Does this improve accuracy, accessibility, or human efficiency without reducing trust?**

If the answer is **no**, it does not belong in VideoText.
