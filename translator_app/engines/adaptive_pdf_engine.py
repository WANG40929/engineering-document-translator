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


def _matching_bullet_rect(
    rect: fitz.Rect,
    bullets: list[fitz.Rect],
) -> fitz.Rect | None:
    center_y = (rect.y0 + rect.y1) / 2
    return next(
        (
            bullet
            for bullet in bullets
            if bullet.x1 <= rect.x0 + 4.0
            and rect.x0 - bullet.x1 <= 32.0
            and abs((bullet.y0 + bullet.y1) / 2 - center_y)
            <= max(rect.height, bullet.height) * 0.7
        ),
        None,
    )


def _uses_table_cell_boundaries(table) -> bool:
    """Reject sparse pseudo-tables formed by notice icons and text rows."""

    rows = int(getattr(table, "row_count", 0) or 0)
    columns = int(getattr(table, "col_count", 0) or 0)
    if rows <= 0 or columns < 2:
        return False
    populated = sum(cell is not None for cell in getattr(table, "cells", ()))
    return populated / max(rows * columns, 1) >= 0.65


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

    @staticmethod
    def _same_application_flow(previous: dict, current: dict) -> bool:
        previous_rect = fitz.Rect(previous["rect"])
        current_rect = fitz.Rect(current["rect"])
        return (
            previous.get("block") == current.get("block")
            and previous.get("block") is not None
            and not previous.get("header")
            and not current.get("header")
            and previous.get("color") == current.get("color")
            and previous.get("rotate") == current.get("rotate") == 0
            and previous.get("table") == current.get("table")
            and previous.get("container_rect") == current.get("container_rect")
            and current_rect.y0 >= previous_rect.y0 + 0.5
            and current_rect.y0 - previous_rect.y1
            <= max(12.0, previous_rect.height, current_rect.height)
        )

    def _coalesce_application_lines(
        self,
        lines: list[dict],
        translations: list[str],
    ) -> tuple[list[dict], list[str]]:
        """Share vertical space between structured runs from one source block.

        Some PDF producers store a warning-box list and its following
        paragraphs in one text block. Keeping every logical item in its own
        narrow source-height rectangle forces each item down to 5.5pt even
        though the complete block has enough room. Translation remains
        segment-based for cache quality; only final insertion is flowed.
        """

        rendered_lines: list[dict] = []
        rendered_translations: list[str] = []
        index = 0
        while index < len(lines):
            end = index + 1
            while end < len(lines) and self._same_application_flow(
                lines[end - 1],
                lines[end],
            ):
                end += 1
            run_lines = lines[index:end]
            run_translations = translations[index:end]
            if len(run_lines) == 1:
                rendered_lines.append(run_lines[0])
                rendered_translations.append(run_translations[0])
                index = end
                continue

            base_x = min(fitz.Rect(line["rect"]).x0 for line in run_lines)
            source_rect = fitz.Rect(run_lines[0]["rect"])
            redact_rect = fitz.Rect(
                run_lines[0].get("redact_rect", run_lines[0]["rect"])
            )
            fit_rect = fitz.Rect(
                run_lines[0].get("fit_rect", run_lines[0]["rect"])
            )
            prepared_parts: list[tuple[dict, str, int]] = []
            for line, translated in zip(
                run_lines,
                run_translations,
                strict=True,
            ):
                line_rect = fitz.Rect(line["rect"])
                source_rect |= line_rect
                redact_rect |= fitz.Rect(
                    line.get("redact_rect", line["rect"])
                )
                line_fit = fitz.Rect(line.get("fit_rect", line["rect"]))
                fit_rect.x1 = max(fit_rect.x1, line_fit.x1)
                fit_rect.y1 = max(fit_rect.y1, line_fit.y1)
                clean = self._clean_translation(line, translated)
                average_character_width = max(2.5, float(line["size"]) * 0.48)
                indent = min(
                    20,
                    max(
                        0,
                        round(
                            (line_rect.x0 - base_x)
                            / average_character_width
                        ),
                    ),
                )
                prepared_parts.append((line, clean, indent))

            prepared: list[str] = []
            for line, clean, indent in prepared_parts:
                raw_bullet_rect = line.get("bullet_rect")
                bullet_rect = (
                    fitz.Rect(raw_bullet_rect)
                    if raw_bullet_rect is not None
                    else None
                )
                # Standalone/inline source bullets normally remain outside
                # their own text redaction. A flowed block can widen that
                # redaction across a later bullet, though; redraw only bullets
                # that the combined rectangle actually erased. This avoids
                # the duplicate "• ◆" marker seen in notice-box lists.
                bullet_was_redacted = (
                    line.get("starts_bullet")
                    and (
                        bullet_rect is None
                        or redact_rect.contains(
                            fitz.Point(
                                (bullet_rect.x0 + bullet_rect.x1) / 2,
                                (bullet_rect.y0 + bullet_rect.y1) / 2,
                            )
                        )
                    )
                )
                bullet = "◆ " if bullet_was_redacted else ""
                prepared.append((" " * indent) + bullet + clean)

            combined = dict(run_lines[0])
            combined["text"] = "\n".join(
                str(line.get("text", ""))
                for line in run_lines
            )
            combined["rect"] = source_rect
            combined["redact_rect"] = redact_rect
            combined["fit_rect"] = fitz.Rect(
                base_x,
                source_rect.y0,
                fit_rect.x1,
                fit_rect.y1,
            )
            combined["size"] = max(
                float(line.get("size", 9))
                for line in run_lines
            )
            combined["strip_generated_bullet"] = False
            rendered_lines.append(combined)
            rendered_translations.append("\n".join(prepared))
            index = end
        return rendered_lines, rendered_translations

    def _apply_page_translations(
        self,
        page,
        page_index: int,
        lines: list[dict],
        translations: list[str],
        options: TranslationOptions,
        result: FileResult,
    ) -> None:
        rendered_lines, rendered_translations = (
            self._coalesce_application_lines(lines, translations)
        )
        super()._apply_page_translations(
            page,
            page_index,
            rendered_lines,
            rendered_translations,
            options,
            result,
        )

    def _page_lines(self, page) -> list[dict]:
        try:
            table_regions: list[fitz.Rect] = []
            for table in page.find_tables().tables:
                # Cell rectangles must precede the outer table rectangle for
                # genuine multi-column tables so _containing_region selects
                # the smallest valid boundary. Single-column safety/notice
                # boxes are frequently misdetected as one table row per text
                # line; treating those rows as cells forces every translation
                # down to a tiny font. Keep only their shared outer boundary.
                if _uses_table_cell_boundaries(table):
                    table_regions.extend(
                        fitz.Rect(cell)
                        for cell in table.cells
                        if cell is not None
                    )
                # Even a sparse notice grid provides a useful shared outer
                # boundary. Only its individual pseudo-cells are ignored.
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

                aligned_bullet_rect = _matching_bullet_rect(rect, bullets)
                if inline_bullet and redact_rect.x0 > original_rect.x0:
                    bullet_rect = fitz.Rect(
                        original_rect.x0,
                        original_rect.y0,
                        redact_rect.x0,
                        original_rect.y1,
                    )
                else:
                    bullet_rect = aligned_bullet_rect

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
                        "starts_bullet": inline_bullet or aligned_bullet_rect is not None,
                        "bullet_rect": bullet_rect,
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
                # A source paragraph can wrap across several lines inside one
                # PDF text block. Adjacent table-of-contents rows and list
                # entries are commonly stored as separate blocks even when
                # their geometry, font, and colour are identical. Crossing
                # that boundary collapses structured pages into one paragraph.
                and atom["block"] == previous["block"]
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
    *,
    repair_page_indices: list[int] | None = None,
) -> None:
    translated = fitz.open(translated_path)
    repaired = fitz.open(repaired_path)
    try:
        if repair_page_indices is None:
            repair_page_indices = list(range(len(page_numbers)))
            expected_page_count = len(page_numbers)
        else:
            expected_page_count = None
        if len(repair_page_indices) != len(page_numbers):
            raise ValueError(
                "Repair page mapping mismatch: "
                f"{len(repair_page_indices)} != {len(page_numbers)}"
            )
        if expected_page_count is not None and repaired.page_count != expected_page_count:
            raise ValueError(
                f"Repair page count mismatch: {repaired.page_count} != {expected_page_count}"
            )
        for repair_index, page_number in zip(
            repair_page_indices,
            page_numbers,
            strict=True,
        ):
            if repair_index < 0 or repair_index >= repaired.page_count:
                raise ValueError(f"Invalid repaired page index: {repair_index}")
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
        failed_repair_indices = {
            page_number - 1
            for page_number in result.skipped_pages
            if 1 <= page_number <= len(ordered_pages)
        }
        successful_entries = [
            (repair_index, original_page)
            for repair_index, original_page in enumerate(ordered_pages)
            if repair_index not in failed_repair_indices
        ]
        successful_pages = [page for _, page in successful_entries]
        failed_pages = [
            original_page
            for repair_index, original_page in enumerate(ordered_pages)
            if repair_index in failed_repair_indices
        ]
        result.usage = dict(result.usage)
        result.usage["repaired_pages"] = successful_pages
        result.usage["failed_pages"] = failed_pages
        result.skipped_pages = failed_pages
        if not successful_entries:
            # Never replace a smart-layout page with a repair that already
            # lost one or more text groups. Failure is now isolated per page,
            # so a bad page does not discard valid repairs from the same run.
            result.status = "failed"
            result.errors.append(
                "; ".join(result.warnings)
                or f"{result.skipped_units} repair text groups did not fit"
            )
            return result
        replace_pdf_pages(
            translated_path,
            selected_output,
            successful_pages,
            repair_page_indices=[
                repair_index for repair_index, _ in successful_entries
            ],
        )
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
