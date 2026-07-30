# VideoText Project

## Purpose

VideoText converts visible text in presentation-style videos into structured, editable documents.

The project is designed to do more than run OCR on arbitrary frames. Its purpose is to identify meaningful presentation states, recover visible text, reconstruct reading order and paragraph relationships, consolidate repeated observations, and export the results into formats that people can search, edit, analyze, and reuse.

Primary use cases include:

* Lecture and presentation recovery
* Searchable study-material creation
* Accessibility review
* Educational-content reuse
* Research involving presentation-based video
* Structured analysis of visible video text

## Current Status

**Current documented version: 1.2.0**

VideoText has progressed beyond its original proof of concept.

The repository currently includes:

* Video ingestion and analysis
* Stable-frame detection
* PaddleOCR integration
* OCR-coordinate storage
* Reading-order reconstruction
* Paragraph reconstruction
* Duplicate and near-duplicate handling
* Terminal-slide detection
* Replay architecture
* Markdown, CSV, and Excel export
* Automated testing
* Benchmark and diagnostic tools
* Windows packaging scripts and configuration
* Architecture and algorithm documentation

The current development phase is focused on strengthening public distribution, improving processing performance, preserving extraction quality, and expanding validation.

## Architecture Documents

Core documentation is maintained in the `docs` directory:

* [`docs/01-Vision.md`](docs/01-Vision.md) — Project purpose and guiding principles
* [`docs/02-Architecture.md`](docs/02-Architecture.md) — System architecture
* [`docs/03-Data-Model.md`](docs/03-Data-Model.md) — Internal data structures
* [`docs/04-Algorithms.md`](docs/04-Algorithms.md) — Detection and reconstruction algorithms
* [`docs/05-Testing-and-Roadmap.md`](docs/05-Testing-and-Roadmap.md) — Testing strategy and roadmap
* [`docs/06-Windows-Packaging.md`](docs/06-Windows-Packaging.md) — Windows packaging process
* [`docs/accuracy-benchmark.md`](docs/accuracy-benchmark.md) — Accuracy evaluation
* [`docs/ocr-diagnostics.md`](docs/ocr-diagnostics.md) — OCR diagnostic procedures
* [`docs/engineering_log.md`](docs/engineering_log.md) — Engineering decisions and development history
* [`docs/changelog.md`](docs/changelog.md) — Version history

## Repository Structure

```text
VideoText/
├── benchmarks/              Accuracy and performance benchmark materials
├── docs/                    Architecture, testing, packaging, and project documentation
├── packaging/               Windows packaging resources
├── src/                     Application source code
├── tests/                   Automated tests
├── tools/                   Development and diagnostic utilities
├── VideoText.spec           PyInstaller configuration
├── build_windows.ps1        Windows build script
├── requirements.txt         Runtime and development dependencies
└── requirements-packaging.txt
                            Packaging dependencies
```

## Coding Standards

Development should follow these principles:

1. Preserve extraction quality before optimizing speed.
2. Keep OCR observations separate from document reconstruction when practical.
3. Make reconstruction behavior deterministic and testable.
4. Add regression tests when correcting extraction errors.
5. Avoid silently discarding uncertain text.
6. Preserve enough diagnostic information to reproduce failures.
7. Prefer explicit configuration over hidden behavior.
8. Document meaningful algorithm or architecture changes.
9. Validate packaged behavior separately from source behavior.
10. Keep user-facing output understandable to nontechnical users.

## How to Build

### Development Environment

Create and activate a Python virtual environment:

```bash
python -m venv .venv
```

PowerShell activation:

```powershell
.venv\Scripts\Activate.ps1
```

Install application dependencies:

```bash
pip install -r requirements.txt
```

Install packaging dependencies when preparing a Windows build:

```bash
pip install -r requirements-packaging.txt
```

### Windows Package

The repository includes a PowerShell build script:

```powershell
.\build_windows.ps1
```

Before treating a build as releasable:

* Build from a clean environment
* Confirm that required OCR models are available or correctly downloaded
* Test application launch
* Process a known sample video
* Verify all supported exports
* Test on a second Windows machine or clean Windows environment
* Record the application version
* Generate a release checksum

See [`docs/06-Windows-Packaging.md`](docs/06-Windows-Packaging.md) for the detailed packaging process.

## How to Test

Run the automated test suite from the repository root.

The exact command should match the currently configured test runner. A typical command is:

```bash
pytest
```

Before a public release, testing should cover:

* Unit tests
* Reconstruction regression tests
* Benchmark videos
* Markdown export
* CSV export
* Excel export
* Source execution
* Packaged execution
* First-run OCR initialization
* Long-video behavior
* Error handling
* Output-folder handling

Do not publish a release solely because the executable builds successfully. The packaged application must also process a known video and produce verified output.

## Current Priorities

### 1. Public Repository

* Replace outdated prototype documentation
* Add repository description and topics
* Add screenshots or demonstration media
* Publish clear installation and usage instructions
* Clarify licensing and contribution expectations

### 2. Windows Distribution

* Finalize the packaged application
* Verify clean-machine installation
* Define model-distribution behavior
* Add version information
* Generate checksums
* Publish the first GitHub release

### 3. Performance

* Measure video-decoding time
* Measure stable-frame analysis time
* Measure OCR initialization time
* Measure OCR inference time
* Measure reconstruction and export time
* Identify optimizations that do not reduce output quality

### 4. Accuracy

* Expand benchmark coverage
* Preserve punctuation and line relationships
* Improve complex-layout reconstruction
* Reduce false duplicate removal
* Document known failure modes

### 5. User Experience

* Improve progress reporting
* Clarify processing stages
* Make errors understandable
* Improve output-folder selection
* Provide useful completion summaries
* Add accessible user documentation

## Known Issues and Limitations

VideoText may produce weaker results when:

* Text is small or blurred
* Video compression is severe
* Slide backgrounds have low contrast
* A presenter obscures content
* Text moves continuously
* Animations reveal incomplete fragments
* Layouts use multiple complex columns
* Text is handwritten
* Slides use highly decorative fonts
* Source video resolution is low

Processing speed is also sensitive to video length, resolution, CPU capability, available memory, disk performance, and OCR-model behavior.

Known issues should be converted into GitHub Issues when they are specific enough to reproduce and resolve.

## Next Milestone

The next milestone is a polished public Windows release supported by:

* An accurate repository homepage
* A version-aligned README
* Verified installation instructions
* A tested executable
* Sample input and output
* Release notes
* A checksum
* A defined license
* Known limitations
* Clean-machine validation

The release should prioritize reliability, transparency, and output quality over adding new features.
