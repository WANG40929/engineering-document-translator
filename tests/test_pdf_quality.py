from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fitz

from translator_app.deepseek import IdentityTranslator
from translator_app.engines.adaptive_pdf_engine import (
    rebuild_dual_pages,
    repair_pdf_pages,
    replace_pdf_pages,
)
from translator_app.engines.pdf_engine import PdfEngine
from translator_app.models import TranslationOptions
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
