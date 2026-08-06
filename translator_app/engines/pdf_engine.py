from __future__ import annotations

import math
import os
import re
import time
from pathlib import Path

import fitz

from ..i18n import tr
from ..models import FileResult, ProgressCallback, TranslationOptions
from ..text_utils import is_translatable, normalize_text
from .base import TranslationEngine


GENERATED_BULLET_RE = re.compile(
    r"^\s*(?:[\uf000-\uf8ff\u2022\u25aa\u25cf\u25c6\u25cb\u25a1\u25a0\u2666]|-\s+)\s*"
)
PRIVATE_USE_RE = re.compile(r"[\uf000-\uf8ff]")
SECTION_NUMBER_JOIN_RE = re.compile(r"^(\d+(?:\.\d+)+)(?=[^\d\s.])")
LEADING_LATIN_FRAGMENT_RE = re.compile(
    r"^([A-Za-z]{1,3})\s*(?=[\u3400-\u9fff])"
)
SOURCE_LATIN_WORD_RE = re.compile(r"^[A-Za-z]+")
INTERNAL_SEGMENT_MARKER_RE = re.compile(
    r"\[\s*\[\s*UDT\s*[_\s-]*SEGMENT\s*[_\s-]*\d{4}\s*\]\s*\]",
    re.IGNORECASE,
)


def _rotation(direction) -> int:
    if not direction:
        return 0
    angle = math.degrees(math.atan2(-direction[1], direction[0])) % 360
    return min((0, 90, 180, 270), key=lambda value: abs(((angle - value + 180) % 360) - 180))


def _rgb(color: int):
    return fitz.sRGB_to_pdf(color) if isinstance(color, int) else (0, 0, 0)


class PdfEngine(TranslationEngine):
    extensions = (".pdf",)

    def __init__(self):
        candidates = [
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "ARIALUNI.ttf",
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "simhei.ttf",
        ]
        self.font_path = next((path for path in candidates if path.exists()), None)
        self.font = fitz.Font(fontfile=str(self.font_path)) if self.font_path else fitz.Font(fontname="china-ss")
        self.font_name = "UDTUnicode" if self.font_path else "china-ss"

    def _page_lines(self, page) -> list[dict]:
        lines: list[dict] = []
        visual_rects: list[fitz.Rect] = []
        data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = normalize_text("".join(span.get("text", "") for span in spans))
                if not spans:
                    continue
                rect = fitz.Rect(line["bbox"])
                if rect.is_empty or rect.width < 0.5 or rect.height < 0.5:
                    continue
                visual_rects.append(rect)
                if not is_translatable(text):
                    continue
                dominant = max(spans, key=lambda span: len(span.get("text", "")))
                rotation = _rotation(line.get("dir"))
                lines.append(
                    {
                        "text": text,
                        "rect": rect,
                        "size": float(dominant.get("size", 9)),
                        "color": _rgb(dominant.get("color", 0)),
                        "rotate": rotation,
                        # A PDF text layer stores glyph coordinates, not the
                        # paragraph alignment used by the source application.
                        # Inferring centering from the line midpoint moved long
                        # body lines when a shorter translation was inserted.
                        # Anchor every translation to the original glyph box.
                        "align": 0,
                    }
                )
        # The glyph bbox is often only as wide as the source words. Reusing
        # that narrow box forces longer translations (especially Chinese page
        # labels) down to tiny font sizes. Keep the original top-left anchor,
        # but extend the fitting area through adjacent whitespace. Nearby text
        # on the same row or below remains a hard boundary.
        page_right = page.cropbox.x1 - max(12.0, page.cropbox.width * 0.03)
        page_bottom = page.cropbox.y1 - max(12.0, page.cropbox.height * 0.02)
        for item in lines:
            rect = fitz.Rect(item["rect"])
            if item["rotate"] not in (0, 180):
                item["fit_rect"] = rect
                continue
            right = page_right
            for other in visual_rects:
                if other.x0 < rect.x1 + 1.0:
                    continue
                vertical_overlap = min(rect.y1, other.y1) - max(rect.y0, other.y0)
                if vertical_overlap >= min(rect.height, other.height) * 0.45:
                    right = min(right, other.x0 - 4.0)
            right = max(rect.x1, right)
            bottom = page_bottom
            for other in visual_rects:
                if other.y0 < rect.y1 - 0.5:
                    continue
                horizontal_overlap = min(right, other.x1) - max(rect.x0, other.x0)
                if horizontal_overlap >= 2.0:
                    bottom = min(bottom, other.y0 - 1.0)
            bottom = max(rect.y1, bottom)
            item["fit_rect"] = fitz.Rect(rect.x0, rect.y0, right, bottom)
        return lines

    def _insert_fitted(self, page, line: dict, text: str, minimum: float) -> tuple[bool, float]:
        source_rect = fitz.Rect(line["rect"])
        rect = fitz.Rect(line.get("fit_rect", source_rect))
        rotation = line["rotate"]
        cross_length = source_rect.height if rotation in (0, 180) else source_rect.width
        size = max(1.2, line["size"])
        # Unicode fonts can have taller ascenders than the source font. The
        # original implementation tried only once, so a failed title insert
        # left an empty redaction box. Build an uncommitted shape first and
        # progressively reduce the size until the text really fits.
        margin = min(2.5, max(0.8, cross_length * 0.18))
        if rotation in (0, 180):
            rect.y1 += margin * 2
        else:
            rect.x1 += margin * 2
        floor = max(1.2, min(float(minimum), size))
        candidate_size = size
        attempted_floor = False
        while candidate_size >= floor - 0.01:
            if candidate_size < floor:
                candidate_size = floor
            attempted_floor = abs(candidate_size - floor) < 0.01
            shape = page.new_shape()
            spare = shape.insert_textbox(
                rect,
                text,
                align=line.get("align", 0),
                fontname=self.font_name,
                fontfile=str(self.font_path) if self.font_path else None,
                fontsize=candidate_size,
                color=line["color"],
                rotate=rotation,
                # The bundled CJK font has a taller visible glyph box than
                # Latin fonts at the same point size. A 1.0 baseline step can
                # therefore make wrapped Chinese lines visibly overlap even
                # when insert_textbox reports success.
                lineheight=float(line.get("lineheight", 1.25)),
            )
            if spare >= -0.05:
                shape.commit(overlay=True)
                return True, candidate_size
            if attempted_floor:
                break
            candidate_size = max(floor, candidate_size * 0.94)
        return False, candidate_size

    @staticmethod
    def _clean_translation(line: dict, translated: str) -> str:
        text = str(translated).strip().replace("\u2011", "-")
        # Segment identity markers belong only to the API wire format. Cache
        # validation evicts polluted entries, but strip them here as a final
        # safety net so no backend or legacy cache can print one into a PDF.
        text = INTERNAL_SEGMENT_MARKER_RE.sub("", text)
        # Private-use glyphs in source PDFs are normally symbol-font bullets.
        # They must never leak into a Unicode translation font as empty boxes.
        text = PRIVATE_USE_RE.sub("", text)
        if line.get("strip_generated_bullet"):
            text = GENERATED_BULLET_RE.sub("", text, count=1)
        fragment = LEADING_LATIN_FRAGMENT_RE.match(text)
        source_word = SOURCE_LATIN_WORD_RE.match(str(line.get("text", "")))
        if fragment and source_word:
            value = fragment.group(1)
            if (
                source_word.group(0).casefold().startswith(value.casefold())
                and (len(value) == 1 or not value.isupper())
            ):
                text = text[len(value) :].lstrip()
        # Models occasionally join a protected section number directly to the
        # translated heading. Restore the visible separator deterministically.
        text = SECTION_NUMBER_JOIN_RE.sub(r"\1 ", text, count=1)
        return text.strip()

    def _apply_page_translations(
        self,
        page,
        page_index: int,
        lines: list[dict],
        translations: list[str],
        options: TranslationOptions,
        result: FileResult,
    ) -> None:
        for line in lines:
            page.add_redact_annot(
                line.get("redact_rect", line["rect"]),
                fill=False,
                cross_out=False,
            )
        page.apply_redactions(images=0, graphics=0, text=0)
        for line, translated in zip(lines, translations):
            translated = self._clean_translation(line, translated)
            inserted, used_size = self._insert_fitted(
                page,
                line,
                translated,
                options.minimum_pdf_font_size,
            )
            if not inserted:
                # A readable original label is safer than either an empty
                # redaction box or an illegible 2–3 pt translation. This is
                # particularly important for narrow engineering-table cells
                # containing units, coating codes and product specifications.
                source_text = self._clean_translation(line, line["text"])
                source_inserted, _source_size = self._insert_fitted(
                    page,
                    line,
                    source_text,
                    options.minimum_pdf_font_size,
                )
                if source_inserted:
                    result.warnings.append(
                        tr(
                            "warning.pdf_source_preserved",
                            page=page_index + 1,
                            text=line["text"][:60],
                        )
                    )
                else:
                    result.skipped_units += 1
                    if page_index + 1 not in result.skipped_pages:
                        result.skipped_pages.append(page_index + 1)
                    result.warnings.append(
                        tr(
                            "warning.pdf_text_overflow",
                            page=page_index + 1,
                            text=line["text"][:60],
                        )
                    )
            elif used_size < options.minimum_pdf_font_size:
                result.warnings.append(
                    tr(
                        "warning.pdf_font_reduced",
                        page=page_index + 1,
                        size=used_size,
                        text=line["text"][:60],
                    )
                )
            result.translated_units += 1

    def _translate_aggregated(
        self,
        source: Path,
        document,
        page_lines: list[list[dict]],
        translator,
        options: TranslationOptions,
        progress: ProgressCallback | None,
        result: FileResult,
    ) -> None:
        """Translate all text together, falling back by page on any failure."""
        total_pages = len(page_lines)
        total_units = sum(len(lines) for lines in page_lines)
        last_fraction = 0.05

        def emit(fraction: float, message: str) -> None:
            nonlocal last_fraction
            last_fraction = max(last_fraction, min(0.99, float(fraction)))
            if progress:
                progress(str(source), last_fraction, message)

        for page_index, lines in enumerate(page_lines):
            if not lines:
                result.skipped_pages.append(page_index + 1)
                result.skipped_units += 1
        emit(
            0.05,
            tr("progress.pdf_analyzed", pages=total_pages, segments=total_units),
        )
        if not total_units:
            for page_index in range(total_pages):
                emit(
                    0.90 + 0.08 * ((page_index + 1) / max(total_pages, 1)),
                    tr(
                        "progress.pdf_no_text",
                        current=page_index + 1,
                        total=total_pages,
                    ),
                )
            emit(0.99, tr("progress.pdf_save"))
            return

        flat_texts = [
            line["text"]
            for lines in page_lines
            for line in lines
        ]

        def aggregate_progress(done: int, pending_total: int) -> None:
            if pending_total <= 0:
                return
            translated_ratio = min(1.0, done / pending_total)
            emit(
                0.05 + 0.75 * translated_ratio,
                tr(
                    "progress.pdf_translating_document",
                    done=done,
                    total=pending_total,
                    pages=total_pages,
                    segments=total_units,
                ),
            )

        try:
            flat_translations = translator.translate_many(
                flat_texts,
                progress=aggregate_progress,
            )
            if len(flat_translations) != len(flat_texts):
                raise RuntimeError(
                    tr(
                        "error.pdf_document_count",
                        actual=len(flat_translations),
                        expected=len(flat_texts),
                    )
                )
        except Exception as aggregate_error:
            # DeepSeekTranslator checkpoints every successful batch. Retrying
            # page-by-page therefore reads completed text from cache and sends
            # only the unresolved part, while restoring exact page diagnostics.
            emit(
                last_fraction,
                tr("progress.pdf_batch_recovering"),
            )
            translations_by_page: list[list[str]] = [[] for _ in page_lines]
            verified_units = 0
            for page_index, lines in enumerate(page_lines):
                if not lines:
                    continue

                def page_progress(done: int, pending_total: int) -> None:
                    if pending_total <= 0:
                        return
                    page_ratio = min(1.0, done / pending_total)
                    candidate_units = verified_units + round(len(lines) * page_ratio)
                    emit(
                        0.05 + 0.75 * (candidate_units / max(total_units, 1)),
                        tr(
                            "progress.pdf_recovering_page",
                            current=page_index + 1,
                            pages=total_pages,
                            done=done,
                            total=pending_total,
                        ),
                    )

                try:
                    page_translations = translator.translate_many(
                        [line["text"] for line in lines],
                        progress=page_progress,
                    )
                    if len(page_translations) != len(lines):
                        raise RuntimeError(
                            tr(
                                "error.pdf_page_count",
                                actual=len(page_translations),
                                expected=len(lines),
                            )
                        )
                except Exception as page_error:
                    raise RuntimeError(
                        tr(
                            "error.pdf_page_failed",
                            current=page_index + 1,
                            total=total_pages,
                            done=verified_units,
                            segments=total_units,
                            reason=page_error,
                        )
                    ) from page_error
                translations_by_page[page_index] = list(page_translations)
                verified_units += len(lines)
                emit(
                    0.05 + 0.75 * (verified_units / max(total_units, 1)),
                    tr(
                        "progress.pdf_page_recovered",
                        current=page_index + 1,
                        pages=total_pages,
                        done=verified_units,
                        total=total_units,
                    ),
                )
            flat_translations = [
                translated
                for translations in translations_by_page
                for translated in translations
            ]
            if len(flat_translations) != len(flat_texts):
                raise RuntimeError(tr("error.pdf_recovery_incomplete")) from aggregate_error

        emit(
            0.80,
            tr(
                "progress.pdf_translation_ready",
                pages=total_pages,
                segments=total_units,
            ),
        )
        translation_offset = 0
        applied_units = 0
        for page_index, lines in enumerate(page_lines):
            if not lines:
                emit(
                    0.80 + 0.18 * (applied_units / max(total_units, 1)),
                    tr(
                        "progress.pdf_no_text",
                        current=page_index + 1,
                        total=total_pages,
                    ),
                )
                continue
            page_translations = flat_translations[
                translation_offset : translation_offset + len(lines)
            ]
            translation_offset += len(lines)
            self._apply_page_translations(
                document[page_index],
                page_index,
                lines,
                page_translations,
                options,
                result,
            )
            applied_units += len(lines)
            emit(
                0.80 + 0.18 * (applied_units / max(total_units, 1)),
                tr(
                    "progress.pdf_writing_page",
                    current=page_index + 1,
                    pages=total_pages,
                    done=applied_units,
                    total=total_units,
                ),
            )
        emit(0.99, tr("progress.pdf_finalize"))

    def translate(self, source, destination, translator, options, progress=None) -> FileResult:
        started = time.monotonic()
        result = FileResult(str(source), str(destination), engine="PDF text layer")
        document = fitz.open(source)
        try:
            total_pages = document.page_count
            # Scan first so progress reflects actual text work instead of
            # treating a seven-line drawing and an eighty-line page equally.
            page_lines = [self._page_lines(document[index]) for index in range(total_pages)]
            total_units = sum(len(lines) for lines in page_lines)
            completed_units = 0
            if getattr(translator, "supports_parallel_batches", False):
                self._translate_aggregated(
                    source,
                    document,
                    page_lines,
                    translator,
                    options,
                    progress,
                    result,
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                document.subset_fonts()
                document.save(destination, garbage=3, deflate=True, clean=False)
                result.status = "completed"
                if progress:
                    progress(str(source), 1.0, tr("progress.pdf_generated_strict"))
                return result
            if progress:
                progress(
                    str(source),
                    0.0,
                    tr(
                        "progress.pdf_analyzed",
                        pages=total_pages,
                        segments=total_units,
                    ),
                )
            for page_index in range(total_pages):
                page = document[page_index]
                lines = page_lines[page_index]
                if not lines:
                    result.skipped_pages.append(page_index + 1)
                    result.skipped_units += 1
                    if progress:
                        fraction = completed_units / max(total_units, 1) if total_units else (page_index + 1) / max(total_pages, 1)
                        progress(
                            str(source),
                            fraction,
                            tr(
                                "progress.pdf_no_text",
                                current=page_index + 1,
                                total=total_pages,
                            ),
                        )
                    continue
                if progress:
                    progress(
                        str(source),
                        completed_units / max(total_units, 1),
                        tr(
                            "progress.pdf_translating_page",
                            current=page_index + 1,
                            total=total_pages,
                            segments=len(lines),
                        ),
                    )

                def batch_progress(done, pending_total):
                    if not progress or not pending_total:
                        return
                    page_fraction = min(1.0, done / max(pending_total, 1))
                    units = completed_units + round(len(lines) * page_fraction)
                    progress(
                        str(source),
                        units / max(total_units, 1),
                        tr(
                            "progress.pdf_translating_batch",
                            current=page_index + 1,
                            total=total_pages,
                            done=done,
                            total_batches=pending_total,
                        ),
                    )

                try:
                    translations = translator.translate_many([line["text"] for line in lines], progress=batch_progress)
                except Exception as exc:
                    raise RuntimeError(
                        tr(
                            "error.pdf_page_failed",
                            current=page_index + 1,
                            total=total_pages,
                            done=completed_units,
                            segments=total_units,
                            reason=exc,
                        )
                    ) from exc
                self._apply_page_translations(
                    page,
                    page_index,
                    lines,
                    translations,
                    options,
                    result,
                )
                completed_units += len(lines)
                if progress:
                    progress(
                        str(source),
                        completed_units / max(total_units, 1),
                        tr(
                            "progress.pdf_page_complete",
                            current=page_index + 1,
                            total=total_pages,
                            done=completed_units,
                            segments=total_units,
                        ),
                    )
            destination.parent.mkdir(parents=True, exist_ok=True)
            document.subset_fonts()
            document.save(destination, garbage=3, deflate=True, clean=False)
            result.status = "completed"
        except Exception as exc:
            result.status = "failed"
            result.errors.append(str(exc))
            if destination.exists():
                destination.unlink()
        finally:
            document.close()
            result.elapsed_seconds = round(time.monotonic() - started, 2)
            result.usage = dict(getattr(translator, "usage", {}))
        return result
