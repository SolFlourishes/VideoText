"""Deterministic, experiment-only image variants for OCR evaluation."""
from dataclasses import dataclass
import cv2
import numpy as np

VARIANTS = ("original", "grayscale", "contrast", "sharpen", "threshold", "upscale", "upscale_sharpen")

@dataclass(frozen=True)
class OCRPreprocessingResult:
    variant: str
    image: np.ndarray
    original_dimensions: tuple[int, int]
    output_dimensions: tuple[int, int]
    parameters: dict[str, object]

def list_preprocessing_variants() -> tuple[str, ...]: return VARIANTS

def apply_preprocessing_variant(image: np.ndarray, variant: str) -> OCRPreprocessingResult:
    if variant not in VARIANTS: raise ValueError(f"Unknown preprocessing variant: {variant}")
    source = image.copy(); height, width = source.shape[:2]
    gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY) if source.ndim == 3 else source.copy()
    params: dict[str, object] = {}
    if variant == "original": output = source
    elif variant == "grayscale": output = gray
    elif variant == "contrast": output = cv2.convertScaleAbs(gray, alpha=1.25, beta=0); params={"alpha":1.25}
    elif variant == "sharpen": output = cv2.filter2D(gray, -1, np.array([[0,-1,0],[-1,5,-1],[0,-1,0]], dtype=np.float32)); params={"kernel":"conservative"}
    elif variant == "threshold": output = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]; params={"method":"otsu"}
    elif variant == "upscale": output = cv2.resize(source, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC); params={"scale":1.5,"interpolation":"cubic"}
    else:
        enlarged=cv2.resize(gray,None,fx=1.5,fy=1.5,interpolation=cv2.INTER_CUBIC); output=cv2.filter2D(enlarged,-1,np.array([[0,-1,0],[-1,5,-1],[0,-1,0]],dtype=np.float32)); params={"scale":1.5,"sharpen":True}
    return OCRPreprocessingResult(variant, output, (width,height), (output.shape[1],output.shape[0]), params)
