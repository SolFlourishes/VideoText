VideoText Roadmap

Project: VideoText

Purpose: Transform video-based instructional content into accurate, accessible, and human-verifiable documents.

Vision

VideoText began as a tool for extracting text from presentation videos. It has evolved into a platform for converting visual instructional content into structured, reusable, and accessible documents.

The long-term goal is to enable organizations to preserve, translate, and remediate instructional content while keeping humans in control of the final output.

VideoText is built as a modular processing pipeline. Each stage produces deterministic evidence that becomes the input to the next stage. Downstream stages enrich prior results without modifying preserved source evidence.

VideoText is guided by four principles:

Accuracy over automation
Never invent or rewrite content.
Preserve the original meaning.
Human-in-the-loop
AI assists.
Humans approve.
Accessibility by design
Outputs should support accessibility rather than simply reproducing appearance.
Deterministic processing
Improvements should be measurable and benchmarked.
Avoid generative "magic fixes."
Current Release
Version 1.3.0

Status: Current Release

Completed
OCR Quality Intelligence
Preserve raw OCR evidence
OCR confidence preservation
Frame-level confidence statistics
Document-level confidence statistics
OCR Quality summary dialog
Confidence-aware CSV export
Backward-compatible replay support
OCR Processing
Geometry-based reading order
Paragraph reconstruction
Duplicate suppression
Boundary stitching
Improved sentence reconstruction
Export
CSV
Markdown
Excel
Confidence-aware CSV fields
Translation Workflow

Five-column protected workbook:

Slide
Original Text
Initial AI Translation (placeholder)
Modified Translation
Verified

Features:

Locked source columns
Editable translation columns
Worksheet protection
Translation guidance
Human verification workflow
Diagnostics
OCR benchmarking framework
CER/WER evaluation
OCR diagnostics
OCR confidence statistics
Version 1.4
Theme

OCR Engine Framework

Release Goal

Decouple OCR from the VideoText processing pipeline so any compliant OCR engine can be substituted without changing downstream processing.

Planned Features
OCR engine interface
OCR abstraction layer
PaddleOCR adapter (default implementation)
Plug-in architecture
Engine registration and discovery
Shared OCR result contract
Preserve replay compatibility
Preserve OCR confidence support
Out of Scope
Additional OCR engines
GUI engine selection
OCR engine comparison
CER/WER benchmarking
Evaluation reports
OCR quality improvements
Version 1.5
Theme

OCR Engine Evaluation

Release Goal

Evaluate and compare OCR engines using the common framework established in Version 1.4.

Planned Features
Additional OCR engine adapters
Side-by-side engine comparison
CER benchmarking
WER benchmarking
Benchmark datasets
Engine evaluation reports
Performance comparisons
Accuracy summaries
Out of Scope
New OCR reconstruction algorithms
AI-assisted OCR correction
Automatic engine selection
Cloud OCR services
Version 1.6
Theme

Translation Foundation

Release Goal

Add translation as a downstream transformation while preserving original OCR evidence.

Planned Features
Translation service interface
Source and target language selection
Preserve original extracted text
Store translated text separately
Deterministic translation pipeline
Clear provenance between OCR and translation
No automatic replacement of OCR output
Initial provider or local model integration
Translation in CSV, Excel, and Markdown
Basic GUI controls
Out of Scope
Translation quality scoring
Multiple providers
Translation memory
Glossaries
Automatic translation approval
Version 1.7
Theme

Translation Quality and Workflow

Release Goal

Expand translation into a complete human-review workflow.

Planned Features
Multiple translation providers
Side-by-side original and translated text
Batch translation
Glossaries
Preferred terminology
Re-translation
Translation quality notes
Cost controls for cloud providers
Milestone
Portable Deployment Experience
Goal

Deliver a polished, portable Windows application requiring no administrator privileges, no installation, and a guided first-run experience.

Planned Features
Portable ZIP distribution
No administrator rights required
No registry modifications
User-writable configuration
User-writable output folders
First-run setup wizard
Verify OCR models
Verify write permissions
Create output folders
Offer to open the User Guide
Optional environment diagnostics
Future update check
Out of Scope
MSI installer
Inno Setup installer
Program Files installation
Registry integration
Administrator privileges
Version 2.0
Theme

Accessibility Edition

Release Goal

Transform verified instructional content into accessible documents.

Planned Features
Accessible Word Export
Heading styles
Paragraph styles
Accessible tables
Real lists
Logical reading order
Slide numbers
Timestamps
Source metadata
Optional Table of Contents
Screen-reader-friendly structure

Suitable for:

WCAG
Section 508
ADA
DOJ Title II
Version 2.1
Theme

Accessible Multimedia Transcript

Release Goal

Combine visual and spoken instructional content into a single accessible transcript.

Planned Features
Verified OCR
Speech-to-text
Slide timing
Speaker identification
Visual notes
Accessible transcript format
Version 2.2
Theme

Accessibility Review Workflow

Planned Features
Accessibility review status
Reviewer notes
Missing caption detection
Reading-order validation
Low-confidence highlighting
Version tracking
Accessibility reports
Version 3.x
Theme

Video Accessibility Platform

Planned Outputs
Excel Translation Workbook
Markdown
CSV
Accessible Word (.docx)
Accessible PDF
HTML
EPUB
Plain Text
Caption files (SRT/VTT)
Translation memory formats
Accessibility compliance reports
Future Milestone
Developer Platform
Goal

Enable third parties to extend VideoText without modifying the core application.

Planned Extension Points
OCR engines
Translation providers
Export formats
Accessibility analyzers
Custom processing workflows
Guiding Philosophy

VideoText is not intended to replace translators, instructional designers, or accessibility specialists.

Instead, it prepares high-quality, structured content so that human experts can work more efficiently and with greater confidence.

Every major feature should answer one question:

Does this improve accuracy, accessibility, or human efficiency without reducing trust?

If the answer is no, the feature does not belong in VideoText.

Design Principles

Every new feature should strive to be:

Deterministic
Measurable
Benchmarkable
Human-verifiable
Accessible
Maintainable
Modular
Backward compatible whenever practical
Success Metrics

Future improvements should be evaluated using objective measures whenever possible.

Examples include:

Character Error Rate (CER)
Word Error Rate (WER)
OCR confidence
Processing time
Memory usage
Translation efficiency
Accessibility readiness
Reviewer effort
Reduction in manual editing
Long-Term Mission

VideoText transforms visual instructional content into accurate, accessible, and human-verifiable documents that support translation, accessibility, preservation, and reuse while preserving the integrity of the original content.