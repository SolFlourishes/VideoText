"""User-facing Help and About text for the VideoText desktop application."""


def get_how_to_use_text() -> str:
    """Return the content used by the formatted VideoText user guide."""

    return """VideoText User Guide

What is VideoText?

VideoText extracts readable text from presentation videos and produces documents that can be reviewed, edited, and translated.

Getting Started

1. Select a video.
2. Choose an output folder.
3. Select export formats.
4. Click Start.
5. Review the exported files.

Video URLs

URL mode accepts direct HTTP or HTTPS links to downloadable video files. Webpage links are not video-file links: YouTube watch pages and protected cloud-sharing pages are not currently supported. Only process content you are authorized to access.

Processing Stages

Candidate Frames — finds stable video frames that are useful for text extraction.
OCR — reads visible text from each candidate frame.
Reading Order — puts detected text into its intended visual order.
Paragraph Reconstruction — joins related lines into readable paragraphs.
Slide Consolidation — combines evidence from repeated views of a slide.
Exports — writes the selected review documents.

Export Formats

Markdown
Readable, editable text for notes, documents, and text editors.

CSV
Simple row-based data for analysis, import, and lightweight editing.

Excel Translation Workbook
A formatted workbook for review and translation. Translators can edit the blank Translated Text column while keeping the reconstructed original text available for reference.

Batch Processing

Batch Processing handles multiple videos in one selected output location. Each video receives its own workspace, processing continues after an individual failure, and a batch log records the outcome of every item.

Advanced Mode (Replay)

Advanced Mode resumes from Candidate frames cache, OCR results cache, or Reading-order cache. It is useful for fast replay when changing exports or formatting, rather than for normal first-time processing.

Note
Replay processing skips OCR and is therefore much faster than processing the original video again.

Only open replay cache files created by VideoText on a trusted computer.
Replay caches use Python pickle files, which can run code when opened, so do
not use cache files from unknown or untrusted sources.

Output Folder Structure

output/
    lecture/
        candidate_frames/
        cache/
            candidate_frames.pkl
            ocr_results.pkl
            reading_order.pkl
        lecture.xlsx
        lecture.csv
        lecture.md

Tips

• Review OCR output, especially unusual characters and complex slide layouts.
• Replay is much faster than full processing.
• Use Excel for translation and review.
• Batch processing is useful for multiple lectures.

Troubleshooting

Slow OCR
OCR is often the longest stage; use the progress display to monitor it.

Missing text
Review the source video and exported text. Resolution, animation, contrast, and unusual fonts can affect OCR.

Replay availability
Select the matching .pkl checkpoint or a prior run folder containing cache/.

Output location
Each run is saved in its own folder beneath the output location you selected.
"""


def get_accuracy_validation_text() -> str:
    """Return the user-facing explanation of VideoText accuracy and validation."""

    return """Accuracy & Validation

What VideoText Is Designed For

VideoText is optimized for extracting visible text from lecture recordings, classroom presentations, webinars, conference presentations, screen-recorded slide decks, and other presentation-style instructional videos. It reconstructs readable documents from the visible content of those slides.

How VideoText Works

VideoText selects stable video frames, reads visible text with OCR, determines reading order, reconstructs paragraphs, consolidates repeated views of slides, and exports the result into the formats you choose.

Expected Accuracy

VideoText supports high-quality extraction of visible text from presentation-style and instructional videos. Extraction accuracy is typically very high for this type of content, but no OCR system can guarantee perfect extraction under every condition.

Factors That Affect Accuracy

Examples include low video resolution, small fonts, motion blur, fast animations, decorative fonts, poor contrast, heavy compression, partially obscured text, complex diagrams, and handwritten content.

Validation

VideoText is continuously validated using automated regression testing, deterministic smoke tests, replay validation, export validation, and real-world presentation videos. AI-assisted comparison of extracted text against visible slide content is one component of this broader validation process; it does not guarantee correctness on its own.

Engineering Philosophy

Every release is checked against a growing suite of deterministic regression tests so that improvements do not unintentionally change previously verified behavior.

Future Validation

Ongoing benchmarking and validation will continue to expand support and characterize performance across additional video types.

Practical Recommendation

For presentation-style instructional content, VideoText provides an excellent starting point for documentation and note generation. When complete fidelity is required, review extracted text against the original video.
"""


def get_about_text() -> str:
    """Return the concise VideoText application description."""

    sections = get_about_sections()
    return "\n\n".join(
        "\n".join((heading, *items)) for heading, items in sections
    )


def get_about_sections() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return concise About prose separately from its Tkinter presentation."""

    return (
        (
            "What VideoText Does",
            (
                "VideoText processes lecture and presentation videos and "
                "reconstructs readable, editable text for review and translation.",
            ),
        ),
        (
            "Privacy and Storage",
            (
                "• Processing occurs locally on this computer.",
                "• Processing outputs and caches stay beneath the selected output folder.",
                "• Small user preferences are stored in the user's application-data folder.",
            ),
        ),
        (
            "Application Information",
            (
                "• VideoText does not require administrator rights.",
                "• VideoText does not create Windows registry entries.",
                "• VideoText does not install or run background services.",
            ),
        ),
    )


def get_about_introduction() -> str:
    """Return the short description displayed below the About title area."""

    return (
        "VideoText turns presentation videos into readable, editable documents "
        "for review and translation."
    )
