"""User-facing Help and About text for the VideoText desktop application."""


def get_how_to_use_text() -> str:
    """Return the plain-language VideoText usage guide."""

    return """What VideoText does

VideoText extracts visible text from lecture and presentation videos. It selects stable candidate frames, applies OCR, reconstructs reading order and paragraphs, consolidates repeated slide content, and exports editable text files.

VideoText creates a reconstructed editable document, not a guaranteed verbatim transcript. Review results carefully, especially for unusual layouts, handwritten content, low-resolution video, animation, overlapping text, uncommon symbols, and highly unstructured slides.

What to expect during processing

VideoText reports these stages:

• Selecting stable frames
• Running OCR
• Reconstructing paragraphs
• Consolidating slides
• Exporting files

OCR is often the longest stage. Processing time varies with video length, the number of candidate frames, image quality, the amount and complexity of visible text, and computer performance.

Normal Mode

1. Select a video.
2. Select an output folder.
3. Select export formats.
4. Start processing.
5. Review the completion summary and exported files.

Advanced Mode

Advanced Mode resumes from a previously saved checkpoint without rerunning earlier stages. Available resume points are Candidate frames cache, OCR results cache, and Reading-order cache.

Select either the expected .pkl checkpoint directly or a prior run folder containing the cache directory. A resumed run creates a new replay folder and does not overwrite the original run.

Output structure

output/
    sample/
        candidate_frames/
        cache/
            candidate_frames.pkl
            ocr_results.pkl
            reading_order.pkl
        sample.md
        sample.csv
        sample.xlsx

Repeated runs create unique folders such as sample_2, sample_replay, and sample_replay_2.

Export formats

Markdown
Readable, editable text for notes, documents, and text editors.

CSV
Simple row-based data for analysis, import, and lightweight editing.

Excel
A formatted workbook for review, translation, annotation, and structured editing. Each reconstructed paragraph remains in one row, with continuation lines formatted for readability.

Reviewing results

Check slide order, headings, line breaks, unusual characters, missing or duplicated content, and layouts with multiple columns or floating text.

Troubleshooting

Locked Excel files
Close the workbook before exporting again.

Missing checkpoint
Select the expected .pkl file or the prior run folder that contains cache/.

Slow OCR
This may be normal for text-heavy or long videos. Use the progress display to monitor the run.

Poor OCR output
Resolution, compression, animation, contrast, and unusual fonts can affect results.

Failed resumed run
Verify that the selected cache matches the selected Advanced Mode stage.
"""


def get_about_text() -> str:
    """Return the concise VideoText application description."""

    return """VideoText

VideoText reconstructs editable text from lecture and presentation videos.

Processing occurs locally on your computer. Output and cache files are stored beneath the output folder you select.

VideoText does not require administrator rights, create registry entries, or use background services.
"""
