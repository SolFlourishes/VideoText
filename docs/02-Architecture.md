# VideoText Architecture

**Version:** 2.0 Draft
**Status:** Living Design Document

---

# 1. Vision

## Purpose

VideoText transforms video-based instructional content into accurate, structured, accessible, and human-verifiable documents.

The system is designed to support:

- Translation workflows
- Digital accessibility remediation
- Content reuse
- Search and indexing
- Archival and preservation
- Knowledge extraction
- Document reconstruction

All outputs originate from a single canonical document model and may be exported into multiple formats without changing the reconstructed content.

---

## Core Philosophy

VideoText is **not** an OCR application.

It is a **document understanding and transformation engine**.

OCR is simply one source of evidence.

Future versions may also incorporate:

- Speech recognition
- Slide metadata
- Timing information
- User corrections
- AI-assisted translation
- Accessibility annotations

Every stage of the pipeline improves the system's understanding of the original instructional content.

The **canonical document**, not the OCR output, is the source of truth.

---

## Success Criteria

Given a presentation video, VideoText should:

- Identify each logical slide exactly once.
- Ignore transition frames.
- Preserve reading order.
- Preserve paragraph structure.
- Preserve list semantics.
- Minimize OCR errors through consensus across multiple observations.
- Produce a clean canonical document.
- Support human review where uncertainty exists.
- Export the same reconstructed content consistently across all formats.

---

# 2. System Architecture

```text
                    Video
                      │
                      ▼
             Frame Selection
                      │
                      ▼
              Candidate Frames
                      │
                      ▼
                     OCR
                      │
                      ▼
              Reading Order
                      │
                      ▼
         Paragraph Reconstruction
                      │
                      ▼
           Slide Consolidation
                      │
                      ▼
          Canonical Document Model
                      │
      ┌────────┬────────┬────────┬────────┬────────┐
      ▼        ▼        ▼        ▼        ▼
   Markdown  Excel    DOCX     JSON   Future APIs
```

The pipeline reconstructs the instructional document once.

Every exporter consumes the same canonical document.

---

# 3. Architectural Principles

## Principle 1

Each stage has **one responsibility**.

Every processing stage should perform one well-defined task and produce a clearly defined output.

---

## Principle 2

Each stage consumes one data model and produces another.

Stages never modify the outputs of earlier stages.

Earlier stages provide evidence.

Later stages interpret that evidence.

---

## Principle 3

Algorithms are replaceable.

Individual algorithms should be interchangeable without requiring changes elsewhere in the pipeline.

Examples include:

- OCR engines
- Reading-order algorithms
- Paragraph reconstruction
- Slide matching
- Consensus strategies

---

## Principle 4

The canonical document model is the source of truth.

All exports originate from the canonical document.

Exporters must never:

- reconstruct paragraphs
- correct OCR
- reorder content
- infer document structure

Formatting belongs in exporters.

Reconstruction belongs in the pipeline.

---

## Principle 5

Human review is preserved.

VideoText assists human reviewers rather than replacing them.

Where uncertainty exists, the system should expose evidence instead of silently altering content.

---

## Principle 6

Evidence is preserved until a decision is required.

Confidence, repeated observations, and future evidence sources should remain available as long as practical before producing the canonical document.

---

# 4. Pipeline Stages

## Stage 1 — Frame Selection

### Input

Video

### Output

CandidateFrame[]

### Responsibility

Identify stable visual states while ignoring transitions, animations, and duplicate frames.

### Possible Future Improvements

- SSIM
- Scene detection
- ML-based slide detection
- Adaptive frame sampling

---

## Stage 2 — OCR

### Input

CandidateFrame[]

### Output

CandidateFrame + OCR observations

### Responsibility

Extract visible text together with positional information.

OCR identifies text.

It does **not** determine document structure.

Future OCR engines should remain interchangeable.

---

## Stage 3 — Reading Order

### Input

OCR text observations

### Output

Ordered text observations

### Responsibility

Determine the logical reading sequence.

No merging occurs.

No reconstruction occurs.

---

## Stage 4 — Paragraph Reconstruction

### Input

Ordered text observations

### Output

Paragraphs

### Responsibility

Group related lines into semantic paragraphs.

Perform deterministic reconstruction within a single slide observation.

Examples include:

- paragraph grouping
- boundary stitching
- duplicate overlap removal

Cross-frame comparison does not occur here.

---

## Stage 5 — Slide Consolidation

### Input

Slide observations

### Output

Canonical slide

### Responsibility

Combine multiple observations of the same logical slide into one reconstructed slide.

Responsibilities include:

- duplicate paragraph identification
- OCR consensus
- observation comparison
- canonical paragraph selection

This is the only stage that reasons across multiple observations.

---

## Stage 6 — Canonical Document Model

### Input

Canonical slides

### Output

Document

The canonical document represents the reconstructed instructional content independent of any export format.

It should preserve:

- slide hierarchy
- reading order
- paragraphs
- headings
- list semantics
- timestamps (future)
- confidence (future)
- source observations (future)
- translation state (future)
- accessibility metadata (future)

The canonical document is the single source of truth for every exporter.

---

## Stage 7 — Export

Each exporter converts the canonical document into a specific target format.

Current exports include:

- Markdown
- Excel
- CSV

Future exports may include:

- DOCX
- JSON
- HTML
- PDF
- EPUB
- Caption formats
- APIs

Exporters perform formatting only.

They never reconstruct content.

---

# 5. Data Flow

Information becomes progressively richer throughout the pipeline.

```text
Video

↓

Candidate Frames

↓

OCR Observations

↓

Ordered Text

↓

Paragraphs

↓

Slide Observations

↓

Canonical Slides

↓

Canonical Document

↓

Export
```

Information is added—not replaced.

---

# 6. Canonical Document Model

The canonical document is designed to outlive any individual export format.

Every exporter consumes the same document.

Future features should extend the canonical model rather than bypass it.

Possible future document attributes include:

- OCR confidence
- Translation status
- Accessibility metadata
- Speaker information
- Audio transcript
- Source timestamps
- Visual descriptions
- Review history

This architecture allows new outputs without redesigning the reconstruction pipeline.

---

# 7. Quality Metrics

Every stage should have measurable outputs.

| Stage | Example Metrics |
|--------|-----------------|
| Frame Selection | Stable frames selected / transition rejection |
| OCR | Character Error Rate (CER), Word Error Rate (WER) |
| Reading Order | Ordering accuracy |
| Paragraph Reconstruction | Paragraph accuracy |
| Slide Consolidation | Duplicate suppression, canonical accuracy |
| Export | Fidelity to canonical document |
| Performance | Runtime, memory usage |
| Accessibility | Accessibility readiness (future) |

The goal is objective benchmarking rather than subjective visual comparison.

---

# 8. Future Evidence Sources

The architecture intentionally supports additional evidence without redesigning the pipeline.

Potential future evidence includes:

- OCR confidence
- Speech-to-text
- Speaker identification
- Slide timestamps
- User corrections
- AI translation
- Accessibility annotations
- External metadata

Each source contributes evidence while preserving deterministic reconstruction.

---

# 9. Accessibility Architecture

Accessibility is a first-class capability of VideoText.

The objective is not to recreate slide appearance but to communicate the same instructional information in accessible formats.

Future accessibility outputs may include:

- Accessible Word documents
- Accessible PDFs
- Multimedia transcripts
- Caption files
- Accessibility review workbooks

These outputs should preserve:

- logical reading order
- document hierarchy
- semantic headings
- lists
- tables
- timestamps
- equivalent instructional meaning

Accessibility exporters consume the same canonical document as every other exporter.

---

# 10. Open Design Questions

Several architectural areas remain intentionally implementation-independent.

Examples include:

- OCR consensus algorithms
- Confidence weighting
- AI-assisted translation
- Speech integration
- Accessibility annotation
- Slide similarity algorithms

The architecture defines **required behavior**, not specific implementations.

This allows the codebase to evolve while preserving architectural stability.

---

# 11. Next Milestones

## Near-Term

- OCR quality intelligence
- Confidence preservation
- OCR engine abstraction
- Translation workflow enhancements
- Additional benchmarking

## Long-Term

- Accessible Word document generation
- Multimedia transcript generation
- Accessibility review workflow
- Additional export formats
- Plugin architecture
- Public APIs

The architecture should continue evolving toward a modular document transformation platform while preserving the canonical document model as the single source of truth.

---

# 12. Guiding Philosophy

The architecture defines **what the system should do**, not how today's code happens to implement it.

The code should evolve to match the architecture—not the other way around.

When new features are proposed, they should be evaluated against three questions:

1. Does this improve the accuracy of the reconstructed document?
2. Does this improve accessibility or reuse of instructional content?
3. Does this preserve human trust by exposing evidence rather than hiding uncertainty?

If the answer is "no," the feature likely belongs outside the core reconstruction pipeline.

---

# Mission Statement

> **VideoText transforms visual instructional content into accurate, accessible, and human-verifiable documents that support translation, accessibility, preservation, and reuse while preserving the integrity of the original content.**