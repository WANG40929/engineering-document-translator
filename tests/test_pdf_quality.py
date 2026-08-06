from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from translator_app.deepseek import IdentityTranslator
from translator_app.engines.adaptive_pdf_engine import (
    AdaptivePdfEngine,
    _line_span_groups,
    _uses_table_cell_boundaries,
    rebuild_dual_pages,
    repair_pdf_pages,
    replace_pdf_pages,
)
from translator_app.engines.pdf_engine import PdfEngine
from translator_app.models import FileResult, TranslationOptions
from translator_app.pdf_quality import analyze_pdf_quality


def _write_lines(path: Path, positions: list[float], *, size: float = 11.0) -> None:
    document = fitz.open()
    page = document.new_page(width=400, height=500)
    for index, y in enumerate(positions):
        page.insert_text(
            (40, y),
            f"Safety instruction number {index + 1} must remain visible",
            fontsize=size,
        )
    document.save(path)
    document.close()


def _draw_dense_table(page: fitz.Page) -> None:
    left, top = 30.0, 30.0
    cell_width, cell_height = 85.0, 35.0
    rows, columns = 5, 5
    for row in range(rows + 1):
        y = top + row * cell_height
        page.draw_line(
            (left, y),
            (left + columns * cell_width, y),
            color=(0, 0, 0),
        )
    for column in range(columns + 1):
        x = left + column * cell_width
        page.draw_line(
            (x, top),
            (x, top + rows * cell_height),
            color=(0, 0, 0),
        )
    for row in range(rows):
        for column in range(columns):
            page.insert_text(
                (
                    left + column * cell_width + 4,
                    top + row * cell_height + 18,
                ),
                f"R{row + 1}C{column + 1}",
                fontsize=7,
            )


class PdfQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="udt_pdf_quality_")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_quality_scan_detects_collapsed_page(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        _write_lines(source, [50, 100, 150, 200, 250, 300, 350, 400])
        _write_lines(translated, [50, 62, 74, 86, 98, 110, 122, 134])

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertTrue(
            {
                "vertical_text_distribution_changed",
                "content_collapsed_vertically",
            }
            & set(report.issues[0].reasons)
        )

    def test_quality_scan_detects_invisible_text_layer(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        visible = "This safety instruction must remain visibly rendered."

        source_document = fitz.open()
        source_document.new_page(width=400, height=250).insert_text(
            (40, 100),
            visible,
            fontsize=11,
        )
        source_document.save(source)
        source_document.close()

        translated_document = fitz.open()
        translated_document.new_page(width=400, height=250).insert_text(
            (40, 100),
            visible,
            fontsize=11,
            render_mode=3,
        )
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=2.0)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("rendered_text_hidden_or_clipped", report.issues[0].reasons)

    def test_quality_scan_detects_partially_clipped_text_span(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        visible = "This notice contains enough text to expose partial clipping."

        source_document = fitz.open()
        source_document.new_page(width=500, height=250).insert_text(
            (40, 100),
            visible,
            fontsize=12,
        )
        source_document.save(source)
        source_document.close()

        translated_document = fitz.open()
        page = translated_document.new_page(width=500, height=250)
        page.insert_text((40, 100), visible, fontsize=12)
        page.draw_rect(
            fitz.Rect(185, 80, 500, 115),
            color=(1, 1, 1),
            fill=(1, 1, 1),
            overlay=True,
        )
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=2.0)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("rendered_text_hidden_or_clipped", report.issues[0].reasons)
        self.assertGreaterEqual(report.issues[0].hidden_characters, 8)

    def test_quality_scan_detects_bottom_half_clipped_text(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        visible = "Continuous lower-half clipping must be detected reliably"

        source_document = fitz.open()
        source_document.new_page(width=500, height=250).insert_text(
            (40, 100),
            visible,
            fontsize=12,
        )
        source_document.save(source)
        source_document.close()

        translated_document = fitz.open()
        page = translated_document.new_page(width=500, height=250)
        page.insert_text((40, 100), visible, fontsize=12)
        page.draw_rect(
            fitz.Rect(35, 92, 470, 112),
            color=(1, 1, 1),
            fill=(1, 1, 1),
            overlay=True,
        )
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=2.0)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("text_partially_clipped", report.issues[0].reasons)
        self.assertGreaterEqual(
            report.issues[0].partially_clipped_characters,
            4,
        )

    def test_quality_scan_detects_stray_latin_translation_fragments(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"

        source_document = fitz.open()
        source_document.new_page(width=500, height=250).insert_text(
            (40, 90),
            "Remove transportation locking and check all supplied parts",
            fontsize=11,
        )
        source_document.save(source)
        source_document.close()

        translated_document = fitz.open()
        page = translated_document.new_page(width=500, height=250)
        page.insert_text(
            (40, 90),
            "拆除运输锁定装置并检查全部随附零件是否完整且没有损坏",
            fontname="china-ss",
            fontsize=11,
        )
        page.insert_text((390, 115), "s", fontsize=11)
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("stray_latin_fragment", report.issues[0].reasons)
        self.assertEqual(report.issues[0].suspicious_latin_fragments, 1)

    def test_quality_scan_detects_new_overlapping_lines(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"

        source_document = fitz.open()
        page = source_document.new_page(width=500, height=250)
        page.insert_text((40, 80), "First safety instruction remains separate")
        page.insert_text((40, 130), "Second safety instruction remains separate")
        source_document.save(source)
        source_document.close()

        translated_document = fitz.open()
        page = translated_document.new_page(width=500, height=250)
        page.insert_text((40, 100), "First translated safety instruction")
        page.insert_text((110, 100), "Second translated safety instruction")
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("text_lines_overlapping", report.issues[0].reasons)
        self.assertGreaterEqual(report.issues[0].overlapping_text_pairs, 1)

    def test_quality_scan_does_not_repair_dense_table_for_bbox_overlap_only(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"

        source_document = fitz.open()
        _draw_dense_table(source_document.new_page(width=500, height=250))
        source_document.save(source)
        source_document.close()

        translated_document = fitz.open()
        page = translated_document.new_page(width=500, height=250)
        _draw_dense_table(page)
        page.insert_text((38, 52), "Translated table value one", fontsize=7)
        page.insert_text((90, 52), "Translated table value two", fontsize=7)
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertFalse(
            any(
                "text_lines_overlapping" in issue.reasons
                for issue in report.issues
            )
        )

    def test_quality_scan_detects_collapsed_structured_labels(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        _write_lines(
            source,
            [50, 85, 120, 155, 190, 225, 260, 295, 330, 365],
        )
        _write_lines(translated, [50, 85, 120, 155])

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("text_lines_collapsed", report.issues[0].reasons)
        self.assertLessEqual(report.issues[0].line_count_ratio, 0.58)

    def test_quality_scan_detects_unreadably_small_font(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        _write_lines(source, [100], size=11)
        _write_lines(translated, [100], size=3)

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("font_below_readability_floor", report.issues[0].reasons)

    def test_quality_scan_detects_internal_placeholder_leak(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        _write_lines(source, [100])

        translated_document = fitz.open()
        translated_document.new_page(width=400, height=500).insert_text(
            (40, 100),
            "Temperature __UDT_0000__ to __UDT_0001__",
            fontsize=11,
        )
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("internal_placeholder_leak", report.issues[0].reasons)
        self.assertEqual(report.issues[0].internal_placeholder_hits, 2)

    def test_quality_scan_detects_segment_identity_marker_leak(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        source_document = fitz.open()
        source_document.new_page(width=400, height=250).insert_text(
            (40, 80),
            "Safety requirements",
            fontsize=12,
        )
        source_document.save(source)
        source_document.close()
        translated_document = fitz.open()
        translated_document.new_page(width=400, height=250).insert_text(
            (40, 80),
            "[[UDT_SEGMENT_0003]] translated safety requirements",
            fontsize=12,
        )
        translated_document.save(translated)
        translated_document.close()

        report = analyze_pdf_quality(source, translated, render_scale=1.5)

        self.assertEqual(report.repair_pages, [1])
        self.assertIn("internal_placeholder_leak", report.issues[0].reasons)
        self.assertEqual(report.issues[0].internal_placeholder_hits, 1)

    def test_repaired_page_replaces_content_without_changing_page_count(self):
        target = self.root / "target.pdf"
        repaired = self.root / "repaired.pdf"

        target_document = fitz.open()
        target_document.new_page(width=300, height=200).insert_text(
            (30, 50), "Keep first page"
        )
        target_document.new_page(width=300, height=200).insert_text(
            (30, 50), "Broken second page"
        )
        target_document.save(target)
        target_document.close()

        repaired_document = fitz.open()
        repaired_document.new_page(width=300, height=200).insert_text(
            (30, 50), "Fixed second page"
        )
        repaired_document.save(repaired)
        repaired_document.close()

        replace_pdf_pages(target, repaired, [2])

        result = fitz.open(target)
        try:
            self.assertEqual(result.page_count, 2)
            self.assertIn("Keep first page", result[0].get_text())
            self.assertIn("Fixed second page", result[1].get_text())
            self.assertNotIn("Broken second page", result[1].get_text())
        finally:
            result.close()

    def test_adaptive_repair_translates_only_selected_pages(self):
        source = self.root / "source.pdf"
        translated = self.root / "translated.pdf"
        _write_lines(source, [60, 100, 140])

        original = fitz.open(source)
        duplicated = fitz.open()
        duplicated.insert_pdf(original)
        duplicated.new_page(width=400, height=500).insert_text(
            (40, 60), "Untouched second page"
        )
        duplicated.save(translated)
        duplicated.close()
        original.close()

        source_document = fitz.open(source)
        source_document.new_page(width=400, height=500).insert_text(
            (40, 60), "Second source page"
        )
        rewritten_source = self.root / "source-two-pages.pdf"
        source_document.save(rewritten_source)
        source_document.close()

        result = repair_pdf_pages(
            rewritten_source,
            translated,
            [1],
            IdentityTranslator(),
            TranslationOptions(target_language="zh"),
        )

        self.assertEqual(result.status, "completed", result.errors)
        repaired_document = fitz.open(translated)
        try:
            self.assertEqual(repaired_document.page_count, 2)
            self.assertIn("Safety instruction", repaired_document[0].get_text())
            self.assertIn("Untouched second page", repaired_document[1].get_text())
        finally:
            repaired_document.close()

    def test_adaptive_layout_does_not_merge_independent_text_blocks(self):
        source = self.root / "source.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=300)
        page.insert_text((50, 100), "NOTICE", fontsize=11, color=(1, 1, 1))
        page.insert_text(
            (50, 112),
            "Material damage can result from unsafe operation.",
            fontsize=11,
            color=(0, 0, 0),
        )
        document.save(source)
        document.close()

        document = fitz.open(source)
        try:
            groups = AdaptivePdfEngine()._page_lines(document[0])
        finally:
            document.close()

        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0]["text"], "NOTICE")
        self.assertTrue(groups[1]["text"].startswith("Material damage"))

    def test_adaptive_layout_keeps_adjacent_same_style_blocks_separate(self):
        source = self.root / "source.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=300)
        page.insert_text((50, 100), "First independent item", fontsize=11)
        page.insert_text((50, 112), "Second independent item", fontsize=11)
        document.save(source)
        document.close()

        document = fitz.open(source)
        try:
            groups = AdaptivePdfEngine()._page_lines(document[0])
        finally:
            document.close()

        self.assertEqual(
            [group["text"] for group in groups],
            ["First independent item", "Second independent item"],
        )

    def test_adaptive_application_flows_items_from_same_source_block(self):
        lines = [
            {
                "text": "First item",
                "rect": fitz.Rect(80, 100, 220, 115),
                "redact_rect": fitz.Rect(80, 100, 220, 115),
                "fit_rect": fitz.Rect(80, 100, 340, 125),
                "size": 10.0,
                "color": (0, 0, 0),
                "rotate": 0,
                "align": 0,
                "block": 7,
                "bold": False,
                "table": False,
                "container_rect": None,
                "header": False,
                "starts_bullet": True,
                "strip_generated_bullet": True,
            },
            {
                "text": "Indented continuation",
                "rect": fitz.Rect(110, 116, 260, 131),
                "redact_rect": fitz.Rect(110, 116, 260, 131),
                "fit_rect": fitz.Rect(110, 116, 340, 170),
                "size": 10.0,
                "color": (0, 0, 0),
                "rotate": 0,
                "align": 0,
                "block": 7,
                "bold": False,
                "table": False,
                "container_rect": None,
                "header": False,
                "starts_bullet": False,
                "strip_generated_bullet": True,
            },
        ]

        rendered_lines, rendered_translations = (
            AdaptivePdfEngine()._coalesce_application_lines(
                lines,
                ["第一项", "缩进续行"],
            )
        )

        self.assertEqual(len(rendered_lines), 1)
        self.assertIn("\n", rendered_translations[0])
        self.assertTrue(rendered_translations[0].startswith("◆ "))
        self.assertTrue(rendered_translations[0].splitlines()[1].startswith(" "))
        self.assertEqual(rendered_lines[0]["fit_rect"].y1, 170)
        self.assertEqual(rendered_lines[0]["lineheight"], 1.25)

    def test_adaptive_flow_keeps_heading_and_body_separate(self):
        heading = {
            "text": "Storage time in the warehouse",
            "rect": fitz.Rect(80, 100, 260, 115),
            "redact_rect": fitz.Rect(80, 100, 260, 115),
            "fit_rect": fitz.Rect(80, 100, 340, 125),
            "size": 12.0,
            "color": (0, 0, 0),
            "rotate": 0,
            "align": 0,
            "block": 7,
            "bold": True,
            "table": False,
            "container_rect": None,
            "header": False,
            "starts_bullet": False,
            "strip_generated_bullet": True,
        }
        body = dict(heading)
        body.update(
            {
                "text": "The expected life increases up to five years.",
                "rect": fitz.Rect(60, 116, 300, 131),
                "redact_rect": fitz.Rect(60, 116, 300, 131),
                "fit_rect": fitz.Rect(60, 116, 340, 170),
                "size": 11.0,
                "bold": False,
            }
        )

        rendered_lines, rendered_translations = (
            AdaptivePdfEngine()._coalesce_application_lines(
                [heading, body],
                ["仓库内存储时间", "预期寿命可延长至五年。"],
            )
        )

        self.assertEqual(len(rendered_lines), 2)
        self.assertEqual(
            rendered_translations,
            ["仓库内存储时间", "预期寿命可延长至五年。"],
        )

    def test_adaptive_flow_does_not_duplicate_preserved_bullet(self):
        lines = [
            {
                "text": "Lead paragraph",
                "rect": fitz.Rect(80, 100, 260, 115),
                "redact_rect": fitz.Rect(80, 100, 260, 115),
                "fit_rect": fitz.Rect(80, 100, 340, 125),
                "size": 10.0,
                "color": (0, 0, 0),
                "rotate": 0,
                "align": 0,
                "block": 7,
                "bold": False,
                "table": False,
                "container_rect": None,
                "header": False,
                "starts_bullet": False,
                "bullet_rect": None,
                "strip_generated_bullet": True,
            },
            {
                "text": "Bullet item",
                "rect": fitz.Rect(110, 116, 260, 131),
                "redact_rect": fitz.Rect(110, 116, 260, 131),
                "fit_rect": fitz.Rect(110, 116, 340, 170),
                "size": 10.0,
                "color": (0, 0, 0),
                "rotate": 0,
                "align": 0,
                "block": 7,
                "bold": False,
                "table": False,
                "container_rect": None,
                "header": False,
                "starts_bullet": True,
                "bullet_rect": fitz.Rect(68, 116, 76, 126),
                "strip_generated_bullet": True,
            },
        ]

        _rendered, translations = (
            AdaptivePdfEngine()._coalesce_application_lines(
                lines,
                ["Lead", "Item"],
            )
        )

        self.assertNotIn("◆", translations[0])

    def test_adaptive_layout_respects_table_cell_boundaries(self):
        source = self.root / "source.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=300)
        for x in (40, 200, 360):
            page.draw_line((x, 60), (x, 180), color=(0, 0, 0))
        for y in (60, 100, 140, 180):
            page.draw_line((40, y), (360, y), color=(0, 0, 0))
        page.insert_text(
            (48, 85),
            "Long component description",
            fontsize=10,
        )
        page.insert_text((208, 85), "Adjacent supplier", fontsize=10)
        document.save(source)
        document.close()

        document = fitz.open(source)
        try:
            groups = AdaptivePdfEngine()._page_lines(document[0])
        finally:
            document.close()

        component = next(
            group
            for group in groups
            if group["text"] == "Long component description"
        )
        supplier = next(
            group
            for group in groups
            if group["text"] == "Adjacent supplier"
        )
        self.assertLessEqual(component["fit_rect"].x1, 200)
        self.assertLessEqual(component["fit_rect"].y1, 100)
        self.assertGreaterEqual(supplier["fit_rect"].x0, 200)

    def test_sparse_notice_grid_is_not_treated_as_table_cells(self):
        class Table:
            row_count = 11
            col_count = 3
            cells = [(0, 0, 1, 1)] * 15 + [None] * 18

        self.assertFalse(_uses_table_cell_boundaries(Table()))

    def test_dense_multi_column_grid_uses_table_cells(self):
        class Table:
            row_count = 4
            col_count = 3
            cells = [(0, 0, 1, 1)] * 12

        self.assertTrue(_uses_table_cell_boundaries(Table()))

    def test_wide_notice_column_is_not_split_into_pseudo_cells(self):
        class Table:
            row_count = 4
            col_count = 3
            bbox = (129.2, 583.5, 512.3, 667.1)
            cells = [
                (129.2, 583.5, 133.5, 606.6),
                (129.2, 606.6, 133.5, 667.1),
                (133.5, 583.5, 507.8, 606.6),
                (133.5, 606.6, 507.8, 630.4),
                (133.5, 630.4, 507.8, 645.8),
                (133.5, 645.8, 507.8, 667.1),
                (507.8, 583.5, 512.3, 606.6),
                (507.8, 606.6, 512.3, 667.1),
            ]

        self.assertFalse(_uses_table_cell_boundaries(Table()))

    def test_pdf_row_spans_are_split_at_table_cell_boundaries(self):
        spans = [
            {"text": "Primer", "bbox": (45, 80, 95, 92)},
            {"text": "Hempel", "bbox": (145, 80, 195, 92)},
            {"text": "Jotun", "bbox": (245, 80, 285, 92)},
        ]
        cells = [
            fitz.Rect(40, 60, 120, 100),
            fitz.Rect(120, 60, 220, 100),
            fitz.Rect(220, 60, 320, 100),
            fitz.Rect(40, 60, 320, 100),
        ]

        groups = _line_span_groups(spans, cells)

        self.assertEqual(
            [[span["text"] for span in group] for group in groups],
            [["Primer"], ["Hempel"], ["Jotun"]],
        )

    def test_adaptive_layout_uses_whole_single_column_notice_region(self):
        source = self.root / "source.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=300)
        for x in (40, 360):
            page.draw_line((x, 60), (x, 180), color=(0, 0, 0))
        for y in (60, 100, 140, 180):
            page.draw_line((40, y), (360, y), color=(0, 0, 0))
        page.insert_text((50, 85), "First notice paragraph", fontsize=10)
        page.insert_text((50, 125), "Second notice paragraph", fontsize=10)
        page.insert_text((50, 165), "Third notice paragraph", fontsize=10)
        document.save(source)
        document.close()

        document = fitz.open(source)
        try:
            groups = AdaptivePdfEngine()._page_lines(document[0])
        finally:
            document.close()

        containers = {
            (
                tuple(
                    round(value, 1)
                    for value in fitz.Rect(group["container_rect"])
                )
                if group["container_rect"] is not None
                else None
            )
            for group in groups
            if group["text"].endswith("notice paragraph")
        }
        self.assertEqual(len(containers), 1)

    def test_adaptive_repair_does_not_replace_page_after_text_overflow(self):
        source = self.root / "source.pdf"
        target = self.root / "target.pdf"
        _write_lines(source, [80])

        target_document = fitz.open()
        target_document.new_page(width=400, height=500).insert_text(
            (40, 80),
            "Keep this smart-layout page",
        )
        target_document.save(target)
        target_document.close()

        failed_result = FileResult(
            input_path=str(source),
            output_path=str(target),
            status="completed",
            skipped_units=1,
            skipped_pages=[1],
            warnings=["text did not fit"],
        )
        with patch.object(
            AdaptivePdfEngine,
            "translate",
            return_value=failed_result,
        ):
            result = repair_pdf_pages(
                source,
                target,
                [1],
                IdentityTranslator(),
                TranslationOptions(target_language="zh"),
            )

        self.assertEqual(result.status, "failed")
        document = fitz.open(target)
        try:
            self.assertIn("Keep this smart-layout page", document[0].get_text())
        finally:
            document.close()

    def test_adaptive_repair_commits_good_pages_and_rolls_back_failed_page(self):
        source = self.root / "source.pdf"
        target = self.root / "target.pdf"
        source_document = fitz.open()
        source_document.new_page(width=400, height=500).insert_text(
            (40, 80),
            "Successful repaired page",
        )
        source_document.new_page(width=400, height=500).insert_text(
            (40, 80),
            "Failed repair source page",
        )
        source_document.save(source)
        source_document.close()

        target_document = fitz.open()
        target_document.new_page(width=400, height=500).insert_text(
            (40, 80),
            "Old first smart-layout page",
        )
        target_document.new_page(width=400, height=500).insert_text(
            (40, 80),
            "Keep failed second smart-layout page",
        )
        target_document.save(target)
        target_document.close()

        def fake_translate(
            _engine,
            selected_source,
            selected_output,
            _translator,
            _options,
            _progress,
        ):
            selected = fitz.open(selected_source)
            try:
                selected.save(selected_output)
            finally:
                selected.close()
            return FileResult(
                input_path=str(selected_source),
                output_path=str(selected_output),
                status="completed",
                skipped_units=1,
                skipped_pages=[2],
                warnings=["second repair page did not fit"],
            )

        with patch.object(AdaptivePdfEngine, "translate", fake_translate):
            result = repair_pdf_pages(
                source,
                target,
                [1, 2],
                IdentityTranslator(),
                TranslationOptions(target_language="zh"),
            )

        self.assertEqual(result.status, "completed", result.errors)
        self.assertEqual(result.usage["repaired_pages"], [1])
        self.assertEqual(result.usage["failed_pages"], [2])
        self.assertEqual(result.skipped_pages, [2])
        document = fitz.open(target)
        try:
            self.assertIn("Successful repaired page", document[0].get_text())
            self.assertNotIn("Old first smart-layout page", document[0].get_text())
            self.assertIn(
                "Keep failed second smart-layout page",
                document[1].get_text(),
            )
        finally:
            document.close()

    def test_adaptive_repair_rolls_back_page_that_fails_post_validation(self):
        source = self.root / "source.pdf"
        target = self.root / "target.pdf"
        _write_lines(
            source,
            [50, 85, 120, 155, 190, 225, 260, 295, 330, 365],
        )
        target_document = fitz.open()
        target_document.new_page(width=400, height=500).insert_text(
            (40, 80),
            "Keep smart-layout page",
        )
        target_document.save(target)
        target_document.close()

        def collapsed_translate(
            _engine,
            _selected_source,
            selected_output,
            _translator,
            _options,
            _progress,
        ):
            _write_lines(selected_output, [50, 85, 120, 155])
            return FileResult(
                input_path=str(source),
                output_path=str(selected_output),
                status="completed",
            )

        with patch.object(
            AdaptivePdfEngine,
            "translate",
            collapsed_translate,
        ):
            result = repair_pdf_pages(
                source,
                target,
                [1],
                IdentityTranslator(),
                TranslationOptions(target_language="zh"),
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.usage["failed_pages"], [1])
        document = fitz.open(target)
        try:
            self.assertIn("Keep smart-layout page", document[0].get_text())
        finally:
            document.close()

    def test_dual_rebuild_keeps_source_and_repaired_text(self):
        source = self.root / "source.pdf"
        mono = self.root / "mono.pdf"
        dual = self.root / "dual.pdf"
        _write_lines(source, [80])
        _write_lines(mono, [140])

        dual_document = fitz.open()
        dual_document.new_page(width=800, height=500).insert_text(
            (40, 60), "Old bilingual content"
        )
        dual_document.save(dual)
        dual_document.close()

        rebuild_dual_pages(dual, source, mono, [1])

        result = fitz.open(dual)
        try:
            text = result[0].get_text()
            self.assertEqual(result.page_count, 1)
            self.assertNotIn("Old bilingual content", text)
            self.assertGreaterEqual(text.count("Safety instruction"), 2)
        finally:
            result.close()

    def test_translation_cleanup_removes_generated_bullet_and_spaces_heading(self):
        cleaned = PdfEngine._clean_translation(
            {
                "strip_generated_bullet": True,
                "text": "Functional description",
            },
            "\uf0a8 ◆ 2.2.1.2功能描述",
        )
        self.assertEqual(cleaned, "2.2.1.2 功能描述")
        self.assertEqual(
            PdfEngine._clean_translation(
                {
                    "strip_generated_bullet": True,
                    "text": "Pull down the main switch",
                },
                "P拉下主隔离开关",
            ),
            "拉下主隔离开关",
        )
        self.assertEqual(
            PdfEngine._clean_translation(
                {
                    "strip_generated_bullet": True,
                    "text": "wiring diagram",
                },
                "wi接线图",
            ),
            "接线图",
        )


if __name__ == "__main__":
    unittest.main()
