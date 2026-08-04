# RapidOCR Feasibility Study

## Scope and Result

RapidOCR is a feasible second-engine candidate for controlled Version 1.5
evaluation, with limitations. An isolated `RapidOCREngine` adapter exists for
contract testing only. It is not registered, is not discoverable, and does not
change PaddleOCR's status as VideoText's only production/default engine.

**Recommendation: Suitable with limitations.**

The documented API supplies text, per-line scores, and four-point line boxes,
which can map deterministically to VideoText's canonical result model. The
remaining decision blockers are empirical accuracy/performance measurements,
Windows PyInstaller validation, and model-license verification for the exact
model bundle selected for evaluation.

## Primary Sources

- [RapidOCR repository and license](https://github.com/RapidAI/RapidOCR)
- [RapidOCR Python package metadata](https://pypi.org/project/rapidocr/)
- [RapidOCR usage and output API](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/)
- [RapidOCR parameters](https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/parameters/)
- [RapidOCR model list](https://rapidai.github.io/RapidOCRDocs/latest/model_list/)

These sources were reviewed on 2026-08-03. Version-specific details must be
rechecked and pinned before any adapter is registered or packaged.

## Licensing

The `rapidocr` PyPI package declares Apache-2.0, and the RapidOCR repository
states its engineering scripts use Apache-2.0. The repository also states that
the OCR-model copyright is held by Baidu. The reviewed RapidOCR sources do not
establish a single redistribution or commercial-use license for every selectable
model. Therefore the exact detector, classifier, and recognizer model licenses
must be reviewed from their primary model sources before distribution.

No commercial-use conclusion should be inferred from the package license alone.
Any notices, attribution, model files, and redistribution obligations must be
recorded with the pinned model configuration.

## Platform, Runtime, and Offline Findings

The current PyPI package advertises Python `>=3.8, <4` and publishes a
platform-independent wheel. The upstream project describes multi-platform and
offline deployment, while its documented default configuration uses ONNX
Runtime. It also documents multiple optional inference backends, including GPU
capable options; actual CPU/GPU availability depends on the selected backend and
its separately installed native runtime.

Installation shown by the upstream project is:

```text
pip install rapidocr onnxruntime
```

The current PyPI `rapidocr` wheel is 27.3 MB, but that is not the total runtime
footprint: ONNX Runtime, selected models, and any optional backend add to the
installed and packaged size. The official documentation indicates default models
are bundled with the wheel for recent releases, and also provides
`rapidocr download_models` for explicit pre-download. Model configuration can
set `model_root_dir`; otherwise models are stored in RapidOCR's installed
package `models` directory according to the documented parameter reference.

This supports offline use after the selected models are present, but requires
Version 1.5 validation for a frozen Windows application: the installed-package
default location may be unsuitable for writable runtime downloads, and the
selected models plus ONNX Runtime must be explicitly collected by PyInstaller.
Startup time, memory, package size, model size, and CPU performance are not
claimed here; they require the planned benchmark.

## Canonical Contract Mapping

Documented `RapidOCROutput` fields are:

| RapidOCR field | Canonical mapping | Treatment |
| --- | --- | --- |
| `txts` | `OCRResult.text` | Preserved in returned order |
| `scores` | `OCRResult.confidence` | Converted to `float` without scaling or calibration |
| `boxes` (`N x 4 x 2`) | `OCRResult.bounding_box` | Deterministic enclosing `[left, top, right, bottom]` rectangle |

VideoText's established geometry model accepts axis-aligned four-value boxes,
whereas RapidOCR documents four corner points. The adapter converts each
quadrilateral to its axis-aligned enclosing extent using minimum/maximum x/y.
This does not invent text, confidence, or a region; it does discard rotation
detail because the existing canonical model has no quadrilateral field. It is
appropriate for the presentation-slide evaluation corpus, but rotated-text
behavior must be measured separately.

The adapter rejects inconsistent box/text/score lengths rather than silently
dropping evidence, and rejects non-quadrilateral boxes rather than guessing a
geometry format. It does not sort results or add preprocessing.

## Adapter Design

`src/rapidocr_engine.py` contains an unregistered `RapidOCREngine` with the
same narrow `recognize(image) -> list[OCRResult]` surface used by production
engines. It owns:

- lazy RapidOCR import and initialization;
- one engine instance per adapter;
- invocation;
- RapidOCR output parsing; and
- canonical result creation.

It is deliberately absent from `discover_ocr_engines()`, the registry, GUI,
processing service, checkpoints, exports, and packaging configuration. A future
task must pin a RapidOCR version and model configuration before considering
registration.

## Adapter Certification Result

**Adapter contract certified; production suitability pending licensing,
dependency, packaging, performance, and accuracy evaluation.**

Mocked-backend certification verifies canonical result-list output, reported
order and exact text preservation, raw finite confidence conversion, canonical
geometry, empty output, malformed collection and shape rejection, independent
repeated result lists, input-image preservation, lazy initialization, and reuse
of one RapidOCR backend instance. Certification does not install RapidOCR or
demonstrate real-model accuracy, model download behavior, offline operation, or
PyInstaller compatibility.

RapidOCR scores are documented as confidence values. The adapter converts each
score only with `float()` and rejects `NaN` or infinity rather than fabricating
a usable confidence. Its envelope transformation preserves each quadrilateral's
full spatial extent while intentionally omitting rotation detail from the
existing axis-aligned canonical model.

## Integration Assessment

| Area | Current assessment | Required Version 1.5 evidence |
| --- | --- | --- |
| Windows/Python | Plausible; package advertises Python 3.8+ | Install and smoke test on supported VideoText Windows/Python versions |
| CPU | Plausible via ONNX Runtime | Cold/warm throughput and memory benchmark |
| GPU | Backend-dependent | Pin runtime/backend and measure separately |
| Offline | Plausible after models are present | Fresh-cache and packaged offline tests |
| Confidence/boxes | Documented fields available | Adapter validation and corpus results |
| Ordering | Adapter preserves reported order | Compare raw and downstream behavior on corpus |
| Packaging | Unproven | PyInstaller data/native-runtime validation |
| Licensing | Incomplete for models | Primary-source model license and redistribution review |
| Maintenance | Active releases exist | Pin version and review release/update stability |

## Next Step

Task 37C certified the isolated adapter contract. Task 37D then validated the
pinned development runtime on two smoke frames; see
[RapidOCR Controlled Runtime Validation](rapidocr-runtime-validation.md).
RapidOCR remains unregistered and must not change the production default.

The resulting accuracy, performance, memory, size, offline-equivalent, and
licensing findings are consolidated in the authoritative
[OCR Engine Evaluation Report v1](ocr-engine-evaluation-report-v1.md).
