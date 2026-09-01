"""Deterministic visual-analysis triage from preserved frame/OCR evidence."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re

import numpy as np

from image_utils import calculate_frame_difference
from models import CandidateFrame, Presentation, Slide
from visual_evidence import ProjectedVisualEvidence, project_candidate_frame_evidence
from visual_understanding_contract import VisualDetectionSignal


DETECTOR_REVISION = "visual-candidate-v1"
DENSE_TEXT_MINIMUM_REGIONS = 5
DENSE_TEXT_MINIMUM_COVERAGE = 0.30
SPARSE_TEXT_MAXIMUM_REGIONS = 2
SPARSE_TEXT_MAXIMUM_COVERAGE = 0.08
LARGE_NON_TEXT_MAXIMUM_COVERAGE = 0.35
NUMERIC_LABEL_MINIMUM = 3
NUMERIC_DISPERSION_MINIMUM = 0.25
HIGH_EDGE_DENSITY_MINIMUM = 0.08
REPEATED_LINEAR_STRUCTURE_MINIMUM = 4
TEXT_DOMINANT_MAXIMUM_EDGE_DENSITY = 0.04
MATERIAL_VISUAL_DIFFERENCE_THRESHOLD = 10.0

_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?%?")
_PERCENTAGE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?%")
_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_ISOLATED_NUMERIC_LABEL = re.compile(
    r"\s*[+-]?(?:\d+(?:[.,]\d+)?%?|(?:19|20)\d{2})(?:\s+[+-]?(?:\d+(?:[.,]\d+)?%?|(?:19|20)\d{2}))*\s*"
)


class VisualCandidateDisposition(Enum):
    """Conservative triage disposition, never a semantic visual judgment."""

    RECOMMENDED = "recommended"
    TEXT_DOMINANT = "text_dominant"
    UNCERTAIN = "uncertain"


class VisualSelectionScope(Enum):
    """Future-GUI-compatible deterministic selection scopes."""

    RECOMMENDED = "recommended"
    ALL_SLIDES = "all_slides"
    USER_SELECTED = "user_selected"


@dataclass(frozen=True)
class VisualCandidateAssessment:
    """Observable frame triage with no content type or calibrated confidence."""

    disposition: VisualCandidateDisposition
    reasons: tuple[str, ...]
    signals: tuple[VisualDetectionSignal, ...]
    detector_revision: str = DETECTOR_REVISION
    explanation: str = ""

    @property
    def analyzable(self) -> bool:
        """Uncertain frames remain eligible; only default text-dominant triage omits."""

        return self.disposition is not VisualCandidateDisposition.TEXT_DOMINANT


@dataclass(frozen=True)
class VisualAnalysisTarget:
    """One detached exact-frame evidence candidate in stable presentation order."""

    evidence: ProjectedVisualEvidence
    assessment: VisualCandidateAssessment

    @property
    def slide_number(self) -> int:
        return self.evidence.reference.slide_number

    @property
    def build_index(self) -> int | None:
        return self.evidence.reference.build_index

    @property
    def frame_number(self) -> int:
        return self.evidence.reference.frame_number


def _validated_image(frame: CandidateFrame) -> np.ndarray:
    image = frame.image
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8 or image.size == 0:
        raise ValueError("Visual candidate detection requires a non-empty uint8 CandidateFrame image.")
    if image.ndim not in (2, 3) or (image.ndim == 3 and image.shape[2] not in (1, 3, 4)):
        raise ValueError("Visual candidate detection requires grayscale, BGR, or BGRA image data.")
    return image


def _ocr_geometry(frame: CandidateFrame, width: int, height: int):
    mask = np.zeros((height, width), dtype=np.uint8)
    centers: list[tuple[float, float]] = []
    usable_regions = []
    for region in frame.ocr_results:
        coordinates = np.asarray(region.bounding_box)
        if coordinates.shape != (4,):
            continue
        left, top, right, bottom = (float(value) for value in coordinates)
        if not np.isfinite((left, top, right, bottom)).all() or left > right or top > bottom:
            continue
        clipped_left = max(0, min(width, int(np.floor(left))))
        clipped_top = max(0, min(height, int(np.floor(top))))
        clipped_right = max(0, min(width, int(np.ceil(right))))
        clipped_bottom = max(0, min(height, int(np.ceil(bottom))))
        if clipped_right <= clipped_left or clipped_bottom <= clipped_top:
            continue
        mask[clipped_top:clipped_bottom, clipped_left:clipped_right] = 1
        centers.append(((left + right) / 2 / width, (top + bottom) / 2 / height))
        usable_regions.append(region)
    coverage = float(mask.mean())
    horizontal_span = max((value[0] for value in centers), default=0.0) - min(
        (value[0] for value in centers), default=0.0
    )
    vertical_span = max((value[1] for value in centers), default=0.0) - min(
        (value[1] for value in centers), default=0.0
    )
    return mask, tuple(centers), tuple(usable_regions), coverage, horizontal_span, vertical_span


def _non_text_geometry(image: np.ndarray, ocr_mask: np.ndarray) -> tuple[float, int, int, int]:
    import cv2

    if image.ndim == 2:
        gray = image.copy()
    elif image.shape[2] == 1:
        gray = image[:, :, 0].copy()
    elif image.shape[2] == 4:
        gray = cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    fill_value = int(np.median(gray))
    gray[ocr_mask.astype(bool)] = fill_value
    edges = cv2.Canny(gray, 80, 160)
    edge_count = int(np.count_nonzero(edges))
    edge_density = edge_count / edges.size
    minimum_length = max(12, round(min(gray.shape) * 0.18))
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(12, round(min(gray.shape) * 0.08)),
        minLineLength=minimum_length,
        maxLineGap=max(3, round(min(gray.shape) * 0.02)),
    )
    horizontal_or_vertical = 0
    if lines is not None:
        for line in lines[:, 0]:
            x1, y1, x2, y2 = (int(value) for value in line)
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dy <= max(2, round(dx * 0.12)) or dx <= max(2, round(dy * 0.12)):
                horizontal_or_vertical += 1
    return float(edge_density), edge_count, 0 if lines is None else len(lines), horizontal_or_vertical


def assess_visual_candidate(frame: CandidateFrame) -> VisualCandidateAssessment:
    """Assess observable evidence only; do not infer a semantic content type."""

    if not isinstance(frame, CandidateFrame):
        raise ValueError("frame must be a CandidateFrame.")
    image = _validated_image(frame)
    height, width = image.shape[:2]
    mask, centers, regions, coverage, horizontal_span, vertical_span = _ocr_geometry(
        frame, width, height
    )
    edge_density, edge_count, line_count, aligned_line_count = _non_text_geometry(image, mask)
    signals: list[VisualDetectionSignal] = [VisualDetectionSignal(
        "ocr_coverage",
        "OCR region geometry relative to the exact candidate frame.",
        {
            "region_count": len(regions),
            "coverage_ratio": coverage,
            "horizontal_center_span_ratio": horizontal_span,
            "vertical_center_span_ratio": vertical_span,
        },
        DETECTOR_REVISION,
    )]

    dense_text = len(regions) >= DENSE_TEXT_MINIMUM_REGIONS and coverage >= DENSE_TEXT_MINIMUM_COVERAGE
    sparse_text = len(regions) <= SPARSE_TEXT_MAXIMUM_REGIONS or coverage <= SPARSE_TEXT_MAXIMUM_COVERAGE
    large_non_text = coverage <= LARGE_NON_TEXT_MAXIMUM_COVERAGE
    if dense_text:
        signals.append(VisualDetectionSignal(
            "dense_text", "OCR regions cover a substantial portion of the frame.",
            {"region_count": len(regions), "coverage_ratio": coverage}, DETECTOR_REVISION,
        ))
    if sparse_text:
        signals.append(VisualDetectionSignal(
            "sparse_text", "Few OCR regions or limited OCR-covered area were observed.",
            {"region_count": len(regions), "coverage_ratio": coverage}, DETECTOR_REVISION,
        ))
    if large_non_text:
        signals.append(VisualDetectionSignal(
            "large_non_text_region", "Most frame pixels are outside OCR bounding boxes.",
            {"non_text_ratio": 1.0 - coverage}, DETECTOR_REVISION,
        ))

    numeric_regions = []
    percentage_count = 0
    year_count = 0
    for region, center in zip(regions, centers):
        tokens = _NUMBER.findall(region.text)
        if tokens and _ISOLATED_NUMERIC_LABEL.fullmatch(region.text):
            numeric_regions.append((region, center, tokens))
            percentage_count += len(_PERCENTAGE.findall(region.text))
            year_count += len(_YEAR.findall(region.text))
    numeric_horizontal_span = max((item[1][0] for item in numeric_regions), default=0.0) - min(
        (item[1][0] for item in numeric_regions), default=0.0
    )
    numeric_vertical_span = max((item[1][1] for item in numeric_regions), default=0.0) - min(
        (item[1][1] for item in numeric_regions), default=0.0
    )
    dispersed_numeric = (
        len(numeric_regions) >= NUMERIC_LABEL_MINIMUM
        and max(numeric_horizontal_span, numeric_vertical_span) >= NUMERIC_DISPERSION_MINIMUM
    )
    if dispersed_numeric:
        signals.append(VisualDetectionSignal(
            "dispersed_numeric_labels",
            "Multiple numeric OCR labels are distributed across the frame.",
            {
                "numeric_region_count": len(numeric_regions),
                "percentage_count": percentage_count,
                "year_count": year_count,
                "horizontal_center_span_ratio": numeric_horizontal_span,
                "vertical_center_span_ratio": numeric_vertical_span,
            },
            DETECTOR_REVISION,
        ))

    repeated_linear = aligned_line_count >= REPEATED_LINEAR_STRUCTURE_MINIMUM
    if repeated_linear:
        signals.append(VisualDetectionSignal(
            "repeated_linear_structure",
            "Repeated horizontal or vertical edge segments remain outside OCR regions.",
            {
                "detected_line_count": line_count,
                "aligned_line_count": aligned_line_count,
            },
            DETECTOR_REVISION,
        ))
    high_edge_density = edge_density >= HIGH_EDGE_DENSITY_MINIMUM
    if high_edge_density:
        signals.append(VisualDetectionSignal(
            "high_edge_density",
            "Substantial edge structure remains outside OCR regions.",
            {"edge_density": edge_density, "edge_pixel_count": edge_count},
            DETECTOR_REVISION,
        ))

    structural = dispersed_numeric or repeated_linear
    if dense_text and not structural and edge_density <= TEXT_DOMINANT_MAXIMUM_EDGE_DENSITY:
        disposition = VisualCandidateDisposition.TEXT_DOMINANT
        reasons = ("dense_text_without_additional_structural_signals",)
        explanation = "Observable evidence is text-dominant; retain under all-slides or user-selected scope."
    elif structural or (large_non_text and high_edge_density):
        disposition = VisualCandidateDisposition.RECOMMENDED
        reasons = tuple(
            code for code, present in (
                ("dispersed_numeric_labels", dispersed_numeric),
                ("repeated_linear_structure", repeated_linear),
                ("large_non_text_with_high_edge_density", large_non_text and high_edge_density),
            ) if present
        )
        explanation = "Observable visual structure may not be represented by flattened OCR."
    else:
        disposition = VisualCandidateDisposition.UNCERTAIN
        reasons = ("insufficient_observable_evidence_for_text_dominant_or_structural_triage",)
        explanation = "Deterministic evidence is uncertain; retain as analyzable rather than excluding it."
    return VisualCandidateAssessment(
        disposition, reasons, tuple(signals), DETECTOR_REVISION, explanation
    )


def _frame_locations(slide: Slide) -> tuple[tuple[int, CandidateFrame], ...]:
    locations = []
    seen: set[int] = set()
    for build_index, build in enumerate(slide.builds):
        for frame in build.candidate_frames:
            identity = id(frame)
            if identity not in seen:
                locations.append((build_index, frame))
                seen.add(identity)
    return tuple(locations)


def _default_frames(slide: Slide) -> tuple[tuple[int, CandidateFrame], ...]:
    locations = _frame_locations(slide)
    if not locations:
        return ()
    primary = locations[-1]
    retained = [primary]
    for location in locations[:-1]:
        frame = location[1]
        if all(
            calculate_frame_difference(frame.image, retained_frame.image)
            >= MATERIAL_VISUAL_DIFFERENCE_THRESHOLD
            for _build, retained_frame in retained
        ):
            retained.append(location)
    return tuple(sorted(retained, key=lambda item: (item[0], item[1].frame_number)))


def select_visual_analysis_targets(
    presentation: Presentation,
    *,
    source_reference: str,
    checkpoint_path: str | Path | None = None,
    scope: VisualSelectionScope = VisualSelectionScope.RECOMMENDED,
    selected_slide_numbers: tuple[int, ...] = (),
    selected_frame_numbers: tuple[int, ...] = (),
) -> tuple[VisualAnalysisTarget, ...]:
    """Select detached targets ordered by slide, build, then frame number."""

    if not isinstance(presentation, Presentation):
        raise ValueError("presentation must be a Presentation.")
    if not isinstance(scope, VisualSelectionScope):
        raise ValueError("scope must be a VisualSelectionScope.")
    slide_filter, frame_filter = set(selected_slide_numbers), set(selected_frame_numbers)
    if scope is VisualSelectionScope.USER_SELECTED and not (slide_filter or frame_filter):
        raise ValueError("User-selected scope requires at least one slide or frame number.")

    targets: list[VisualAnalysisTarget] = []
    for slide in sorted(presentation.slides, key=lambda value: value.slide_number):
        locations = (
            tuple(
                location for location in _frame_locations(slide)
                if slide.slide_number in slide_filter or location[1].frame_number in frame_filter
            )
            if scope is VisualSelectionScope.USER_SELECTED
            else _default_frames(slide)
        )
        for build_index, frame in locations:
            assessment = assess_visual_candidate(frame)
            if scope is VisualSelectionScope.RECOMMENDED and not assessment.analyzable:
                continue
            evidence = project_candidate_frame_evidence(
                frame,
                source_reference=source_reference,
                checkpoint_path=checkpoint_path,
                slide_number=slide.slide_number,
                build_index=build_index,
            )
            targets.append(VisualAnalysisTarget(evidence, assessment))
    return tuple(sorted(
        targets,
        key=lambda target: (
            target.slide_number,
            -1 if target.build_index is None else target.build_index,
            target.frame_number,
        ),
    ))
