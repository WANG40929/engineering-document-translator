from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from translator_app.deepseek import IdentityTranslator
from translator_app.engines.adaptive_pdf_engine import (
    AdaptivePdfEngine,
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
