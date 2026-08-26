# Optional Translation Workflow

Translation is explicitly opt-in in the VideoText GUI. When **Translate OCR
text** is off, no provider, credential, request, package inspection, or network
activity occurs. Users select one or more target locales, a workbook grouping,
and one or more translation outputs. In Single video mode the fixed, useful
organization is **One workbook per video**, with one worksheet per selected
target locale. Batch mode retains all four grouping choices.

The GUI separates **OCR Outputs** (Markdown, CSV, and Excel containing the
canonical OCR-derived document) from **Translation Outputs**. Translation
outputs are Translation Review Workbook, Translation CSV, and Translation
Markdown. The Translation Review Workbook is the separate human-review artifact
with source, AI, editable, verification, and review-status columns.

Target locales use a compact chooser rather than a long checkbox list. The
collapsed control summarizes the selection; press Space to select choices and
Enter to apply them. Local Translation shows only exact installed/approved
locale mappings as selectable. Changing provider never silently clears an
existing choice; unavailable selected locales are called out and must be
resolved before processing.

OpenAI is the current selectable cloud provider. Before execution, VideoText
explains that selected OCR-derived text is sent to OpenAI, that video/image data
is not sent by the translation provider, and that API use may incur charges. The
API key is requested for the current session only and is not persisted, logged,
or written to workbook metadata. The approved model is `gpt-4.1-mini`.

The model is configured once in `translation_settings.OPENAI_TRANSLATION_MODEL`.
The GUI offers only fixed vetted choices and labels its tested default as
**Recommended**. It does not fetch a newest-model list or accept arbitrary model
IDs in the normal interface.
VideoText never reads a developer key from the environment or ships a key. If
OpenAI rejects the configured model, only that translation request fails with a
clear model-unavailable result; OCR and its exports remain intact, and VideoText
does not retry or switch to another model. A future replacement requires corpus
evaluation, availability and pricing review, a single setting change, regression
tests, and a maintenance release. Model comparison is deferred to Task 38G2B.

Local Translation uses approved external CTranslate2/M2M100 model directories.
Its runtime and model are loaded only after OCR has completed. VideoText does
not download models or fall back to another provider.

Manual validation: OCR-only run; single and batch Spanish; single and batch
Spanish/German; each grouping mode; cancel the disclosure; omit the API key;
simulate one failed request; verify Argos is unavailable; navigate controls by
keyboard; and inspect completion logs and outputs.

## Validation status

Automated tests validate deterministic job composition, all four workbook
grouping modes, successful and failed evidence export, no-overwrite behavior,
and completion-summary formatting. A packaged Sample2 OCR-results-cache run
validated five local target locales: 55 translations succeeded, none failed,
and four were marked Review Recommended. OCR Quality, Translation, and
Translation Outputs are separate completion-summary sections. Physical offline
operation and the keyboard-only GUI matrix passed interactive operator checks.
No key is available to automated tests, and none is read from environment
variables.

Argos remains gated on a supported Windows runtime installation, approved
explicit package directory, exact en-to-es and en-to-de package identities and
licenses, offline execution, fixed-corpus evaluation, and portable-package
impact review.

The 38G3 attempt confirmed that the Argos library and its required en→es/en→de
model packages are not release-ready here: the development installation did not
complete, and current primary model-license evidence does not clear either
required package for redistribution. Argos therefore remains disabled; see
`docs/argos-operational-validation.md`.

Translation output folders remain adjacent to the originating OCR evidence: a
single run writes `<run-output>/translations/`, while a batch writes beneath
its selected batch-output root. This keeps downstream review artifacts with the
OCR run that produced their source evidence.
