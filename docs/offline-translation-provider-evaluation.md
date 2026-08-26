# Offline Translation Provider Evaluation — 38D1

## Scope and status

This is a development-only evaluation of possible future providers for the
explicit `local` translation selection. It does not register a provider, alter
the translation pipeline, add a dependency, download a model, or change OCR
evidence. Translation remains a downstream review layer; raw translations from
this evaluation are never canonical evidence.

**Environment inspected:** Windows; VideoText virtual environment uses Python
3.12.10. On 2026-08-06, `argostranslate`, `transformers`, `ctranslate2`,
`torch`, and `sentencepiece` were not installed. No models were downloaded or
tested. Consequently, this report contains architecture and licensing findings,
not measured runtime, memory, or quality claims.

## Fixed evaluation corpus

[`benchmarks/translation_evaluation_v1/corpus.json`](../benchmarks/translation_evaluation_v1/corpus.json)
contains seven exact English source segments and the required `en → es` and
`en → de` pairs. It covers titles, prose, bullets, health-professions language,
punctuation, numerals, proper nouns, OCR-like line breaks, and an intentionally
ambiguous pronoun. Future runs must record raw output unchanged, in corpus order,
with candidate/library/model/language-pair/runtime/failure fields.

## Candidate findings

| Candidate | Integration and language handling | Offline/model management | Packaging and licensing | Current assessment |
| --- | --- | --- | --- | --- |
| Argos Translate | Python API; uses ISO 639 codes; direct installed pairs and optional pivoting. VideoText must map BCP-47 requests explicitly and reject unsupported regional variants rather than silently coerce them. | Separately installable `.argosmodel` pair packages contain CTranslate2 model/tokenizer/SBD data. Installed packages can be listed without translating. | Library is open source; every selected package's model terms still require verification. Optional packages keep the core ZIP small. | Best first runtime spike. |
| NLLB-200 via Transformers | Python API needs Transformers, PyTorch, tokenizer, and NLLB/FLORES language-code mapping. A multilingual model can cover many languages but requires explicit forced target-language handling. | The `facebook/nllb-200-distilled-600M` repository reports 196 languages and a 2.46 GB repository snapshot. Model/cache availability can be inspected without inference after download. | The checked model card reports CC-BY-NC-4.0, which blocks commercial production use without another model/license decision. PyTorch and model packaging add substantial Windows risk. | Evaluation-only; not a first local provider. |
| CTranslate2 plus a compatible model/tokenizer | CTranslate2 is an inference runtime, not a translation model or language catalog. A separately selected converted model, tokenizer, language mapping, and model license are required. | Quantized converted models can improve CPU footprint/speed, but model conversion/versioning/integrity and tokenizer distribution become VideoText responsibilities. | CTranslate2 is MIT; selected model and tokenizer terms govern redistribution. Native wheels/DLLs increase PyInstaller and antivirus validation work. | Promising optimization path after choosing a licensable model. |

LibreTranslate is a possible future self-hosted API provider, not a separate
embedded-engine candidate: its documented local translation stack is based on
Argos Translate.

## Runtime and determinism

No candidate was measured. The 38D2 spike must measure cold start, per-segment
CPU time, peak memory, and repeated-output equality on the fixed corpus.
Providers should load lazily inside their own adapter; no model or optional SDK
may load during core registry import or discovery. CPU must be the safe default;
GPU use, batching, cancellation, progress, and thread safety need explicit
adapter-level measurements before exposure.

Argos documents sentence splitting and a roughly 150-token sequence limit, so
the one-request/one-source-unit contract remains appropriate. Its documented
pivoting must be disabled or made explicit for VideoText: automatic pivots would
violate the requirement to reject unsupported direct language handling clearly.

## Packaging and installation direction

The core VideoText package should remain usable without translation runtimes or
models. A future optional installer/manager should accept a user-selected,
versioned model package into an application-controlled data directory, record
its source, checksum where available, language direction, and license notice,
and permit removal. It must support offline installation from an already
downloaded package. No model belongs in Git or the base executable.

The translation contract accepts BCP-47-style identifiers. 38D2 should define
a finite, versioned map from those identifiers to the selected engine's codes.
It must reject unsupported regional variants unless the model explicitly
distinguishes them; it must not silently reduce `pt-BR` to `pt`.

## Licensing sources

- [Argos Translate repository](https://github.com/argosopentech/argos-translate)
- [Argos package documentation](https://argos-translate.readthedocs.io/en/stable/source/argostranslate.html)
- [NLLB-200 distilled 600M model card](https://huggingface.co/facebook/nllb-200-distilled-600M)
- [CTranslate2 repository and MIT license](https://github.com/OpenNMT/CTranslate2)

The Argos library's open-source status does **not** establish redistribution or
commercial permissions for each language package. The reviewed NLLB-200
distilled 600M model card declares CC-BY-NC-4.0; it is unsuitable for a
commercially distributable default unless a different model and its terms are
separately verified. CTranslate2's MIT runtime license likewise does not grant
rights to a converted model or tokenizer.

## Decision matrix

| Criterion | Argos Translate | NLLB/Transformers | CTranslate2 + model |
| --- | --- | --- | --- |
| Translation quality | Unmeasured | Unmeasured | Unmeasured; model-dependent |
| Language coverage | Pair-package dependent | Broad, 196-language model card claim | Model-dependent |
| Offline suitability | Strong after package install | Possible after large model download | Possible after managed model install |
| CPU/package footprint | Expected moderate; unmeasured | High risk due PyTorch/model size | Potentially efficient; unmeasured |
| Model management | Pair-oriented packages | Large cache/model lifecycle | Highest: conversion, tokenizer, model lifecycle |
| Windows packaging risk | Moderate | High | Moderate to high native-DLL risk |
| Licensing certainty | Per-package review required | Blocked for reviewed CC-BY-NC model | Per-model review required |
| Implementation complexity | Lowest | High | High |
| Maintainability | Promising | Limited by runtime/model size | Limited by model selection/operations |

## Recommendation and 38D2 boundary

**Recommend an Argos Translate-only 38D2 adapter spike, contingent on
verifying the exact English-to-Spanish and English-to-German package licenses.**
It is the smallest path to an optional, offline, pair-oriented local provider.
This is not a production recommendation until the fixed corpus has measured
quality/performance results, model terms are verified, and Windows packaging is
tested.

38D2 should add one unregistered `ArgosTranslationProvider` adapter. Its
factory/adapter must lazily import Argos and inspect only the configured local
package directory. It must map only documented supported language pairs,
construct explicit failed results for absent packages/unsupported codes, and
return the existing immutable `TranslationResult`. It must not select source
text, auto-download a model, pivot automatically, register itself, or alter
the OCR/Excel/UI layers.
