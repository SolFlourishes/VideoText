# RapidOCR Controlled Runtime Validation

## Scope

This development-only validation ran the unregistered `RapidOCREngine` against
two existing `packaged_ocr_smoke` candidate frames on 2026-08-04. It does not
register RapidOCR, change PaddleOCR's default status, modify production
requirements, or validate the main PyInstaller package.

## Pinned Evaluation Dependencies

`requirements-evaluation.txt` records the isolated CPU evaluation pins:

```text
rapidocr==3.9.1
onnxruntime==1.27.0
```

The installation also resolved `omegaconf==2.3.1`,
`flatbuffers==25.12.19`, and `antlr4-python3-runtime==4.9.3`. `pip check`
reported no broken requirements. These dependencies remain absent from the
production and packaging requirement files.

## Licensing Status

RapidOCR declares Apache-2.0, and ONNX Runtime declares MIT. RapidOCR's
repository attributes OCR-model copyright to Baidu, but the exact PP-OCRv6
detector/recognizer and classifier redistribution, commercial-use, attribution,
and bundling terms were not confirmed from primary model-license sources.

**Redistribution of the selected model bundle is blocked pending that review.**
The runtime test is only a local development evaluation and does not distribute
the models.

Primary sources:

- [RapidOCR project license statement](https://github.com/RapidAI/RapidOCR)
- [RapidOCR package metadata](https://pypi.org/project/rapidocr/)
- [ONNX Runtime license](https://github.com/microsoft/onnxruntime)
- [RapidOCR model list](https://rapidai.github.io/RapidOCRDocs/latest/model_list/)

## Installation and Model Behavior

RapidOCR and ONNX Runtime were installed in the project virtual environment:

```text
.venv/Lib/site-packages/rapidocr
.venv/Lib/site-packages/onnxruntime
```

RapidOCR used its installed-package model directory rather than a user cache:

```text
.venv/Lib/site-packages/rapidocr/models
```

The tested model bundle was already included locally after installation; no
model download occurred at first inference. Its files and sizes were:

| Model | Size |
| --- | ---: |
| `PP-OCRv6_det_small.onnx` | 9,929,594 bytes |
| `ch_ppocr_mobile_v2.0_cls_mobile.onnx` | 585,532 bytes |
| `PP-OCRv6_rec_small.onnx` | 21,234,383 bytes |
| **Total models** | **31,749,509 bytes** |

Measured installed directories were 33,068,637 bytes for `rapidocr` and
43,569,448 bytes for `onnxruntime`. These measurements are development-machine
values, not a packaged-size estimate.

## Real Adapter Result

The adapter processed smoke frames `frame_000000_0.00s.png` and
`frame_000025_5.00s.png`. It returned canonical `OCRResult` lists with finite
confidence values and axis-aligned envelopes. Repeated identical input produced
equivalent canonical results, the input images were unchanged, and one adapter
instance reused one RapidOCR backend.

| Frame | RapidOCR regions | Observed text |
| --- | ---: | --- |
| 0 | 2 | `Slide1`; `VideoText Packaged OCR Smoke Test` |
| 25 | 3 | `Slide 2`; `1. Review the selected video`; `Use stable frames for OCR` |

RapidOCR's reported region order was preserved. No RapidOCR output object
entered the canonical results; only text, float confidence, and transformed
axis-aligned boxes were returned.

## Small Exploratory Paddle Comparison

The same two frames were run once through fresh RapidOCR and PaddleOCR adapters
in one development process. This is not a benchmark and does not select a
winner.

| Measurement | RapidOCR | PaddleOCR |
| --- | ---: | ---: |
| First-frame time including initialization | 7.140 s | 58.141 s |
| Second-frame warm time | 0.766 s | 4.734 s |
| Frame 0 region count | 2 | 2 |
| Frame 25 region count | 3 | 3 |

The first frame differed visibly only in the title spacing: RapidOCR returned
`Slide1`; PaddleOCR returned `Slide 1`. Frame 25 text matched in this small
sample. RapidOCR supplied finite confidences on all returned regions.

Resident-memory samples were approximately 45 MB before RapidOCR, 187 MB after
the RapidOCR run, and 777 MB after the subsequent PaddleOCR run. They are not
isolated peak-memory measurements because both engines ran in the same process.

## Offline-Equivalent Validation

With `DISABLE_MODEL_SOURCE_CHECK=True`, the tested RapidOCR process was run
after model availability while `requests` session calls and `urllib` URL opens
were patched to fail if invoked. Inference succeeded and returned the expected
two regions for frame 0. This shows the tested local-model path required no
Python-level network request.

This is an **offline-equivalent process test**, not a physical network
disconnection test. A later evaluation task must repeat the test with the
machine genuinely disconnected and a clean, pre-populated model location.

## Packaging Feasibility

RapidOCR is not in the VideoText PyInstaller specification. A future isolated
freeze must collect the CPU ONNX Runtime native libraries and the selected
RapidOCR model files, account for Windows architecture-specific binaries, and
set an explicit read-only model location. It must also validate any hidden
imports, model-source checks, package-size impact, and first-run behavior.

## Decision

**Ready with limitations for formal benchmarking.**

Technical adapter/runtime evidence is sufficient to begin controlled accuracy
and performance benchmarking with pinned dependencies. Production suitability
and redistribution remain blocked pending exact model-license verification,
real Windows packaging validation, physical offline validation, and a formal
benchmark corpus.
