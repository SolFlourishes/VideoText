# Argos Operational and Licensing Validation (38G3)

**Status: no-go for VideoText 1.6 GUI enablement or package bundling.**

## Environment and library attempt

Validation was attempted on Windows with Python 3.12.10 in the VideoText
development virtual environment. `argostranslate` was not previously installed.
A development-only `pip install argostranslate` was started on 2026-08-07 but
made no progress output within two minutes and was stopped. The library was not
installed. `ctranslate2 4.8.1` and `sentencepiece 0.2.2` were already present
as partial dependency artifacts; no Argos model package was downloaded.

## Required models and licensing blocker

The official Argos index identifies `translate-en_es` version 1.0 and
`translate-en_de` version 1.0 as direct language pairs. The package filenames
are `translate-en_es-1_0.argosmodel` and `translate-en_de-1_0.argosmodel`.
The official package index supplies download links, but the current model
metadata/documentation does not establish a redistribution or commercial-use
license for either required model. The project’s own open licensing issue lists
both packages as lacking a specified license.

The Argos Translate library itself is MIT/CC0, but that does **not** establish
model-package redistribution permission. Therefore VideoText must not bundle,
download, or enable these packages until primary-source licensing is verified.

Sources consulted:

- Argos Translate repository and license: <https://github.com/argosopentech/argos-translate>
- Official package index: <https://github.com/argosopentech/argospm-index/blob/main/index.json>
- Official package directory: <https://data.argosopentech.com/argospm/v1/>
- Open licensing issue: <https://github.com/argosopentech/argos-translate/issues/507>
- Package-directory setting: <https://argos-translate.readthedocs.io/en/latest/source/settings.html>

## Explicit directory policy and runtime status

Argos documents `ARGOS_PACKAGES_DIR` as the process-level package-directory
setting. The adapter already accepts an explicit package directory for
inspection, but no installed library/models were available to verify that normal
runtime translation uses the same directory rather than global installed state.

If this gate is reopened, use a normal-user-writable, application-owned
directory (for example, a portable VideoText data directory), set it explicitly
before Argos runtime loading, and prove in an isolated process that inspection
and translation resolve the same en→es and en→de packages. Do not use a
developer path or an unrelated user cache.

## Deferred operational checks

The following have not run because no legally cleared model package exists:

- offline en→es and en→de translation;
- fixed-corpus translation output and sanity review;
- package checksums/sizes/attribution verification;
- multi-instance process-global directory behavior;
- PyInstaller/portable-build size and native-runtime validation.

Argos remains visible as **Local (Argos) — Not configured**. It requires no
cloud API key when configured, but VideoText makes no claim that a distributable
offline setup is currently available.
