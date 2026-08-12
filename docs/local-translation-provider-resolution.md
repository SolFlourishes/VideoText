# Local Translation Provider Resolution

## Decision

VideoText 1.6 uses an external-model foundation built around the CTranslate2
runtime and the multilingual `facebook/m2m100_418M` model family. The local
provider is pair-neutral: it receives exact source and target language IDs from
the existing `TranslationRequest`, then deterministically resolves one approved
installed model. It never downloads a model, contacts a service, requests an
API key, pivots through another language, or falls back to OpenAI.

M2M100 is the selected foundation, not a bundled starter model. Its primary
model card identifies an MIT license, 101-language coverage, direct many-to-many
translation, and includes all current VideoText targets: Spanish, German,
French, Italian, Portuguese, Japanese, Korean, Chinese, and Arabic. CTranslate2
supports M2M100 and provides Windows x86-64 Python wheels for CPU operation.

## Primary locale requirements

VideoText treats `pt-BR`, `en-CA`, `es-419`, `es-ES`, `ko-KR`, and `nl-NL` as
first-class locale identifiers, not aliases for `pt`, `en`, `es`, `ko`, or `nl`.
The catalog maps an exact source locale and target locale to an approved model
configuration. It can represent future `es-AR`, `es-CL`, `es-PR`, `pt-PT`, or
`en-US` mappings without a pipeline redesign. `en-US → en-CA` is also
representable as same-language localization; its actual provider/model strategy
is deferred because M2M100 is a cross-language translation model.

M2M100 has generic language tokens for Portuguese, Spanish, Korean, and Dutch,
which is a credible technical runtime path for `pt-BR`, `es-419`, `es-ES`,
`ko-KR`, and `nl-NL`. It is not itself a locale policy. A manifest must
explicitly approve each locale pair and record its underlying runtime token; the
requested locale remains unchanged in request/result provenance and exports. No
approved locale mapping is installed yet, so none is advertised as available.

## Candidate comparison

Pair-specific OPUS-MT/Marian models with CTranslate2 remain a credible optional
language-pack strategy: smaller packages can be installed only when needed.
They require pair-by-pair licensing review, however. For example, the primary
Helsinki model cards currently list Apache-2.0 for `opus-mt-en-es` but CC-BY-4.0
for `opus-mt-en-de`; runtime licensing cannot settle those model terms. A single
multilingual M2M100 model has a clearer expansion path and avoids redesign when
adding a target language, at the cost of a substantially larger external model.

Argos remains not configured: its model-package licensing and Windows runtime
validation remain unresolved. It is not selected, bundled, or enabled.

## Catalog and storage

Approved models live outside the executable under the user-writable default:

```text
%LOCALAPPDATA%/VideoText/models/translation/
```

`VIDEOTEXT_TRANSLATION_MODELS` can explicitly select another portable root.
Each installed model directory contains a `videotext-model.json` manifest. The
manifest records model ID, model family/version, exact language pairs, local
path, license identifier, mapping revision, and compact metadata. Discovery is
deterministic and does not load, download, or translate. Regional variants are
exact matches only; `es-MX`, `pt-BR`, and `zh-TW` are not silently reduced.

The initial installation strategy is explicit approved language/model packs,
installed outside the executable. A downloader/model manager and bundled models
are deferred. An installed model is not the same as model-family support, and no
language is offered by the local GUI path until its approved manifest and files
are present.

## Current operational state

The approved external model is installed at
`%LOCALAPPDATA%/VideoText/models/translation/m2m100-418m-int8`. It was acquired
on 2026-08-07 from `facebook/m2m100_418M` at revision
`55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`, whose pinned model metadata reports
the MIT license. The development download measured 3,877,717,593 bytes because
the official repository includes both PyTorch and Rust weights. CTranslate2
4.8.1 converted the PyTorch model with `ct2-transformers-converter` on Windows
11/Python 3.12.10, using Transformers 4.57.6, Torch 2.13.0+cpu, and SentencePiece
0.2.2. Float32 conversion measured 1,948,648,472 bytes; the selected int8
conversion measures 499,726,639 bytes. The installed CTranslate2 package itself
measures 62,682,984 bytes.

Live local validation succeeded for `en → pt-BR`, `en → es-419`, `en → es-ES`,
`en → ko-KR`, and `en → nl-NL`. Initial cold translation took about 7.2 seconds;
subsequent short translations took about 0.5–0.8 seconds on this development
workstation. Both Spanish locale requests deliberately produced the same generic
Spanish output because they use the same M2M100 `es` token; VideoText preserves
the requested locale but does not claim regional lexical localization. The same
limitation applies to the generic Portuguese `pt` token. `en-US → en-CA`
localization is not provided by M2M100 in 1.6.

A packaged OCR-results-cache validation of Sample2 also completed on 2026-08-07:
49 OCR frames produced 10 slides and 55 translations across `pt-BR`, `es-419`,
`es-ES`, `ko-KR`, and `nl-NL`, with 0 failures and 4 review-recommended results.
The Translation Review Workbook contained the five locale sheets and hidden
provenance metadata. Completion summaries present OCR Quality, Translation, and
Translation Outputs as separate sections. Physical disconnected-network and
keyboard-only packaged-GUI validation remain manual release checks.

The provider reads only the installed local manifest/files and has no code path
for network, OpenAI construction, API keys, downloads, or fallback. This is the
offline proof: the tested provider was instantiated directly from the external
model root and produced translations solely through CTranslate2. A full
packaged-GUI and disconnected-network smoke test remains required before release.

When installed, local results preserve the original immutable request and add
provider/model/path/license/mapping provenance. They flow through the same
review-intelligence statuses as cloud results. All translations still require
human review.

## Sources

- [CTranslate2 Windows installation](https://github.com/OpenNMT/CTranslate2/blob/master/docs/installation.md)
- [CTranslate2 supported Transformers models](https://github.com/OpenNMT/CTranslate2/blob/master/docs/guides/transformers.md)
- [CTranslate2 Marian quick start](https://github.com/OpenNMT/CTranslate2/blob/master/docs/quickstart.md)
- [M2M100-418M model card](https://huggingface.co/facebook/m2m100_418M)
- [OPUS-MT English-Spanish model card](https://huggingface.co/Helsinki-NLP/opus-mt-en-es)
- [OPUS-MT English-German model card](https://huggingface.co/Helsinki-NLP/opus-mt-en-de)
