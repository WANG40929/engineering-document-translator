from __future__ import annotations

import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

import fitz
from PIL import Image, ImageChops, ImageOps


QUALITY_BANDS = 30
MINIMUM_READABLE_FONT = 5.5
INTERNAL_PLACEHOLDER_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:_{1,2}\s*)?UDT\s*_?\s*\d{4}(?:\s*_{1,2})?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class PageQualityIssue:
    page: int
    score: float
    reasons: tuple[str, ...]
    hidden_characters: int
    internal_placeholder_hits: int
    replacement_character_hits: int
    characters_under_5_5pt: int
    minimum_font_size: float | None
    vertical_distribution_change: float
    vertical_spread_loss: float
    text_block_ratio: float

    def to_dict(self) -> dict:
        value = asdict(self)
        value["reasons"] = list(self.reasons)
        return value


@dataclass(frozen=True, slots=True)
class PdfQualityReport:
    page_count: int
    issues: tuple[PageQualityIssue, ...]
    elapsed_seconds: float

    @property
    def repair_pages(self) -> list[int]:
        return [issue.page for issue in self.issues]

    def to_dict(self) -> dict:
        return {
            "page_count": self.page_count,
            "flagged_count": len(self.issues),
            "flagged_pages": [issue.to_dict() for issue in self.issues],
            "elapsed_seconds": self.elapsed_seconds,
        }


@dataclass(slots=True)
class _PageProfile:
    histogram: list[float]
    text_characters: int
    line_count: int
    block_count: int
    minimum_font_size: float | None
    characters_under_5_5pt: int
    maximum_band_share: float
    centroid: float
    spread: float
    hidden_characters: int = 0
    internal_placeholder_hits: int = 0
    replacement_character_hits: int = 0


def _rgb_from_int(value: int) -> tuple[int, int, int]:
    return (value >> 16) & 255, (value >> 8) & 255, value & 255


def _coverage(histogram: list[int], upper: int) -> float:
    total = sum(histogram)
    return sum(histogram[:upper]) / total if total else 0.0


def _span_is_hidden(
    raster: Image.Image,
    page_rect: fitz.Rect,
    span: dict,
    scale: float,
) -> bool:
    rect = fitz.Rect(span["bbox"]) & page_rect
    if rect.is_empty:
        return False
    x0 = max(0, min(raster.width, int((rect.x0 - page_rect.x0) * scale)))
    y0 = max(0, min(raster.height, int((rect.y0 - page_rect.y0) * scale)))
    x1 = max(0, min(raster.width, int((rect.x1 - page_rect.x0) * scale + 1)))
    y1 = max(0, min(raster.height, int((rect.y1 - page_rect.y0) * scale + 1)))
    if x1 <= x0 or y1 <= y0:
        return False

    crop = raster.crop((x0, y0, x1, y1))
    text_color = _rgb_from_int(int(span.get("color", 0)))
    solid = Image.new("RGB", crop.size, text_color)
    difference = ImageChops.difference(crop, solid).convert("L")
    color_coverage = _coverage(difference.histogram(), 60)
    dark_coverage = _coverage(ImageOps.grayscale(crop).histogram(), 215)
    # A glyph may be clipped by the smart engine while remaining in the PDF
    # text layer. Requiring both tests avoids treating white text on a colored
    # notice bar as hidden.
    return color_coverage < 0.004 and dark_coverage < 0.004


def _page_profile(
    page: fitz.Page,
    *,
    inspect_visibility: bool,
    render_scale: float,
) -> _PageProfile:
    page_rect = page.rect
    height = max(page_rect.height, 1.0)
    histogram = [0.0] * QUALITY_BANDS
    sizes: list[tuple[float, int]] = []
    text_characters = 0
    line_count = 0
    block_count = 0
    y_values: list[tuple[float, int]] = []
    hidden_characters = 0
    internal_placeholder_hits = 0
    replacement_character_hits = 0

    data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
    raster = None
    if inspect_visibility:
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(render_scale, render_scale),
            colorspace=fitz.csRGB,
            alpha=False,
        )
        raster = Image.frombytes(
            "RGB",
            (pixmap.width, pixmap.height),
            pixmap.samples,
        )

    for block in data.get("blocks", []):
        if block.get("type") != 0:
            continue
        block_used = False
        for line in block.get("lines", []):
            line_used = False
            for span in line.get("spans", []):
                raw_text = str(span.get("text", ""))
                internal_placeholder_hits += len(
                    INTERNAL_PLACEHOLDER_RE.findall(raw_text)
                )
                replacement_character_hits += raw_text.count("\ufffd")
                compact = "".join(
                    character
                    for character in raw_text
                    if not character.isspace()
                )
                if not compact:
                    continue
                count = len(compact)
                rect = fitz.Rect(span["bbox"])
                y_center = (rect.y0 + rect.y1) / 2.0
                band = max(
                    0,
                    min(
                        QUALITY_BANDS - 1,
                        int((y_center - page_rect.y0) / height * QUALITY_BANDS),
                    ),
                )
                histogram[band] += count
                size = float(span.get("size", 0.0))
                sizes.append((size, count))
                text_characters += count
                y_values.append((y_center, count))
                line_used = True
                block_used = True
                if (
                    raster is not None
                    and count >= 2
                    and _span_is_hidden(raster, page_rect, span, render_scale)
                ):
                    hidden_characters += count
            if line_used:
                line_count += 1
        if block_used:
            block_count += 1

    total = sum(histogram)
    normalized = [value / total for value in histogram] if total else histogram
    size_values = [size for size, _count in sizes]
    weighted_y_total = sum(y * count for y, count in y_values)
    weighted_y_count = sum(count for _y, count in y_values)
    used_y = [y for y, _count in y_values]
    return _PageProfile(
        histogram=normalized,
        text_characters=text_characters,
        line_count=line_count,
        block_count=block_count,
        minimum_font_size=min(size_values) if size_values else None,
        characters_under_5_5pt=sum(
            count for size, count in sizes if size < MINIMUM_READABLE_FONT
        ),
        maximum_band_share=max(normalized, default=0.0),
        centroid=(
            (weighted_y_total / weighted_y_count - page_rect.y0) / height
            if weighted_y_count
            else 0.0
        ),
        spread=(
            (max(used_y) - min(used_y)) / height if len(used_y) > 1 else 0.0
        ),
        hidden_characters=hidden_characters,
        internal_placeholder_hits=internal_placeholder_hits,
        replacement_character_hits=replacement_character_hits,
    )


def _compare_profiles(
    source: _PageProfile,
    translated: _PageProfile,
    page_number: int,
) -> PageQualityIssue | None:
    distribution_change = sum(
        abs(left - right)
        for left, right in zip(source.histogram, translated.histogram)
    ) / 2.0
    concentration_gain = max(
        0.0,
        translated.maximum_band_share - source.maximum_band_share,
    )
    spread_loss = max(0.0, source.spread - translated.spread)
    centroid_shift = abs(source.centroid - translated.centroid)
    block_ratio = translated.block_count / max(source.block_count, 1)
    line_ratio = translated.line_count / max(source.line_count, 1)
    font_penalty = (
        max(0.0, MINIMUM_READABLE_FONT - translated.minimum_font_size)
        / MINIMUM_READABLE_FONT
        if translated.minimum_font_size is not None
        else 0.0
    )
    score = (
        distribution_change * 3.0
        + concentration_gain * 4.0
        + spread_loss * 3.0
        + centroid_shift * 2.0
        + abs(math.log(max(block_ratio, 0.05))) * 0.45
        + abs(math.log(max(line_ratio, 0.05))) * 0.25
        + font_penalty * 3.0
        + min(translated.characters_under_5_5pt / 100.0, 2.0)
        + min(translated.hidden_characters / 12.0, 4.0)
        + min(translated.internal_placeholder_hits * 2.0, 6.0)
        + min(translated.replacement_character_hits * 2.0, 6.0)
    )

    reasons: list[str] = []
    if translated.hidden_characters >= 20:
        reasons.append("rendered_text_hidden_or_clipped")
    if translated.internal_placeholder_hits:
        reasons.append("internal_placeholder_leak")
    if translated.replacement_character_hits:
        reasons.append("unicode_replacement_character")
    if translated.characters_under_5_5pt >= 20:
        reasons.append("font_below_readability_floor")
    # Moderate distribution changes are normal when Chinese needs fewer lines
    # than the source language. Treat only a dramatic redistribution as an
    # independent defect; clipping, tiny text, collapse, and merged blocks
    # remain separate stronger signals below.
    if distribution_change >= 0.70:
        reasons.append("vertical_text_distribution_changed")
    if spread_loss >= 0.35:
        reasons.append("content_collapsed_vertically")
    if block_ratio <= 0.30 and source.block_count >= 8:
        reasons.append("text_blocks_merged")
    if not reasons:
        return None

    return PageQualityIssue(
        page=page_number,
        score=round(score, 4),
        reasons=tuple(reasons),
        hidden_characters=translated.hidden_characters,
        internal_placeholder_hits=translated.internal_placeholder_hits,
        replacement_character_hits=translated.replacement_character_hits,
        characters_under_5_5pt=translated.characters_under_5_5pt,
        minimum_font_size=(
            round(translated.minimum_font_size, 3)
            if translated.minimum_font_size is not None
            else None
        ),
        vertical_distribution_change=round(distribution_change, 4),
        vertical_spread_loss=round(spread_loss, 4),
        text_block_ratio=round(block_ratio, 4),
    )


def analyze_pdf_quality(
    source_path: Path,
    translated_path: Path,
    progress: Callable[[int, int], None] | None = None,
    *,
    render_scale: float = 2.0,
) -> PdfQualityReport:
    started = time.monotonic()
    source = fitz.open(source_path)
    translated = fitz.open(translated_path)
    try:
        if source.page_count != translated.page_count:
            raise ValueError(
                f"PDF page count mismatch: {source.page_count} != {translated.page_count}"
            )
        issues: list[PageQualityIssue] = []
        total = source.page_count
        for page_index in range(total):
            source_profile = _page_profile(
                source[page_index],
                inspect_visibility=False,
                render_scale=render_scale,
            )
            translated_profile = _page_profile(
                translated[page_index],
                inspect_visibility=True,
                render_scale=render_scale,
            )
            issue = _compare_profiles(
                source_profile,
                translated_profile,
                page_index + 1,
            )
            if issue is not None:
                issues.append(issue)
            if progress:
                progress(page_index + 1, total)
        return PdfQualityReport(
            page_count=total,
            issues=tuple(issues),
            elapsed_seconds=round(time.monotonic() - started, 2),
        )
    finally:
        source.close()
        translated.close()


__all__ = [
    "MINIMUM_READABLE_FONT",
    "PageQualityIssue",
    "PdfQualityReport",
    "analyze_pdf_quality",
]
