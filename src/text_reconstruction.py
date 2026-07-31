"""Deterministic geometry-based OCR line reconstruction."""

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from models import OCRResult, TextLine


STRONG_VERTICAL_OVERLAP = 0.65
CENTERLINE_TOLERANCE = 0.30
MIN_CENTERLINE_OVERLAP = 0.25
SMALL_DUPLICATE_MAX_CHARACTERS = 12
MIN_SMALL_REGION_OVERLAP = 0.20


@dataclass(frozen=True)
class NormalizedOCRRegion:
    """A read-only geometric representation of one OCR result."""

    source_index: int
    result: OCRResult
    left: float
    top: float
    right: float
    bottom: float
    center_y: float
    height: float


@dataclass(frozen=True)
class RegionLineAssignment:
    """Diagnostic metadata for a region's line placement or suppression."""

    source_index: int
    bounding_box: tuple[float, float, float, float]
    line_id: int | None
    within_line_position: int | None
    suppressed: bool
    suppression_reason: str | None = None


def vertical_overlap(region: OCRResult, top: float, bottom: float) -> float:
    """Return overlap as a fraction of the smaller vertical span."""

    overlap = min(region.bottom, bottom) - max(region.top, top)
    if overlap <= 0:
        return 0.0
    return overlap / min(region.bottom - region.top, bottom - top)


def _normalize_regions(ocr_results: Iterable[OCRResult]) -> list[NormalizedOCRRegion]:
    return [
        NormalizedOCRRegion(
            source_index=index,
            result=result,
            left=result.left,
            top=result.top,
            right=result.right,
            bottom=result.bottom,
            center_y=result.center_y,
            height=max(1.0, result.bottom - result.top),
        )
        for index, result in enumerate(ocr_results, start=1)
    ]


def _belongs_to_line(region: NormalizedOCRRegion, line: list[NormalizedOCRRegion], median_height: float) -> bool:
    line_top = min(item.top for item in line)
    line_bottom = max(item.bottom for item in line)
    overlap = vertical_overlap(region.result, line_top, line_bottom)
    line_center = median(item.center_y for item in line)
    center_distance = abs(region.center_y - line_center)
    return overlap >= STRONG_VERTICAL_OVERLAP or (
        overlap >= MIN_CENTERLINE_OVERLAP
        and center_distance <= median_height * CENTERLINE_TOLERANCE
    )


def group_regions_into_lines(ocr_results: list[OCRResult]) -> list[list[NormalizedOCRRegion]]:
    """Group visual lines using y geometry, independent of OCR return order."""

    regions = _normalize_regions(ocr_results)
    if not regions:
        return []
    median_height = median(region.height for region in regions)
    regions.sort(key=lambda item: (item.center_y, item.top, item.left, item.source_index))
    lines: list[list[NormalizedOCRRegion]] = []
    for region in regions:
        matches = [line for line in lines if _belongs_to_line(region, line, median_height)]
        if matches:
            # The nearest compatible centerline resolves unusually tall overlap.
            selected = min(matches, key=lambda line: (abs(region.center_y - median(item.center_y for item in line)), min(item.left for item in line)))
            selected.append(region)
        else:
            lines.append([region])
    return lines


def order_regions_within_line(regions: list[NormalizedOCRRegion]) -> list[NormalizedOCRRegion]:
    """Return left-to-right geometry ordering with stable tie-breaking."""

    return sorted(regions, key=lambda item: (item.left, item.center_y, item.source_index))


def _normalized_tokens(text: str) -> list[str]:
    return [token for token in " ".join(text.lower().split()).split(" ") if token]


def _overlap_fraction(smaller: NormalizedOCRRegion, larger: NormalizedOCRRegion) -> float:
    width = max(0.0, min(smaller.right, larger.right) - max(smaller.left, larger.left))
    height = max(0.0, min(smaller.bottom, larger.bottom) - max(smaller.top, larger.top))
    return (width * height) / max(1.0, (smaller.right - smaller.left) * (smaller.bottom - smaller.top))


def _overlapping_text_edges(smaller: NormalizedOCRRegion, larger: NormalizedOCRRegion) -> tuple[bool, bool]:
    """Return whether the smaller region overlaps the larger left/right edge."""

    larger_width = max(1.0, larger.right - larger.left)
    edge_tolerance = larger_width * 0.25
    return (
        smaller.right <= larger.left + edge_tolerance,
        smaller.left >= larger.right - edge_tolerance,
    )


def detect_overlapping_duplicate_regions(regions: list[NormalizedOCRRegion]) -> tuple[set[int], dict[int, str]]:
    """Suppress only small, geometrically overlapping token duplicates."""

    suppressed: set[int] = set()
    reasons: dict[int, str] = {}
    for smaller in regions:
        small_text = " ".join(smaller.result.text.lower().split())
        if not small_text or len(small_text) > SMALL_DUPLICATE_MAX_CHARACTERS:
            continue
        for larger in regions:
            if smaller is larger:
                continue
            small_area = (smaller.right - smaller.left) * (smaller.bottom - smaller.top)
            large_area = (larger.right - larger.left) * (larger.bottom - larger.top)
            if small_area >= large_area or _overlap_fraction(smaller, larger) < MIN_SMALL_REGION_OVERLAP:
                continue
            large_text = " ".join(larger.result.text.lower().split())
            overlaps_left, overlaps_right = _overlapping_text_edges(smaller, larger)
            is_prefix_duplicate = overlaps_left and (
                large_text == small_text or large_text.startswith(small_text + " ")
            )
            is_suffix_duplicate = overlaps_right and (
                large_text == small_text or large_text.endswith(" " + small_text)
            )
            if is_prefix_duplicate or is_suffix_duplicate:
                suppressed.add(smaller.source_index)
                reasons[smaller.source_index] = (
                    "small overlapping region duplicates the "
                    + ("prefix" if is_prefix_duplicate else "suffix")
                    + " of a larger region"
                )
                break
    return suppressed, reasons


def _shared_boundary_length(left_text: str, right_text: str) -> int:
    """Return the longest case-insensitive suffix/prefix character overlap."""

    maximum = min(len(left_text), len(right_text))
    for length in range(maximum, 0, -1):
        if left_text[-length:].casefold() == right_text[:length].casefold():
            return length
    return 0


def _stitch_overlapping_boundary(
    left: NormalizedOCRRegion,
    right: NormalizedOCRRegion,
) -> str | None:
    """Return one conservative merge for adjacent overlapping OCR regions.

    OCR sometimes emits two regions that share one or more characters at their
    physical boundary.  Only a positive horizontal overlap permits stitching;
    ordinary adjacent words retain their normal separating space.  The special
    one-uppercase-character case joins a split leading capital such as
    ``A`` + ``ctivating`` without inventing any character.
    """

    left_text = left.result.text.strip()
    right_text = right.result.text.strip()

    if not left_text or not right_text or right.left >= left.right:
        return None

    shared_length = _shared_boundary_length(left_text, right_text)
    if shared_length:
        # Remove only characters that are already present on both sides.
        return left_text[:-shared_length] + right_text

    if (
        len(left_text) == 1
        and left_text.isupper()
        and right_text[0].islower()
    ):
        return left_text + right_text

    return None


def _join_region_text(regions: list[NormalizedOCRRegion]) -> str:
    text = ""
    previous_region: NormalizedOCRRegion | None = None
    previous_fragment = ""

    for region in regions:
        fragment = region.result.text.strip()
        if not fragment:
            continue
        if not text:
            text = fragment
        elif previous_region is not None:
            stitched = _stitch_overlapping_boundary(previous_region, region)
            if stitched is not None:
                # The previous raw fragment is the current text suffix.
                text = text[:-len(previous_fragment)] + stitched
            elif fragment[0] in ".,;:!?)]}" or text[-1] in "([{":
                text += fragment
            else:
                text += " " + fragment
        previous_region = region
        previous_fragment = fragment
    return text


def reconstruct_lines_with_metadata(ocr_results: list[OCRResult]) -> tuple[list[TextLine], list[RegionLineAssignment]]:
    """Build top-to-bottom lines and diagnostics without mutating OCR results."""

    grouped = group_regions_into_lines(ocr_results)
    grouped.sort(key=lambda line: (median(item.center_y for item in line), median(item.top for item in line), min(item.left for item in line), min(item.source_index for item in line)))
    reconstructed: list[TextLine] = []
    assignments: list[RegionLineAssignment] = []
    for line_id, group in enumerate(grouped, start=1):
        ordered = order_regions_within_line(group)
        suppressed, reasons = detect_overlapping_duplicate_regions(ordered)
        visible = [region for region in ordered if region.source_index not in suppressed]
        for position, region in enumerate(ordered, start=1):
            assignments.append(RegionLineAssignment(
                source_index=region.source_index,
                bounding_box=(region.left, region.top, region.right, region.bottom),
                line_id=line_id,
                within_line_position=position,
                suppressed=region.source_index in suppressed,
                suppression_reason=reasons.get(region.source_index),
            ))
        if not visible:
            continue
        reconstructed.append(TextLine(
            text=_join_region_text(visible),
            top=min(region.top for region in visible),
            bottom=max(region.bottom for region in visible),
            left=min(region.left for region in visible),
            right=max(region.right for region in visible),
            confidence=sum(region.result.confidence for region in visible) / len(visible),
        ))
    assignments.sort(key=lambda item: item.source_index)
    return reconstructed, assignments


def reconstruct_lines(ocr_results: list[OCRResult]) -> list[TextLine]:
    """Compatibility entry point returning reconstructed lines only."""

    return reconstruct_lines_with_metadata(ocr_results)[0]
