# VideoText Roadmap

**Project:** VideoText

**Current Release:** Version 1.6.0

---

# Mission

> **VideoText transforms visual instructional content into accurate, accessible, and human-verifiable documents while preserving evidence throughout every stage of processing.**

Rather than replacing human expertise, VideoText prepares structured evidence so reviewers, translators, instructional designers, and accessibility specialists can work more efficiently and with greater confidence.

---

# Vision

VideoText began as an OCR extraction utility.

It is evolving into an evidence-preserving content processing platform where every processing stage enriches prior work without replacing it.

```
Video
    ↓
OCR
    ↓
Verified OCR (optional)
    ↓
Translation (optional)
    ↓
Verified Translation (optional)
    ↓
Accessibility (optional)
    ↓
Verified Accessible Outputs
```

Each layer preserves provenance.

---

# Guiding Principles

## 1. Accuracy over Automation

- Never invent content.
- Never silently rewrite evidence.
- Preserve original meaning.

## 2. Human in the Loop

- AI proposes.
- Humans verify.
- Review is optional but always supported.

## 3. Accessibility by Design

Outputs communicate information rather than reproduce appearance.

## 4. Deterministic Processing

- Benchmarkable
- Measurable
- Reproducible

Avoid generative "magic fixes."

## 5. Preserve Evidence

Original evidence is never discarded.

Every processing stage adds information rather than replacing previous work.

---

# Current Capabilities (Version 1.6)

## OCR

- Geometry-aware reading order
- Paragraph reconstruction
- Duplicate suppression
- Boundary stitching
- Raw OCR evidence preservation
- OCR confidence preservation
- OCR quality statistics

## OCR Framework

- Engine abstraction
- PaddleOCR adapter
- Engine discovery
- Engine registry
- Shared OCR contract
- Replay compatibility

## Benchmarking

- Human-verified benchmark corpus
- OCR engine evaluation
- CER/WER benchmarking
- Confidence analysis
- Performance benchmarking
- Review utility

## Export

- Markdown
- CSV
- Excel Translation Workbook

## Diagnostics

- OCR diagnostics
- OCR preprocessing experiments
- Confidence statistics

---

# Version 1.6

## Theme

Translation Foundation

### Goal

Introduce translation as a downstream processing stage while preserving verified OCR evidence.

### Delivered Features

- Translation abstraction layer
- Translation provider interface
- Local and cloud translation providers
- Source/target language selection
- Translation provenance
- Translation stored separately from OCR
- Translation exports
- Initial GUI integration

Version 1.6 also delivers Translation Review Workbook/CSV/Markdown outputs,
deterministic review warnings, OpenAI BYOK preflight and safe error handling,
an optional external Local Translation Pack, and keyboard/accessibility help.
OCR remains canonical and all translations require human review.

---

# Version 1.7

## Theme

Translation Review Workflow

### Goal

Create a human-centered translation workflow.

### Delivered Features

- Separate source OCR, original AI translation, and verified translation layers
- Human review states: Unreviewed, Accepted, Edited / Verified, and Flagged
- Reviewer notes and deterministic translation review reasons
- Filterable Excel review workbook with protected evidence and provenance
- Central reviewed-translation resolution without promoting failed translations
- Existing translation grouping modes and CSV/Markdown compatibility
- Provider switching that removes unsupported locale selections

### Deferred Translation Work

- Reviewed-workbook import and persistent human review tracking
- Possible use of verified translations as quality-evaluation/reference data
- Dedicated translation review workspace
- Batch Translate Existing Results using completed run folders or trusted
  `reading_order.pkl` checkpoints, skipping OCR across multiple results
- Re-translation with another language, provider, or model without repeating OCR
- Broader validated local-language support
- True offline regional localization, including Canadian English (`en-CA`)
- Glossaries and preferred terminology

---

# Version 1.8

## Theme

AI-Assisted Understanding

### Goal

Use AI to enrich OCR evidence without replacing deterministic OCR.

### Planned Features

- Vision providers
- Local vision models
- Cloud vision models
- Diagram understanding
- Figure descriptions
- Equation recognition
- Structured slide understanding
- Accessibility annotations
- Optional AI summaries

### Out of Scope

- Replacing OCR
- Automatic rewriting
- Mandatory cloud services

---

# Version 1.9

## Theme

Modern User Experience

### Goal

Transform VideoText into a modern, accessible desktop application while preserving its simplicity and offline-first philosophy.

### Planned Features

### Modern Interface

- Updated visual design
- Improved typography
- Better spacing
- Responsive layout
- High-DPI support

### Workflow

- Clear step-by-step workflow
- Better progress reporting
- Recent projects
- Processing summary
- Improved dialogs

### Processing Controls

- Stop Processing
- Graceful cancellation
- Safe Exit
- Background cleanup
- Session recovery (optional)

### Accessibility

- Keyboard-first navigation
- Screen-reader improvements
- Focus indicators
- High-contrast compatibility
- DPI validation

### Workspace Foundation

Prepare the interface for:

- OCR Review
- Translation Review
- Accessibility Review
- AI-assisted review

### Design Goals

The interface should feel:

- Professional
- Calm
- Trustworthy
- Accessible
- Modern

### Out of Scope

- Electron/WebView rewrite
- Administrator requirements
- Decorative animations

---

# Version 2.0

## Theme

Accessibility Edition

### Planned Features

- Accessible Word export
- Heading structure
- Accessible tables
- Lists
- Reading order
- Screen-reader optimization
- WCAG support
- Section 508 support
- ADA support

---

# Version 2.1

## Theme

Accessible Multimedia Transcript

### Planned Features

- Speech-to-text
- Speaker identification
- Slide timing
- Visual descriptions
- Accessible multimedia transcript

---

# Version 2.2

## Theme

Human Verification Workspace

### Goal

Provide a unified review experience for OCR, translation, and accessibility.

### Planned Features

- Side-by-side image and text review
- Accept/Edit/Flag workflow
- OCR-region highlighting
- Verified text layer
- Reviewer attribution
- Review progress
- Save and resume
- Project-based review
- Optional verified-only exports

---

# Ongoing Project Initiatives

These continue across multiple releases.

## Benchmark Suite

- Expand verified benchmark corpus
- Additional sample videos
- Additional content categories
- Multilingual corpus
- Long-term regression testing

## Portable Deployment

- Portable ZIP
- No administrator rights
- First-run experience
- Environment validation
- OCR model verification
- Output-folder creation
- Update notification

## Plugin Platform

- OCR plugins
- Translation plugins
- Export plugins
- Accessibility plugins
- Processing plugins

---

# Long-Term Vision (3.x)

VideoText becomes a complete evidence-preserving accessibility and instructional-content platform supporting:

- OCR
- Human verification
- Translation
- Accessibility remediation
- AI-assisted understanding
- Accessible document generation
- Multimedia transcripts
- Compliance reporting
- Multiple export formats

---

# Design Principles

Every feature should strive to be:

- Deterministic
- Evidence-preserving
- Human-verifiable
- Accessible
- Measurable
- Benchmarkable
- Modular
- Maintainable
- Backward compatible whenever practical

---

# Success Metric

Every proposed feature should answer one question:

> **Does this improve accuracy, accessibility, or human efficiency without reducing trust?**

If the answer is **no**, it does not belong in VideoText.
