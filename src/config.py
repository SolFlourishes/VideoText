"""
config.py

Application-wide configuration settings.
"""

# Frame detection
FRAME_DIFFERENCE_THRESHOLD = 10.0
MAX_SECONDS_BETWEEN_CAPTURES = 5.0

# OCR
OCR_LANGUAGE = "en"

# Minimum recognized-region confidence retained by reading-order processing.
MIN_CONFIDENCE = 0.60
