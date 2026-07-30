from __future__ import annotations

import os
import re
import tempfile
from dataclasses import replace
from pathlib import Path

import fitz

from ..models import FileResult, ProgressCallback, TranslationOptions
from ..text_utils import is_translatable, normalize_text
from .pdf_engine import PdfEngine, _rgb, _rotation


STANDALONE_BULLET_RE = re.compile(
    r"^[\uf000-\uf8ff\u2022\u25aa\u25cf\u25c6\u25cb\u25a1\u25a0\u2666\-]\s*$"
)
INLINE_BULLET_RE = re.compile(
    r"^[\uf000-\uf8ff\u2022\u25aa\u25cf\u25c6\u25cb\u25a1\u25a0\u2666]\s*"
)


def _containing_region(
    rect: fitz.Rect,
    regions: list[fitz.Rect],
) -> fitz.Rect | None:
    center = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
    matches = [region for region in regions if region.contains(center)]
    return min(matches, key=lambda region: region.get_area()) if matches else None


def _aligned_bullet(rect: fitz.Rect, bullets: list[fitz.Rect]) -> bool:
    center_y = (rect.y0 + rect.y1) / 2
    return any(
        bullet.x1 <= rect.x0 + 4.0
        and rect.x0 - bullet.x1 <= 32.0
        and abs((bullet.y0 + bullet.y1) / 2 - center_y)
        <= max(rect.height, bullet.height) * 0.7
        for bullet in bullets
    )


class _PagewiseTranslator:
    """Delegate API calls while preventing cross-page aggregate recovery."""

    supports_parallel_batches = False

    def __init__(self, translator):
        self._translator = translator

    def __getattr__(self, name):
        return getattr(self._translator, name)

    def translate_many(self, texts, progress=None):
        return self._translator.translate_many(texts, progress=progress)


class AdaptivePdfEngine(PdfEngine):
    """Preserve tables and fixed regions while grouping wrapped body prose."""

    def _page_lines(self, page) -> list[dict]:
        try:
            table_regions: list[fitz.Rect] = []
            for table in page.find_tables().tables:
                # Cell rectangles must precede the outer table rectangle so
                # _containing_region selects the smallest valid boundary.
                # Treating the whole table as one region allowed translated
                # text to run through adjacent columns.
                table_regions.extend(
                    fitz.Rect(cell)
                    for cell in table.cells
                    if cell is not None
                )
                table_regions.append(fitz.Rect(table.bbox))
        except Exception:
            table_regions = []

        data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
        bullets: list[fitz.Rect] = []
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = normalize_text(
                    "".join(span.get("text", "") for span in line.get("spans", []))
                )
                if text and STANDALONE_BULLET_RE.match(text):
                    bullets.append(fitz.Rect(line["bbox"]))

        atoms: list[dict] = []
        for block_index, block in enumerate(data.get("blocks", [])):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                raw_text = normalize_text(
                    "".join(span.get("text", "") for span in spans)
                )
                if not raw_text or STANDALONE_BULLET_RE.match(raw_text):
                    continue

                inline_bullet = bool(INLINE_BULLET_RE.match(raw_text))
                text = INLINE_BULLET_RE.sub("", raw_text, count=1).lstrip()
                if not is_translatable(text):
                    continue
                translatable_spans = [
                    span
                    for span in spans
                    if is_translatable(normalize_text(span.get("text", "")))
                ]
                dominant = max(
                    translatable_spans or spans,
                    key=lambda span: len(span.get("text", "")),
                )
                original_rect = fitz.Rect(line["bbox"])
                rect = fitz.Rect(original_rect)
                redact_rect = fitz.Rect(original_rect)
                if translatable_spans:
                    first_span = translatable_spans[0]
                    first_rect = fitz.Rect(first_span["bbox"])
                    # Section numbers are sometimes vector glyphs or separate
                    # non-translatable spans. Start at the first actual title
                    # glyph so the number remains untouched.
                    rect.x0 = max(rect.x0, first_rect.x0)
                    redact_rect.x0 = max(redact_rect.x0, first_rect.x0)
                    if str(first_span.get("text", "")).startswith((" ", "\t")):
                        rect.x0 = min(
                            rect.x1,
                            rect.x0 + float(dominant.get("size", 9)) * 0.85,
                        )
                    elif not inline_bullet and first_rect.x0 - original_rect.x0 > 4.0:
                        rect.x0 = min(rect.x1, rect.x0 + 2.5)
                if (
                    inline_bullet
                    and translatable_spans
                    and INLINE_BULLET_RE.match(
                        normalize_text(translatable_spans[0].get("text", ""))
                    )
                ):
                    redact_rect.x0 = min(
                        redact_rect.x1,
                        redact_rect.x0 + min(18.0, dominant.get("size", 9) * 1.6),
                    )
                    rect.x0 = min(rect.x1, rect.x0 + min(18.0, dominant.get("size", 9) * 1.6))
                if rect.is_empty or rect.width < 0.5 or rect.height < 0.5:
                    continue

                flags = int(dominant.get("flags", 0))
                container_rect = _containing_region(rect, table_regions)
                atoms.append(
                    {
                        "text": text,
                        "rect": rect,
                        "redact_rect": redact_rect,
                        "size": float(dominant.get("size", 9)),
                        "color": _rgb(dominant.get("color", 0)),
                        "rotate": _rotation(line.get("dir")),
                        "align": 0,
                        "block": block_index,
                        "bold": bool(flags & fitz.TEXT_FONT_BOLD),
                        "table": container_rect is not None,
                        "container_rect": container_rect,
                        "header": (
                            rect.y0
                            < page.cropbox.y0 + page.cropbox.height * 0.10
                        ),
                        "starts_bullet": inline_bullet or _aligned_bullet(rect, bullets),
                        "strip_generated_bullet": True,
                    }
                )

        groups: list[dict] = []
        for atom in atoms:
            if not groups:
                groups.append(atom)
                continue
            previous = groups[-1]
            previous_rect = fitz.Rect(previous["rect"])
            rect = fitz.Rect(atom["rect"])
            vertical_gap = rect.y0 - previous_rect.y1
            same_indent = abs(rect.x0 - previous_rect.x0) <= 5.0
            indented_continuation = (
                rect.x0 > previous_rect.x0
                and rect.x0 - previous_rect.x0 <= 30.0
            )
            close_vertically = -1.0 <= vertical_gap <= max(
                10.0,
                min(previous_rect.height, rect.height) * 0.90,
            )
            similar_size = abs(atom["size"] - previous["size"]) <= max(
                0.8,
                previous["size"] * 0.15,
            )
            can_merge = (
                not atom["header"]
                and not previous["header"]
                and atom["color"] == previous["color"]
                and atom["table"] == previous["table"]
                and atom.get("container_rect") == previous.get("container_rect")
                and not atom["starts_bullet"]
                and atom["rotate"] == previous["rotate"] == 0
                and close_vertically
                and similar_size
                and atom["bold"] == previous["bold"]
                and (same_indent or indented_continuation)
            )
            if can_merge:
                previous["text"] = normalize_text(
                    f"{previous['text']} {atom['text']}"
                )
                previous["rect"] = previous_rect | rect
                previous["redact_rect"] = (
                    fitz.Rect(previous["redact_rect"])
                    | fitz.Rect(atom["redact_rect"])
                )
                previous["size"] = max(previous["size"], atom["size"])
            else:
                groups.append(atom)

        visual_rects = [fitz.Rect(item["rect"]) for item in groups]
        page_right = page.cropbox.x1 - max(12.0, page.cropbox.width * 0.03)
        page_bottom = page.cropbox.y1 - max(12.0, page.cropbox.height * 0.02)
        for item in groups:
            rect = fitz.Rect(item["rect"])
            if item["rotate"] not in (0, 180):
                item["fit_rect"] = rect
                continue
            right = page_right
            container_rect = item.get("container_rect")
            if container_rect is not None:
                right = min(right, fitz.Rect(container_rect).x1 - 3.0)
            for other in visual_rects:
                if other.x0 < rect.x1 + 1.0:
                    continue
                vertical_overlap = min(rect.y1, other.y1) - max(rect.y0, other.y0)
                if vertical_overlap >= min(rect.height, other.height) * 0.35:
                    right = min(right, other.x0 - 4.0)
            right = max(rect.x1, right)
            bottom = page_bottom
            if container_rect is not None:
                bottom = min(
                    bottom,
                    fitz.Rect(container_rect).y1 - 2.0,
                )
            for other in visual_rects:
                if other.y0 < rect.y1 - 0.5:
                    continue
                horizontal_overlap = min(right, other.x1) - max(rect.x0, other.x0)
                if horizontal_overlap >= 2.0:
                    bottom = min(bottom, other.y0 - 1.0)
            bottom = max(rect.y1, bottom)
            item["fit_rect"] = fitz.Rect(rect.x0, rect.y0, right, bottom)
        return groups


def _save_rewritten(document: fitz.Document, destination: Path) -> None:
    temporary = destination.with_name(f".{destination.name}.udt-repair.pdf")
    if temporary.exists():
        temporary.unlink()
    try:
        document.save(temporary, garbage=3, deflate=True, clean=False)
        # Windows does not allow replacing a file while the source document
        # still holds an open handle to it.
        document.close()
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def replace_pdf_pages(
    translated_path: Path,
    repaired_path: Path,
    page_numbers: list[int],
) -> None:
    translated = fitz.open(translated_path)
    repaired = fitz.open(repaired_path)
    try:
        if repaired.page_count != len(page_numbers):
            raise ValueError(
                f"Repair page count mismatch: {repaired.page_count} != {len(page_numbers)}"
            )
        for repair_index, page_number in enumerate(page_numbers):
            page = translated[page_number - 1]
            page.add_redact_annot(page.rect, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions(images=2, graphics=2, text=0)
            page.show_pdf_page(
                page.rect,
                repaired,
                repair_index,
                keep_proportion=False,
                overlay=True,
            )
        _save_rewritten(translated, translated_path)
    finally:
        repaired.close()
        if not translated.is_closed:
            translated.close()


def rebuild_dual_pages(
    dual_path: Path,
    source_path: Path,
    repaired_mono_path: Path,
    page_numbers: list[int],
) -> None:
    dual = fitz.open(dual_path)
    source = fitz.open(source_path)
    mono = fitz.open(repaired_mono_path)
    try:
        for page_number in page_numbers:
            page = dual[page_number - 1]
            rect = page.rect
            page.add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
            page.apply_redactions(images=2, graphics=2, text=0)
            if rect.width >= rect.height:
                midpoint = rect.x0 + rect.width / 2
                source_rect = fitz.Rect(rect.x0, rect.y0, midpoint, rect.y1)
                translated_rect = fitz.Rect(midpoint, rect.y0, rect.x1, rect.y1)
            else:
                midpoint = rect.y0 + rect.height / 2
                source_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, midpoint)
                translated_rect = fitz.Rect(rect.x0, midpoint, rect.x1, rect.y1)
            page.show_pdf_page(
                source_rect,
                source,
                page_number - 1,
                keep_proportion=True,
                overlay=True,
            )
            page.show_pdf_page(
                translated_rect,
                mono,
                page_number - 1,
                keep_proportion=True,
                overlay=True,
            )
        _save_rewritten(dual, dual_path)
    finally:
        mono.close()
        source.close()
        if not dual.is_closed:
            dual.close()


def repair_pdf_pages(
    source_path: Path,
    translated_path: Path,
    page_numbers: list[int],
    translator,
    options: TranslationOptions,
    progress: ProgressCallback | None = None,
) -> FileResult:
    ordered_pages = sorted(set(page_numbers))
    if not ordered_pages:
        return FileResult(
            input_path=str(source_path),
            output_path=str(translated_path),
            status="completed",
            engine="PDF adaptive repair",
        )

    with tempfile.TemporaryDirectory(prefix="udt_pdf_repair_") as temporary_value:
        temporary = Path(temporary_value)
        selected_source = temporary / "selected-source.pdf"
        selected_output = temporary / "selected-output.pdf"
        source = fitz.open(source_path)
        selected = fitz.open()
        try:
            for page_number in ordered_pages:
                if page_number < 1 or page_number > source.page_count:
                    raise ValueError(f"Invalid repair page: {page_number}")
                selected.insert_pdf(
                    source,
                    from_page=page_number - 1,
                    to_page=page_number - 1,
                )
            selected.save(selected_source, garbage=3, deflate=True)
        finally:
            selected.close()
            source.close()

        strict_options = replace(
            options,
            minimum_pdf_font_size=max(5.5, options.minimum_pdf_font_size),
            pdf_mode="strict",
            pdf_output="mono",
        )
        pagewise_translator = _PagewiseTranslator(translator)
        result = AdaptivePdfEngine().translate(
            selected_source,
            selected_output,
            pagewise_translator,
            strict_options,
            progress,
        )
        if result.status != "completed":
            return result
        if result.skipped_units:
            # Never replace the smart-layout page with a repair that already
            # lost one or more text groups. The previous implementation still
            # marked this situation completed and made the output worse.
            result.status = "failed"
            result.errors.append(
                "; ".join(result.warnings)
                or f"{result.skipped_units} repair text groups did not fit"
            )
            return result
        replace_pdf_pages(translated_path, selected_output, ordered_pages)
        result.input_path = str(source_path)
        result.output_path = str(translated_path)
        result.engine = "PDF adaptive repair"
        return result


__all__ = [
    "AdaptivePdfEngine",
    "rebuild_dual_pages",
    "repair_pdf_pages",
    "replace_pdf_pages",
]
