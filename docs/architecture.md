# VideoText Architecture

## Design Philosophy

Each module has one responsibility.

video_reader.py
    Opens videos and provides metadata.

frame_extractor.py
    Reads frames and detects significant visual changes.

Future Modules

ocr_processor.py
    Extract text from saved frames.

excel_exporter.py
    Write extracted text to Excel.