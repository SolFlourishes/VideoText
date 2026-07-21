"""
config.py

Application-wide configuration settings.
"""

# Frame detection
FRAME_DIFFERENCE_THRESHOLD = 10.0
MAX_SECONDS_BETWEEN_CAPTURES = 5.0
COOLDOWN_FRAMES = 30

# Image processing
COMPARISON_WIDTH = 320
COMPARISON_HEIGHT = 180

# Output
OUTPUT_FOLDER = "output"
CACHE_FOLDER = "output/cache"
CANDIDATE_FRAME_FOLDER = "output/candidate_frames"

# OCR
OCR_LANGUAGE = "en"
MINIMUM_OCR_CONFIDENCE = 0.80

# Development

CANDIDATE_CACHE = f"{CACHE_FOLDER}/candidate_frames.pkl"
OCR_CACHE = f"{CACHE_FOLDER}/ocr_results.pkl"
READING_ORDER_CACHE = f"{CACHE_FOLDER}/reading_order.pkl"