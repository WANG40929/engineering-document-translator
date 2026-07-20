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
        data = page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = normalize_text("".join(span.get("text", "") for span in spans))
                if not spans or not is_translatable(text):
                    continue
                rect = fitz.Rect(line["bbox"])
                if rect.is_empty or rect.width < 0.5 or rect.height < 0.5:
                    continue
                dominant = max(spans, key=lambda span: len(span.get("text", "")))
                rotation = _rotation(line.get("dir"))
                if rotation in (0, 180):
                    page_midpoint = page.cropbox.width / 2
                    line_midpoint = rect.x0 + rect.width / 2
                    centered = abs(line_midpoint - page_midpoint) <= page.cropbox.width * 0.04
                else:
                    page_midpoint = page.cropbox.height / 2
                    line_midpoint = rect.y0 + rect.height / 2
                    centered = abs(line_midpoint - page_midpoint) <= page.cropbox.height * 0.04
                lines.append(
                    {
                        "text": text,
                        "rect": rect,
                        "size": float(dominant.get("size", 9)),
                        "color": _rgb(dominant.get("color", 0)),
                        "rotate": rotation,
                        "align": 1 if centered else 0,
                    }
                )
        return lines

    def _insert_fitted(self, page, line: dict, text: str, minimum: float) -> tuple[bool, float]:
        rect = fitz.Rect(line["rect"])
        rotation = line["rotate"]
        flow_length = rect.width if rotation in (0, 180) else rect.height
        cross_length = rect.height if rotation in (0, 180) else rect.width
        unit_length = max(self.font.text_length(text, fontsize=1), 0.01)
        size_by_length = flow_length * 0.96 / unit_length
        size_by_height = cross_length * 0.88
        size = max(1.2, min(line["size"], size_by_length, size_by_height))
        # Unicode fonts can have taller ascenders than the source font. The
        # original implementation tried only once, so a failed title insert
        # left an empty redaction box. Build an uncommitted shape first and
        # progressively reduce the size until the text really fits.
        margin = min(2.5, max(0.8, cross_length * 0.18))
        if rotation in (0, 180):
            rect.y0 -= margin; rect.y1 += margin
        else:
            rect.x0 -= margin; rect.x1 += margin
        candidate_size = size
        while candidate_size >= 1.2:
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
            candidate_size *= 0.88
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
