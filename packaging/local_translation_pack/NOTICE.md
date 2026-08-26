# Local Translation Pack Notices

## M2M100

Model: `facebook/m2m100_418M` at revision
`55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636`.

The official pinned model metadata identifies the model license as MIT. Preserve
the included model card and this license information when redistributing the
pack. The converted int8 weights are derived from that pinned source revision;
VideoText's manifest records the conversion and does not claim a new model
license.

## CTranslate2

VideoText Core uses CTranslate2 4.8.1 for local inference. CTranslate2 is
licensed under MIT; see its distributed license notice in the core package.

## SentencePiece

VideoText Core uses SentencePiece 0.2.2 for tokenization. SentencePiece is
licensed under Apache-2.0; see its distributed license notice in the core
package.

## VideoText

VideoText itself is not distributed under the dependency or model licenses
listed above. No open-source license has been granted for the VideoText source;
third-party notices apply only to their respective components.
