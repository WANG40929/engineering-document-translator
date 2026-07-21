from __future__ import annotations

import math
import os
import time
from pathlib import Path

import fitz

from ..models import FileResult, ProgressCallback, TranslationOptions
from ..text_utils import is_translatable, normalize_text
from .base import TranslationEngine


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
                lineheight=1.0,
            )
            if spare >= -0.05:
                shape.commit(overlay=True)
                return True, candidate_size
            if attempted_floor:
                break
            candidate_size = max(floor, candidate_size * 0.94)
        return False, candidate_size

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
            if progress:
                progress(str(source), 0.0, f"已分析 PDF：{total_pages} 页，共 {total_units} 个文字段落")
            for page_index in range(total_pages):
                page = document[page_index]
                lines = page_lines[page_index]
                if not lines:
                    result.skipped_pages.append(page_index + 1)
                    result.skipped_units += 1
                    if progress:
                        fraction = completed_units / max(total_units, 1) if total_units else (page_index + 1) / max(total_pages, 1)
                        progress(str(source), fraction, f"第 {page_index + 1}/{total_pages} 页无文字层，已保留原样")
                    continue
                if progress:
                    progress(
                        str(source),
                        completed_units / max(total_units, 1),
                        f"正在翻译 PDF 第 {page_index + 1}/{total_pages} 页（本页 {len(lines)} 段）",
                    )

                def batch_progress(done, pending_total):
                    if not progress or not pending_total:
                        return
                    page_fraction = min(1.0, done / max(pending_total, 1))
                    units = completed_units + round(len(lines) * page_fraction)
                    progress(
                        str(source),
                        units / max(total_units, 1),
                        f"正在翻译 PDF 第 {page_index + 1}/{total_pages} 页 · 本页批次 {done}/{pending_total}",
                    )

                try:
                    translations = translator.translate_many([line["text"] for line in lines], progress=batch_progress)
                except Exception as exc:
                    raise RuntimeError(
                        f"PDF 第 {page_index + 1}/{total_pages} 页翻译失败（已完成 {completed_units}/{total_units} 段）：{exc}"
                    ) from exc
                for line in lines:
                    page.add_redact_annot(line["rect"], fill=False, cross_out=False)
                page.apply_redactions(images=0, graphics=0, text=0)
                for line, translated in zip(lines, translations):
                    inserted, used_size = self._insert_fitted(page, line, translated, options.minimum_pdf_font_size)
                    if not inserted:
                        result.warnings.append(f"第 {page_index + 1} 页文字框空间不足：{line['text'][:60]}")
                    elif used_size < options.minimum_pdf_font_size:
                        result.warnings.append(f"第 {page_index + 1} 页译文字号缩小至 {used_size:.1f} pt：{line['text'][:60]}")
                    result.translated_units += 1
                completed_units += len(lines)
                if progress:
                    progress(
                        str(source),
                        completed_units / max(total_units, 1),
                        f"已完成 PDF 第 {page_index + 1}/{total_pages} 页 · {completed_units}/{total_units} 段",
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
