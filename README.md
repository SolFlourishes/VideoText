# VideoText

**VideoText converts presentation and lecture videos into structured, editable text.**

Instead of performing OCR on every video frame, VideoText identifies stable presentation frames, extracts visible text, reconstructs reading order and paragraph structure, consolidates repeated observations, and exports the results into usable document formats.

> **Current version: 1.4.0**
## New in Version 1.4.0

- Engine-neutral OCR contract with a PaddleOCR adapter
- Deterministic engine registration and discovery
- Paddle remains the only built-in and default OCR engine
- Preprocessing experiments and benchmarks use the shared OCR contract
- Clear VideoText Windows application icon

## Why VideoText?

Important information is often trapped inside recorded lectures, presentations, webinars, and training videos. Slide text may be visible on screen but difficult to search, edit, reuse, or review.

VideoText is designed to recover that material while preserving more of its logical structure than a simple frame-by-frame OCR export.

VideoText can help:

* Educators recover text from recorded presentations
* Learners create searchable study materials
* Accessibility professionals identify visible text in video content
* Researchers analyze presentation-based video collections
* Content creators repurpose material from recorded slides
* Institutions preserve editable versions of instructional content

## VideoText in Action

### Select and process a presentation video

![VideoText application window](docs/images/main.png)

### Convert visible slide content into editable output

![VideoText reconstructed output](docs/images/processing-complete.png)

## Current Capabilities

VideoText currently supports:

* Local video-file analysis
* Stable-frame and presentation-state detection
* Engine-neutral OCR processing with PaddleOCR as the default engine
* Reading-order reconstruction
* Paragraph and text-block reconstruction
* Duplicate and near-duplicate consolidation
* Terminal-slide detection
* Replay of stored OCR observations without rerunning the entire video
* Markdown export
* CSV export
* Excel export
* Diagnostic output for testing and refinement
* Windows application packaging
* Offline processing after required models are available
* Automated testing and benchmark evaluation

## How It Works

VideoText processes a video through several stages:

1. **Video analysis**
   The application reads the video and samples its visual content.

2. **Stable-frame detection**
   It identifies points where presentation content has stabilized rather than treating every frame as unique.

3. **Text recognition**
   The OCR engine contract returns visible words and their screen coordinates.
   Version 1.4 uses PaddleOCR through the built-in Paddle adapter.

4. **Geometric reconstruction**
   Detected text is organized using its position, alignment, spacing, and reading order.

5. **Duplicate consolidation**
   Repeated observations of the same slide or text state are combined.

6. **Document export**
   The reconstructed content is exported into formats that can be searched, edited, analyzed, and reused.

## Example Workflow

```text
Lecture or presentation video
            ↓
Stable presentation frames
            ↓
OCR observations and coordinates
            ↓
Reading-order and paragraph reconstruction
            ↓
Duplicate consolidation
            ↓
Markdown, CSV, or Excel output
```

## Download

A packaged Windows release will be available through the repository's **Releases** section.

Until the first public installer is posted, developers can run VideoText from the source code using the instructions below.

## Running from Source

### Requirements

* Windows 10 or Windows 11
* Python
* FFmpeg, when required by the selected video workflow
* Sufficient storage for OCR models and generated output

Performance depends on:

* Video length
* Video resolution
* Number of presentation changes
* CPU performance
* Available memory
* Disk speed
* OCR model initialization and inference time

### Installation

Clone the repository:

```bash
git clone https://github.com/SolFlourishes/VideoText.git
cd VideoText
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it in PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the required packages:

```bash
pip install -r requirements.txt
```

Run the application using python src/main.py

> The precise launch command may change as packaging is finalized. See the project and packaging documentation for the current development workflow.

## Building the Windows Application

The repository includes:

* `VideoText.spec`
* `build_windows.ps1`
* `requirements-packaging.txt`
* A dedicated packaging directory
* Windows packaging documentation

See:

* [Windows Packaging Guide](docs/06-Windows-Packaging.md)
* [Release 1.0 Documentation](docs/Release-1.0.md)

## Output Formats

### Markdown

Markdown output is intended to provide readable, editable text with reconstructed headings and paragraphs.

### CSV

CSV output provides structured data suitable for analysis, review, comparison, and import into other applications. Processing exports append document-level OCR confidence fields for region count, minimum, maximum, mean, median, low-confidence count and proportion, and the active threshold.

### Excel

Excel output provides a familiar tabular format for reviewing extracted text and associated metadata.

### OCR Confidence

VideoText preserves the original OCR regions before confidence filtering so confidence statistics describe the complete OCR evidence, including regions later excluded from reconstruction. The completion dialog shows document-level OCR Quality details, and CSV exports include the same summary fields. Confidence statistics are descriptive: low-confidence regions do not rewrite or correct the extracted text.

### OCR Engine Framework

VideoText uses a small OCR engine contract so the processing pipeline receives
the same canonical OCR regions regardless of the underlying engine. Version
1.4 registers Paddle as the only built-in and default engine; there is no GUI
or command-line engine selector. Additional engines and comparisons are planned
for Version 1.5. Preprocessing experiments and benchmarks use this same
contract. The manual Paddle probe remains a developer diagnostic for inspecting
raw PaddleOCR responses directly.

## Accuracy and Validation

VideoText includes a benchmark and diagnostic framework for measuring extraction quality and identifying reconstruction errors.

The project evaluates more than raw character recognition. Validation also considers:

* Reading order
* Line joining
* Paragraph boundaries
* Punctuation handling
* Duplicate suppression
* Slide-state reconstruction
* Geometric relationships between detected text regions

See:

* [Accuracy Benchmark](docs/accuracy-benchmark.md)
* [OCR Diagnostics](docs/ocr-diagnostics.md)
* [OCR Preprocessing Experiments](docs/ocr-preprocessing-experiments.md)
* [Testing and Roadmap](docs/05-Testing-and-Roadmap.md)

## Known Limitations

VideoText is primarily designed for presentation-style videos in which text remains visible long enough to form a stable visual state.

Results may be less reliable when:

* Text is very small
* Video resolution is low
* Compression artifacts obscure letters
* Slides contain highly decorative typography
* Text moves continuously
* A presenter frequently blocks slide content
* Animations reveal text only briefly
* Backgrounds have low contrast
* Handwriting is used
* The video consists primarily of natural scenes rather than presentation content

OCR output should be reviewed before being treated as an exact transcription.

## Documentation

Detailed technical documentation is available in the [`docs`](docs) directory.

Key documents include:

* [Project Vision](docs/01-Vision.md)
* [Architecture](docs/02-Architecture.md)
* [Data Model](docs/03-Data-Model.md)
* [Algorithms](docs/04-Algorithms.md)
* [Testing and Roadmap](docs/05-Testing-and-Roadmap.md)
* [Windows Packaging](docs/06-Windows-Packaging.md)
* [Accuracy Benchmark](docs/accuracy-benchmark.md)
* [Changelog](docs/changelog.md)
* [Engineering Log](docs/engineering_log.md)

## Project Status

VideoText has moved beyond its original proof of concept and now includes an end-to-end extraction and reconstruction pipeline, multiple export formats, testing infrastructure, benchmark tools, diagnostics, and Windows packaging support.

Current work is focused on:

* Improving processing speed
* Preserving extraction accuracy
* Refining Windows distribution
* Expanding benchmark coverage
* Improving the user experience
* Producing clear public documentation and examples

## Roadmap

Potential future work includes:

* Additional OCR-engine options
* Improved GPU acceleration
* Expanded language support
* More configurable reconstruction settings
* Better handling of complex slide layouts
* Additional accessibility workflows
* Batch processing
* Improved progress and performance reporting
* Broader platform support

Roadmap items are exploratory and are not guaranteed for a particular release.

## Contributing

VideoText is currently under active development.

Bug reports, reproducible test cases, benchmark examples, and carefully scoped improvement suggestions are welcome through GitHub Issues.

Before contributing code, please review the architecture, algorithms, and testing documentation.

## Privacy

VideoText is designed to process local video files. Users are responsible for ensuring that they have permission to process, store, and export the content contained in those videos.

## License

License information will be added before or alongside the first broadly distributed public release.

Until a license is added, the presence of source code in this public repository should not be interpreted as permission to copy, modify, or redistribute it.

## Author

Created and maintained by **Sol Roberts-Lieb** under **SolFlourishes**.

VideoText began as an effort to make presentation-based video content more searchable, editable, reusable, and accessible.
