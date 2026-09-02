"""Read-only projection of exact candidate frames into visual evidence."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path

import numpy as np

from models import CandidateFrame
from visual_understanding_contract import VisualEvidenceReference, VisualOCRRegion


CANONICAL_IMAGE_MEDIA_TYPE = "image/png"
CANONICAL_PNG_COMPRESSION = 9
LOCAL_VISUAL_MAXIMUM_IMAGE_DIMENSION = 1536
LOCAL_VISUAL_IMAGE_TRANSPORT_REVISION = "local-vision-image-transport-v1"


@dataclass(frozen=True)
class CanonicalVisualImage:
    """Deterministically encoded immutable image evidence."""

    png_bytes: bytes
    media_type: str
    sha256: str
    width: int
    height: int


@dataclass(frozen=True)
class ProjectedVisualEvidence:
    """Provider-ready copies projected from one exact CandidateFrame."""

    reference: VisualEvidenceReference
    image_bytes: bytes
    image_media_type: str
    ocr_text: str
    ocr_regions: tuple[VisualOCRRegion, ...]


def bounded_visual_image_transport(
    image: CanonicalVisualImage,
    *,
    maximum_dimension: int = LOCAL_VISUAL_MAXIMUM_IMAGE_DIMENSION,
) -> CanonicalVisualImage:
    """Return a deterministic aspect-preserving PNG derivative when the bound is exceeded."""

    if not isinstance(image, CanonicalVisualImage):
        raise ValueError("image must be a CanonicalVisualImage.")
    if (
        not isinstance(maximum_dimension, int)
        or isinstance(maximum_dimension, bool)
        or maximum_dimension < 1
    ):
        raise ValueError("maximum_dimension must be a positive integer.")
    if max(image.width, image.height) <= maximum_dimension:
        return image

    import cv2

    pixels = cv2.imdecode(np.frombuffer(image.png_bytes, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if pixels is None:
        raise ValueError("Canonical visual image could not be decoded for transport sizing.")
    scale = maximum_dimension / max(image.width, image.height)
    width = max(1, round(image.width * scale))
    height = max(1, round(image.height * scale))
    resized = cv2.resize(pixels, (width, height), interpolation=cv2.INTER_AREA)
    return canonical_candidate_frame_image(resized)


def canonical_candidate_frame_image(image: np.ndarray) -> CanonicalVisualImage:
    """Encode one canonical uint8 candidate image as PNG and hash exact bytes."""

    if not isinstance(image, np.ndarray):
        raise ValueError("Candidate-frame image must be a NumPy array.")
    if image.dtype != np.uint8 or image.ndim not in (2, 3) or image.size == 0:
        raise ValueError("Candidate-frame image must be a non-empty uint8 grayscale, BGR, or BGRA array.")
    if image.ndim == 3 and image.shape[2] not in (1, 3, 4):
        raise ValueError("Candidate-frame image must contain one, three, or four channels.")

    import cv2

    success, encoded = cv2.imencode(
        ".png",
        image,
        (cv2.IMWRITE_PNG_COMPRESSION, CANONICAL_PNG_COMPRESSION),
    )
    if not success:
        raise ValueError("Candidate-frame image could not be encoded as canonical PNG evidence.")
    png_bytes = encoded.tobytes()
    height, width = image.shape[:2]
    return CanonicalVisualImage(
        png_bytes=png_bytes,
        media_type=CANONICAL_IMAGE_MEDIA_TYPE,
        sha256=hashlib.sha256(png_bytes).hexdigest(),
        width=int(width),
        height=int(height),
    )


def project_candidate_frame_evidence(
    frame: CandidateFrame,
    *,
    source_reference: str,
    slide_number: int,
    build_index: int | None = None,
    checkpoint_path: str | Path | None = None,
) -> ProjectedVisualEvidence:
    """Copy exact frame pixels and OCR context without mutating project evidence."""

    if not isinstance(frame, CandidateFrame):
        raise ValueError("frame must be a CandidateFrame.")
    authoritative_image = canonical_candidate_frame_image(frame.image)
    image = bounded_visual_image_transport(authoritative_image)
    regions: list[VisualOCRRegion] = []
    for source_index, region in enumerate(frame.ocr_results):
        coordinates = np.asarray(region.bounding_box)
        if coordinates.shape != (4,):
            raise ValueError("Candidate-frame OCR region must use a four-coordinate bounding box.")
        regions.append(VisualOCRRegion(
            source_index=source_index,
            text=region.text,
            confidence=float(region.confidence),
            bounding_box=tuple(float(value) for value in coordinates),
        ))

    reference = VisualEvidenceReference(
        source_reference=source_reference,
        checkpoint_path=None if checkpoint_path is None else str(checkpoint_path),
        slide_number=slide_number,
        build_index=build_index,
        frame_number=frame.frame_number,
        timestamp=frame.timestamp,
        image_width=authoritative_image.width,
        image_height=authoritative_image.height,
        authoritative_image_sha256=authoritative_image.sha256,
        submitted_image_sha256=image.sha256,
        submitted_image_width=image.width,
        submitted_image_height=image.height,
        image_transport_revision=(
            LOCAL_VISUAL_IMAGE_TRANSPORT_REVISION
            if image.sha256 != authoritative_image.sha256 else None
        ),
    )
    return ProjectedVisualEvidence(
        reference=reference,
        image_bytes=image.png_bytes,
        image_media_type=image.media_type,
        ocr_text=frame.formatted_text,
        ocr_regions=tuple(regions),
    )
