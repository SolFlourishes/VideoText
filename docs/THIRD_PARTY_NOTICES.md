# Third-Party Notices for VideoText 1.6.0

VideoText's portable distribution contains third-party Python packages, native
libraries, and package metadata. Their licenses remain independent; no single
dependency license covers another component or VideoText itself.

Key runtime components include:

- PaddleOCR 3.3.3 and PaddlePaddle 3.2.0 for OCR
- PaddleX runtime components used by PaddleOCR
- OpenAI Python SDK 2.53.0 for optional BYOK cloud translation
- HTTPX, HTTP Core, H11, and Certifi for the OpenAI HTTP/TLS stack
- CTranslate2 4.8.1 for optional local translation inference
- SentencePiece 0.2.2 for local tokenization
- OpenCV, NumPy, and OpenPyXL for video/image and workbook processing

The portable package preserves installed distribution metadata and license
files collected by the packaging tool where supplied by those distributions.
Operators preparing public artifacts should retain the complete `_internal`
directory; removing files from it can break both runtime behavior and license
notice preservation.

The optional Local Translation Pack has separate model attribution and notices
in its `NOTICE.md` and `MODEL_CARD.md`. The M2M100 model license does not cover
CTranslate2, SentencePiece, or VideoText.

VideoText itself has no granted open-source license at this release-preparation
stage and remains subject to applicable copyright law.
