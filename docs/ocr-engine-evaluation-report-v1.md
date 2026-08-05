# OCR Engine Evaluation Report v1

## Executive summary

PaddleOCR remains VideoText's production default. RapidOCR is the leading
lightweight alternative: it was materially faster and used less process memory
in the initial evaluation, but its broader accuracy, model redistribution
terms, Windows PyInstaller behavior, and physical offline behavior are not yet
proven. RapidOCR is suitable for broader controlled benchmarking only. It must
not be bundled, registered, or exposed to normal users yet.

Normal processing must run one selected engine. Multi-engine execution belongs
only in explicit Evaluation Mode.

## Evaluation methodology

Both engines received the same four checked-in PNG frames from
`benchmarks/ocr_engine_v1/`, unchanged BGR image input, adapter settings,
ground truth, and Unicode-NFC scoring policy. Whitespace and line endings were
collapsed to one space; case, punctuation, and bullet markers remained
significant. Raw engine text and geometry-reconstructed text were scored
separately.

Performance used five sequential repetitions per engine. Each measurement used
a fresh child process with models left installed/cached but no initialized
adapter. Initialization, first-frame, and warm-frame inference used
`perf_counter()`. Child RSS was sampled every 10 ms and is an operating-system
process measurement, not exact model allocation.

## Hardware and software profile

- Windows 11 10.0.26220; Python 3.12.10
- Intel CPU: 4 physical / 8 logical cores; 16,111 MB RAM
- Quadro P1000, 4,096 MB detected; both engines measured in CPU mode
- `OMP_NUM_THREADS=1`; normal Windows process priority
- PaddleOCR 3.3.3 / PaddlePaddle; RapidOCR 3.9.1 / ONNX Runtime

## Benchmark corpus

The initial human-verified corpus contains four smoke-video frames: title,
numbered/body content, multi-line progressive paragraph, and compact labels.
It is a reproducibility baseline, not a production-selection corpus. Low
contrast, tables, charts, diagram labels, text over graphics, and compression
artifacts are not represented yet.

## Accuracy results

| Engine | CER | WER | Exact frames |
| --- | ---: | ---: | ---: |
| PaddleOCR | 0.00% | 0.00% | 4/4 |
| RapidOCR | 0.87% | 10.53% | 2/4 |

Raw and reconstructed scores were identical on this corpus. RapidOCR's two
observed differences were spacing-only title results such as `Slide1` instead
of `Slide 1`. The WER difference should not be overinterpreted: the corpus is
small and one missing space changes a short title's word alignment.

## Performance results

Median values from five isolated runs:

| Engine | Initialize | First frame | Warm frame | OCR total | Benchmark total |
| --- | ---: | ---: | ---: | ---: | ---: |
| PaddleOCR | 13.507s | 5.007s | 4.383s | 18.157s | 31.550s |
| RapidOCR | 1.064s | 0.763s | 0.635s | 2.667s | 3.738s |

On this machine and corpus, RapidOCR initialization was about 92% shorter,
warm-frame latency about 86% shorter, OCR time about 85% shorter, and child
benchmark time about 88% shorter. These measurements are not a general
performance guarantee.

## Memory results

| Engine | Post-init RSS | Init increase | Peak RSS |
| --- | ---: | ---: | ---: |
| PaddleOCR | 458.625 MB | 404.473 MB | 1,255.699 MB |
| RapidOCR | 144.328 MB | 90.250 MB | 362.113 MB |

RapidOCR's median peak RSS was about 71% lower here. RSS includes runtime and
process memory; it does not precisely identify model allocation.

## Installed, model, and cache size

- Paddle package/runtime: 383.667 MB
- Paddle selected models: 135.763 MB
- PaddleX cache: 268.480 MB
- RapidOCR package/runtime: 42.809 MB
- RapidOCR bundled models: 30.279 MB

RapidOCR bundled models are separate from the reported package/runtime total,
so they are not double-counted. Paddle's selected models are inside the broader
PaddleX cache and must likewise not be added to that cache total.

## Offline suitability

Task 37D's local-model, offline-equivalent test succeeded with network helper
calls patched to fail and `DISABLE_MODEL_SOURCE_CHECK=True`. The selected
RapidOCR models were already present in its installed package. This is not a
physical offline or clean-machine test. PaddleOCR's cached-model workflow
remains the production baseline.

## Licensing and redistribution

RapidOCR software is Apache-2.0 and ONNX Runtime is MIT. Exact redistribution
and commercial-use terms for the selected RapidOCR model bundle remain
unresolved. Package licensing must not be used to infer model licensing.
Production bundling is blocked until primary-source model terms, notices,
attribution, and redistribution obligations are verified.

## Packaging implications

RapidOCR is absent from the VideoText PyInstaller specification. An isolated
PyInstaller proof must collect ONNX Runtime native libraries and pinned models,
verify hidden imports and first-run behavior, and validate packaged offline
operation. Current evidence does not prove packaging readiness.

## Architectural compatibility

Both adapters satisfy `OCREngine.recognize(image)` and return canonical
`OCRResult` evidence. Paddle preserves rectangles. RapidOCR preserves returned
text/order/confidence and envelopes four-point boxes into the existing
axis-aligned geometry. RapidOCR remains outside discovery, the registry, GUI,
normal processing, checkpoints, exports, production requirements, and package.

## User-experience implications

RapidOCR could reduce wait time and resource pressure if it clears the
production gates. That benefit does not justify user exposure before behavior,
packaging, offline support, and licensing are reliable. Version 1.5 evaluation
work adds no engine selector.

## Decision matrix and recommendation

| Area | PaddleOCR | RapidOCR |
| --- | --- | --- |
| Initial accuracy | Strong | Limited evidence |
| Speed | Limited evidence | Strong |
| Memory | Limited evidence | Promising |
| Package size | Limited evidence | Promising |
| Offline operation | Ready for existing workflow | Limited evidence |
| Licensing certainty | Ready for existing workflow | Blocked |
| Packaging readiness | Ready for existing workflow | Blocked |
| Production readiness | Ready | Blocked |

**Recommendation:** retain PaddleOCR as the production default. RapidOCR is
the leading lightweight alternative and is suitable for broader controlled
benchmarking, but not for bundling or normal-user exposure yet.

## Limitations

- The authoritative v2 corpus contains nine representative frames; it is still not representative of all course videos.
- Measurements use one Windows CPU configuration with cached models; background activity can add noise.
- GPU behavior was not evaluated.
- No physical offline, clean-cache, or PyInstaller RapidOCR test was performed.
- Model-license evidence for the selected RapidOCR bundle is incomplete.

## Next steps

1. **37H — Broaden benchmark corpus** with reviewed lecture frames and difficult layouts.
2. **37I — Isolated RapidOCR packaging proof** for resource collection, physical offline behavior, and Windows launch.
3. **37J — Optional normal-mode engine selector** only if RapidOCR clears all production gates.
4. **37K — Release readiness** for final evidence, packaging, and licensing review.

## Evidence

- `docs/rapidocr-feasibility.md`
- `docs/rapidocr-runtime-validation.md`
- `output/task37e_ocr_engine_benchmark/ocr_engine_benchmark.json`
- `output/task37f_performance/ocr_engine_performance.json`

## Authoritative v2 update

The verified nine-frame v2 corpus supersedes the earlier four-frame exploratory
accuracy result. Its authoritative reconstructed metrics are PaddleOCR CER
0.67% / WER 3.92% / 44.4% exact frames and RapidOCR CER 5.74% / WER 10.39% /
33.3% exact frames. Paddle therefore remains the default. RapidOCR remains
evaluation-only because its accuracy was lower on dense, small, structured, and
punctuation-heavy content, and its licensing, physical-offline, and packaging
gates remain unresolved. See
`output/task37k_authoritative_benchmark/authoritative_benchmark.md`.

## Authoritative v2 confidence analysis

The authoritative output records native confidence evidence separately for each
engine; these values are not calibrated across engines. PaddleOCR reported 144
regions with mean/median confidence 98.14%/99.60%, one region below 60%, and a
frame-level mean-confidence versus reconstructed-CER correlation of -0.388.
RapidOCR reported 73 regions with mean/median confidence 97.39%/99.20%, no
regions below 60%, and a corresponding correlation of -0.640. These negative
correlations are descriptive only: the nine-frame corpus is small and higher
engine-native confidence does not itself establish higher accuracy.

The authoritative JSON, CSV, and Markdown outputs now carry the same accuracy,
performance, confidence-distribution, recommendation, and limitation sections.
