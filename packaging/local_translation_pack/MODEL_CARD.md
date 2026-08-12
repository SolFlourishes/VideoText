# M2M100 418M deployment model

This pack contains an int8 CTranslate2 conversion of
`facebook/m2m100_418M`, pinned to source revision
`55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`.

- Upstream model: <https://huggingface.co/facebook/m2m100_418M>
- Pinned source tree: <https://huggingface.co/facebook/m2m100_418M/tree/55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636>
- Upstream license identifier: MIT
- Deployment conversion: CTranslate2 4.8.1, int8

The source model supports generic M2M100 language tokens. VideoText maps the
validated English-source pairs to exact application locale identifiers while
preserving that requested locale in provenance. The model does not guarantee
Brazilian, Latin-American, or Spain-specific lexical localization.

This release artifact omits the original approximately 3.8 GB source-model
staging, float32 conversion staging, PyTorch/Transformers conversion
environment, and development caches.
