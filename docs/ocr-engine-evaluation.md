# OCR Engine Evaluation Methodology

## Purpose

Version 1.5 will evaluate OCR engines using the engine-neutral contract added
in Version 1.4. The objective is to identify the best practical balance of
accuracy, speed, resource use, offline operation, licensing, and Windows
packaging compatibility for instructional presentation video content.

PaddleOCR is the current baseline and default. This document defines how any
candidate is evaluated before it can affect that default. It does not authorize
an engine change, a user-facing engine selector, or production behavior change.

## Evaluation Rules

1. Only the OCR engine changes during a comparison.
2. Every engine receives the same extracted candidate frames.
3. Every engine receives the same preprocessing unless it technically cannot
   accept the shared input format.
4. Any engine-specific preprocessing must be disclosed, timed, and reported as
   a separate condition.
5. Each adapter returns canonical `OCRResult` objects in its engine response
   order, with its original bounding boxes and confidence values when supplied.
6. Reading order, paragraph reconstruction, slide consolidation, confidence
   statistics, exports, and scoring remain shared.
7. Raw OCR evidence is preserved before confidence filtering or interpretation.
8. No recognized text may be manually corrected before scoring.
9. Runs must be reproducible from recorded inputs and configuration.
10. Record engine versions, settings, hardware, device mode, and dataset
    version for every result.

The evaluation runner must use the same `OCREngine.recognize(image)` boundary
as normal processing. It must not parse engine-specific response dictionaries
outside the relevant adapter.

## Adapter Certification

Before an adapter may be evaluated against the corpus, it must pass the shared
adapter certification tests. Certification verifies that the adapter returns
independent `list[OCRResult]` values, preserves reported order, text, and raw
finite confidence values, emits valid canonical `[left, top, right, bottom]`
geometry, handles empty output deterministically, and does not mutate its input
image. It also verifies lazy initialization, one retained backend instance per
adapter, deterministic repeated mocked responses, and clear rejection of
malformed or inconsistent backend output.

Canonical geometry must satisfy `left <= right` and `top <= bottom`. Paddle
retains its documented rectangular coordinates unchanged. RapidOCR converts its
documented quadrilaterals to deterministic axis-aligned envelopes and rejects
other shapes. Non-finite confidence values are rejected explicitly; neither
adapter scales, clamps, rounds, or fabricates confidence.

Certification is not production approval. In particular, it does not register
an engine, change the default, approve licensing, or prove packaging,
performance, accuracy, or offline suitability.

### Current certification results

- **PaddleOCREngine:** adapter contract certified. It remains the registered,
  process-lifetime production default; its normal initialization, parsing,
  replay, and raw/working evidence behavior are regression-tested.
- **RapidOCREngine:** adapter contract certified; production suitability is
  pending licensing, dependency, packaging, performance, and accuracy
  evaluation. It remains unregistered and unavailable to normal users.

## First formal comparison

The initial RapidOCR/PaddleOCR comparison is recorded in the authoritative
[OCR Engine Evaluation Report v1](ocr-engine-evaluation-report-v1.md). It uses
four human-verified saved frames and five isolated performance repetitions per
engine. Paddle remains the production default; RapidOCR remains evaluation-only
pending broader accuracy, model-license, offline, and packaging evidence.

## Candidate Scope

### Primary candidates

| Candidate | Evaluation role | Evidence required before adoption |
| --- | --- | --- |
| PaddleOCR | Current baseline | Baseline accuracy, performance, packaging, and offline measurements |
| Tesseract OCR | Conventional local OCR candidate | Canonical-region adapter feasibility and Windows/offline measurements |
| EasyOCR | Python OCR candidate | Adapter feasibility, model behavior, and packaging measurements |
| Surya OCR | Document OCR candidate | Slide-content accuracy, resource, and licensing review |
| RapidOCR | Lightweight OCR candidate | Adapter behavior, backend dependency, and packaging review |
| docTR | Deep-learning OCR candidate | Detection/recognition output compatibility and Windows review |

These are candidates, not approved dependencies. Version 1.5 must verify their
current license, model license, maintenance status, supported Python and
Windows versions, device support, model download requirements, and commercial
use terms from primary sources before implementation.

### Research-only candidates

Microsoft TrOCR, other transformer OCR models, and local vision-language models
may be researched separately. They are not initial production candidates until
they can meet the canonical evidence, reproducibility, offline, and packaging
requirements.

### AI Vision

AI Vision is not a standard OCR engine by default. It may help with structured
slide understanding, diagrams, charts, or layout interpretation, but it may
incur API or hardware cost, produce nondeterministic output, and conflict with
VideoText's offline-first design. If explored later, it should be an optional
parallel mode rather than a replacement for conventional OCR. Preserved OCR
evidence remains authoritative. Version 1.5 must not implement AI Vision.

## Initial Benchmark Corpus

Start with a small, curated, versioned corpus of manually verified frames and
slides. Each item must have a stable identifier, source provenance permitted
for testing, an image checksum, and a machine-readable reference transcript.

| Category | Failure modes exercised | Ground-truth requirements | Required in initial corpus |
| --- | --- | --- | --- |
| Simple title slides | Large text, centering, sparse regions | Exact title and subtitle text | Yes |
| Standard bullet slides | List markers, indentation, wrapping | Text, markers, and line breaks | Yes |
| Dense lecture slides | Region ordering and small spacing | Complete text and paragraph boundaries | Yes |
| Small text | Missed or merged characters | Character-exact transcription | Yes |
| Low contrast | Low confidence and omissions | Exact visible text | Yes |
| Mixed fonts | Font-dependent substitutions | Exact text and style-independent reading order | Yes |
| Bold and italic text | Stroke and punctuation errors | Exact text | Yes |
| Tables | Cell order and repeated labels | Table reading-order policy and text | Yes |
| Equations | Symbol recognition | Defined Unicode/LaTex-like transcription policy | Pilot |
| Charts with labels | Small labels and axes | All intended text labels | Yes |
| Diagrams with embedded text | Spatially distributed text | Text and expected reading order | Pilot |
| Text over images | Background interference | Exact visible text | Yes |
| Animated transitions | Progressive text states | Stable final state and frame identifiers | Yes |
| Duplicate frames | Repeated evidence | Same reference and duplicate identity | Yes |
| Compression artifacts | Blurring and blocking | Exact intended text | Yes |
| Unusual aspect ratios | Scaling and layout behavior | Exact text and layout policy | Pilot |
| Multilingual samples | Script and language support | Language-specific verified reference | Future |

The first corpus should prioritize instructional slides represented by existing
diagnostics and deterministic smoke inputs. It should be expanded only after
the initial engines have comparable, repeatable results.

## Ground Truth Policy

Ground truth is human-verified transcription, never an OCR engine output.
Reference files should be versioned JSON or JSON Lines records containing at
least dataset version, frame identifier, source checksum, visible text,
expected line order, and review metadata.

Use consistent Unicode normalization (NFC) before scoring. Preserve the
reference's intended characters, punctuation, bullets, line breaks, and slide
number separately from any comparison normalization. Define and record the
following policies before a benchmark begins:

- whether case is significant for the metric;
- how whitespace sequences and line breaks are normalized for CER/WER;
- whether list markers and punctuation are scored;
- how empty reference or empty hypothesis values score;
- how equations and non-text visual labels are represented.

At least one transcriber and one independent reviewer should approve each
reference. Corrections create a new dataset version; they do not silently
replace earlier benchmark references.

## Accuracy and Evidence Metrics

Calculate both per-frame/slide values and aggregate corpus values from total
edit counts, not averages of percentages.

```text
CER = (substitutions + deletions + insertions) / reference characters
WER = (substitutions + deletions + insertions) / reference words
```

Report empty-reference and empty-hypothesis cases explicitly rather than
producing `NaN`. Use the documented normalization policy consistently across
all engines. In addition to CER and WER, report where useful:

- exact-match rate;
- raw region count;
- missed-text rate;
- false-positive-text rate;
- line-order correctness;
- text coverage; and
- confidence calibration against actual CER/WER.

Do not reduce these measurements to an unqualified composite score. A metric
may be reported only when its ground truth and calculation policy are recorded.

## Confidence Evaluation

Keep each engine's raw confidence values unchanged in canonical `OCRResult`
objects. Engines without confidence support use unavailable confidence (`None`)
and must not fabricate scores. Different confidence scales must not be treated
as directly comparable without a separately documented calibration analysis.

For engines that provide confidence, report availability, scale/documentation,
distribution, low-confidence rate at the active threshold, and the relationship
between confidence and observed CER/WER. Preserve raw values even if a future
report also provides calibrated analysis.

## Performance Measurement

Measure cold and warm runs separately. Record:

- model initialization time;
- first-frame latency;
- per-frame OCR time;
- total OCR and total benchmark runtime;
- CPU and GPU utilization;
- peak memory use;
- model download, installed-package, packaged-application, and model-cache
  sizes.

Every report must include operating system, CPU, RAM, GPU and GPU memory,
Python version, engine version, device mode, and relevant thread settings.
Measurements should use the same corpus, machine state, frame order, and
repetition policy for all engines.

## Integration Assessment

For each candidate, record factual, source-backed findings for Windows and
Python compatibility; CPU/GPU support; offline operation; package and model
licenses; commercial-use restrictions; model downloads; PyInstaller behavior;
model/package size; update stability; maintenance activity; confidence and
bounding-box output; reading-order compatibility; and multilingual support.

Store links to primary documentation or license sources alongside the finding.
Unknown values remain unknown; they must not be inferred from another engine.

## Evaluation Workflows

### Normal processing

Normal processing runs one selected production engine once. Paddle remains the
default unless evaluation evidence supports a later change. It does not run
multiple engines automatically.

### Evaluation mode

Evaluation mode is a future developer/research workflow that runs identical
inputs through multiple engines and writes comparison data. It is separate from
normal processing, never automatic, and must not change user output or
checkpoints. Task 37A adds no GUI control for either mode.

## Future Report Outputs

Future evaluation runs should write a machine-readable CSV, structured JSON,
and concise Markdown summary. Recommended fields are:

```text
engine_name
engine_version
dataset_version
hardware_profile
device_mode
frame_count
region_count
cer
wer
exact_match_rate
startup_seconds
ocr_seconds
total_seconds
peak_memory_mb
model_size_mb
package_size_mb
confidence_available
mean_confidence
notes
```

## Decision Policy

The default engine decision considers accuracy, speed, memory use, offline
operation, licensing, packaging, stability, confidence support, and
instructional-content performance. Lowest CER alone does not select the
default. A more accurate engine can still be unsuitable if it requires cloud
access, excessive GPU resources, restrictive licensing, a substantially larger
package, unstable Windows support, or impractical distribution.

## Recommended Version 1.5 Sequence

```text
37A — Evaluation framework design
37B — Select and implement second OCR adapter
37C — Validate second adapter against canonical contract
37D — Multi-engine evaluation runner
37E — Accuracy benchmarking
37F — Performance benchmarking
37G — Evaluation reports
37H — Optional normal-mode engine selector
37I — Release readiness
```

An engine selector is considered only after at least two adapters are stable,
tested against the canonical contract, and benchmarked.

## Open Questions Before Implementation

- Which second candidate has the clearest current Windows, offline, license,
  and bounding-box support after primary-source review?
- Which existing diagnostic frames can be redistributed as benchmark fixtures?
- What exact line-order and equation-transcription policies best represent
  instructional content?
- Which resource-monitoring mechanism is sufficiently reliable on supported
  Windows hardware?
- What number of repeated cold and warm runs balances measurement stability
  with practical benchmark duration?
