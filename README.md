# VideoText

VideoText 1.7.1 converts presentation and lecture videos into structured,
editable OCR text and can optionally create machine-translation review
artifacts. OCR remains the canonical evidence: translation is downstream,
never overwrites OCR, and always requires human review.

## What VideoText does

VideoText identifies stable presentation frames, runs PaddleOCR, reconstructs
reading order and paragraphs, consolidates repeated observations, and exports
Markdown, CSV, and Excel. Preserved raw OCR evidence supports confidence
statistics, replay from cached stages, diagnostics, and human review.

VideoText includes optional translation:

- **Local Translation** uses the separately installed M2M100 Local Translation
  Pack through CTranslate2 and SentencePiece. It works offline and requires no
  API key or cloud account.
- **OpenAI Cloud** uses a user-supplied OpenAI API key for the current session.
  VideoText displays a cloud disclosure first, does not persist the key, and
  sends OCR-derived text—not video or image data—to the provider.

Both providers can translate to multiple target locales. Single- and
multi-video jobs can produce Translation Review Workbooks, translation CSV,
and translation Markdown in a `translations` directory beside the originating
OCR run. Deterministic review signals mark items as **Normal Review**, **Review
Recommended**, or **Translation Failed**; these labels are not confidence
scores or automatic verification.

Version 1.7 makes the Excel workbook a lightweight human translation-review
surface. It preserves source OCR and the original AI translation separately,
while adding editable Verified Translation, Human Review Status, and Reviewer
Notes fields. Human review states are **Unreviewed**, **Accepted**, **Edited /
Verified**, and **Flagged**. Translation Failed results cannot be promoted to a
valid reviewed translation through review metadata.

Version 1.7.1 adds **Batch Translate Existing Results**. Organizations can
select multiple completed VideoText result folders and create translations for
additional target locales from their preserved reading-order caches. OCR is
not rerun, source result folders remain unchanged, and all new artifacts are
written beneath a separate translation workspace. Only reuse completed results
from a trusted source or computer.

## Supported local locales

The compatible optional Local Translation Pack supports English source text to:

- Portuguese — Brazil (`pt-BR`)
- Spanish — Latin America (`es-419`)
- Spanish — Spain (`es-ES`)
- Korean — South Korea (`ko-KR`)
- Dutch — Netherlands (`nl-NL`)

The M2M100 runtime uses generic Portuguese and Spanish language tokens.
VideoText preserves the requested locale in provenance but does not guarantee
regional lexical localization. Canadian English (`en-CA`) is available through
OpenAI Cloud, not the current local pack.

## Download and run

Download `VideoText-1.7.1-Windows-Portable.zip` from the GitHub release, extract
the entire archive to a user-writable folder, and run `VideoText.exe`. No
administrator privileges or installer are required.

VideoText Core works without the Local Translation Pack. To enable offline
translation, follow the instructions included in
the separately published Local Translation Pack and in the
[Local Translation workflow guide](docs/translation-gui-workflow.md).

### Running from source

Requirements are Windows 10/11, Python, sufficient storage for OCR models and
outputs, and FFmpeg when required by the selected video workflow.

```powershell
git clone https://github.com/SolFlourishes/VideoText.git
cd VideoText
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src\gui.py
```

Build the portable application with `build_windows.ps1 -Clean`. See the
[Windows Packaging Guide](docs/06-Windows-Packaging.md).

## Outputs and review

- **OCR Markdown, CSV, and Excel** preserve the canonical reconstructed text.
- **Translation Review Workbook** keeps original text, initial machine
  translation, editable human changes, verification fields, provenance, and a
  textual review status.
- **Translation CSV and Markdown** provide downstream views of the same
  immutable translation evidence.

Machine translation can be incomplete or incorrect. Review OCR first, then
review every translation before publication or operational use.

## Accessibility

The primary GUI and locale selector support keyboard navigation, including
Tab/Shift+Tab, Space/Enter, Up/Down navigation in the locale list, and Escape
cancellation. Review status is communicated in text rather than color alone.
`Help → Accessibility` documents keyboard guidance, accessible-output
practices, and known limitations. The design is standards-informed; VideoText
does not claim formal WCAG or Section 508 certification.

## Privacy and security

Local OCR and Local Translation can operate without cloud translation. OpenAI
Cloud is optional and BYOK: the key is masked, held for the current session
only, and is not logged, persisted, or exported. Users are responsible for
permission to process and transmit their source content.

## Documentation

- [Changelog](docs/changelog.md)
- [Use Cases](docs/USE_CASES.MD)
- [Translation Workflow](docs/translation-gui-workflow.md)
- [Translation Exports](docs/translation-exports.md)
- [Translation Review Intelligence](docs/translation-review-intelligence.md)
- [Architecture](docs/02-Architecture.md)
- [Accuracy Benchmark](docs/accuracy-benchmark.md)
- [Roadmap](docs/Roadmap.md)

## Known limitations

OCR is optimized for presentation-style video with stable, readable text and
can be affected by resolution, motion, occlusion, decorative typography, and
low contrast. OCR and all machine translations require human review. Local
translation supports only installed approved mappings and does not guarantee
regional Spanish or Portuguese wording. OpenAI Cloud requires internet access,
a valid user key, and may incur charges.

## License

No open-source license has been granted for VideoText itself. The repository's
source remains subject to applicable copyright law. Redistributed third-party
components and the optional model pack retain their own licenses and notices.

Created and maintained by **Sol Roberts-Lieb** under **SolFlourishes**.
