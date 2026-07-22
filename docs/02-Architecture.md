Excellent. Let's do this like a real software project.

One thing I want to change from our previous approach: **this architecture document should describe *what* the system does, not *how* the current code works.** The code should evolve to match the architecture—not the other way around.

---

# VideoText 1.0 Architecture

**Version:** Draft 0.1

**Status:** Design

---

# 1. Vision

## Purpose

VideoText converts lecture videos into structured, editable documents that closely reconstruct the original presentation while preserving the logical organization of the content.

The system is intended for:

* Translation workflows
* Accessibility
* Content reuse
* Search and indexing
* Archival
* Document reconstruction

The output should be independent of any specific export format.

---

## Core Philosophy

VideoText is **not** an OCR program.

It is a **document reconstruction engine**.

OCR is simply one source of evidence.

Every stage of the pipeline should improve the system's understanding of the original document.

---

## Success Criteria

Given a lecture video, VideoText should:

* Identify each logical slide exactly once.
* Ignore transition frames.
* Preserve reading order.
* Preserve paragraph structure.
* Minimize OCR errors through consensus across multiple observations.
* Produce a clean internal document model.
* Export the document to multiple formats without additional reconstruction.

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
           Text Lines
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
         Document Model
        ┌─────┼─────┬─────┐
        ▼     ▼     ▼     ▼
    Markdown DOCX PPTX Excel JSON
```

---

# 3. Architectural Principles

### Principle 1

Each stage has **one responsibility**.

---

### Principle 2

Each stage consumes one data model and produces another.

Stages never modify earlier stages.

---

### Principle 3

Algorithms are replaceable.

For example, OCR may later change from PaddleOCR to another engine without affecting the rest of the pipeline.

---

### Principle 4

The internal document model is the source of truth.

Exporters never perform reconstruction.

---

### Principle 5

Evidence is preserved until a decision is required.

This is particularly important during slide consolidation.

---

# 4. Pipeline Stages

## Stage 1 — Frame Selection

### Input

Video

### Output

CandidateFrame[]

### Responsibility

Identify stable visual states while ignoring animations and transitions.

### Future Improvements

* SSIM
* Scene detection
* ML-based slide detection

---

## Stage 2 — OCR

### Input

CandidateFrame[]

### Output

CandidateFrame + OCR results

### Responsibility

Extract all visible text and positional information.

OCR should never attempt to interpret document structure.

---

## Stage 3 — Reading Order

### Input

OCR text lines

### Output

Ordered text lines

### Responsibility

Determine the natural reading sequence of text.

No merging occurs.

---

## Stage 4 — Paragraph Reconstruction

### Input

Ordered text lines

### Output

TextParagraph[]

### Responsibility

Group related lines into semantic paragraphs.

No cross-frame comparison occurs.

---

## Stage 5 — Slide Consolidation

### Input

SlideBuild[]

### Output

Canonical Slide

### Responsibility

Combine multiple observations of the same slide into a single reconstructed slide.

This stage is responsible for:

* Identifying repeated paragraphs
* Resolving OCR inconsistencies
* Removing duplicate observations
* Producing one canonical version of each paragraph

This is the only stage that reasons across multiple frames.

---

## Stage 6 — Document Model

### Input

Slides

### Output

Document

The document model should be completely independent of export format.

---

## Stage 7 — Export

Each exporter converts the document model into a target format.

Exporters should never:

* merge paragraphs
* correct OCR
* reorder text
* infer document structure

Their responsibility is formatting only.

---

# 5. Data Flow

The data becomes progressively richer.

```text
Video

↓

CandidateFrame

↓

OCR TextLines

↓

Ordered TextLines

↓

Paragraphs

↓

Slide Builds

↓

Canonical Slides

↓

Document

↓

Export
```

Notice that **information is added**, not replaced.

---

# 6. Quality Metrics

Each stage should have measurable outputs.

| Stage                    | Metric                                              |
| ------------------------ | --------------------------------------------------- |
| Frame Selection          | Stable frames selected / transition frames rejected |
| OCR                      | Character accuracy                                  |
| Reading Order            | Line ordering accuracy                              |
| Paragraph Reconstruction | Paragraph accuracy                                  |
| Slide Consolidation      | Duplicate rate / canonical accuracy                 |
| Export                   | Fidelity to document model                          |

This allows us to benchmark changes objectively instead of relying on visual inspection.

---

# 7. Open Design Question: Slide Consolidation

This is the one area we should not finalize yet.

Instead, I propose we document its required behavior without committing to a specific implementation.

The architecture should require that the consolidator:

* Collect evidence from multiple slide builds.
* Group observations that represent the same logical paragraph.
* Produce one canonical paragraph for each group.
* Preserve enough information that future consensus algorithms (OCR confidence, voting, spell-checking, AI-assisted reconstruction) can be added without changing the rest of the pipeline.

Whether that is implemented with clusters, tracks, graphs, or another approach is an implementation detail. The architecture should remain agnostic.

---

## Next Milestone

