from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

import fitz
from docx import Document
from openpyxl import Workbook, load_workbook

from translator_app.cache import TranslationCache
from translator_app.config import ConfigStore
from translator_app.deepseek import DeepSeekTranslator, IdentityTranslator
from translator_app.engines.csv_engine import CsvEngine
from translator_app.engines.docx_engine import DocxEngine
from translator_app.engines.pdf_engine import PdfEngine
from translator_app.engines.xlsx_engine import XlsxEngine
from translator_app.models import TranslationOptions
from translator_app.secret_store import SecretStore
from translator_app.text_utils import is_translatable, protect_text


class PrefixTranslator:
    usage = {"offline": True}

    def translate_many(self, texts, progress=None):
        if progress:
            progress(len(texts), len(texts))
        return [f"中译：{text}" for text in texts]


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="udt_test_")
        self.root = Path(self.temp.name)
        self.options = TranslationOptions(target_language="zh")

    def tearDown(self):
        self.temp.cleanup()

    def test_token_protection_and_classification(self):
        protected = protect_text("Pump KZ5001-MB-010 is 6.3 kV")
        self.assertIn("__UDT_", protected.text)
        self.assertEqual(protected.restore(protected.text), "Pump KZ5001-MB-010 is 6.3 kV")
        self.assertFalse(is_translatable("KZ5001-MB-010"))
        self.assertTrue(is_translatable("Lube oil pump"))

    def test_api_batch_deduplicates_and_caches(self):
        class MockDeepSeek(DeepSeekTranslator):
            calls = 0
            def _request(inner, items):
                inner.calls += 1
                return {item["id"]: "译文" for item in items}

        cache = TranslationCache(self.root / "cache.sqlite3")
        translator = MockDeepSeek("test-key", cache=cache)
        self.assertEqual(translator.translate_many(["Bearing", "Bearing", "Pump"]), ["译文", "译文", "译文"])
        self.assertEqual(translator.calls, 1)
        translator.translate_many(["Bearing", "Pump"])
        self.assertEqual(translator.calls, 1)

    def test_cache_trims_oldest_rows_and_compacts_file(self):
        path = self.root / "limited-cache.sqlite3"
        cache = TranslationCache(path, max_cache_bytes=64 * 1024)
        pairs = [(f"source-{index}-" + "x" * 600, f"target-{index}-" + "y" * 600) for index in range(200)]
        cache.put_many("en", "zh", pairs)
        conn = sqlite3.connect(path)
        try:
            remaining = conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
            oldest = conn.execute("SELECT source_text FROM translations ORDER BY rowid LIMIT 1").fetchone()[0]
        finally:
            conn.close()
        self.assertLess(remaining, len(pairs))
        self.assertNotIn("source-0-", oldest)
        self.assertLessEqual(path.stat().st_size, 64 * 1024)

    def test_legacy_model_config_is_migrated(self):
        path = self.root / "config.json"
        path.write_text('{"model":"deepseek-chat","target_language":"zh"}', encoding="utf-8")
        config = ConfigStore(path).load()
        self.assertEqual(config.model, "deepseek-v4-flash")
        self.assertFalse(config.pure_target_language)

    def test_pure_target_choice_is_respected_after_migration(self):
        path = self.root / "config-v2.json"
        path.write_text('{"config_version":2,"pure_target_language":true}', encoding="utf-8")
        self.assertTrue(ConfigStore(path).load().pure_target_language)

    def test_quality_review_retries_real_words_but_not_short_codes(self):
        class ReviewDeepSeek(DeepSeekTranslator):
            reviews = []
            def _request(inner, items, review=False):
                if review:
                    inner.reviews.extend(item["text"] for item in items)
                    return {item["id"]: "六角螺母" for item in items}
                return {item["id"]: item["text"] for item in items}

        translator = ReviewDeepSeek("test-key", cache=TranslationCache(self.root / "review.sqlite3"))
        result = translator.translate_many(["HEXAGON NUT", "PCE"])
        self.assertEqual(result, ["六角螺母", "PCE"])
        self.assertEqual(translator.reviews, ["HEXAGON NUT"])
        self.assertEqual(translator.usage["quality_retries"], 1)

    def test_dpapi_secret_round_trip(self):
        store = SecretStore(self.root / "key.bin")
        store.save("sk-test-123")
        self.assertEqual(store.load(), "sk-test-123")

    def test_pdf_text_layer_and_blank_page(self):
        source, output = self.root / "sample.pdf", self.root / "sample_ZH.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=300)
        page.draw_line((20, 100), (380, 100), color=(1, 0, 0), width=2)
        page.insert_text((30, 50), "Lube oil pump KZ5001-MB-010", fontsize=12)
        document.new_page(width=400, height=300)
        document.save(source); document.close()
        result = PdfEngine().translate(source, output, IdentityTranslator(), self.options)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.skipped_pages, [2])
        translated = fitz.open(output)
        self.assertEqual(translated.page_count, 2)
        self.assertIn("Lube oil pump", translated[0].get_text())
        self.assertTrue(translated[0].get_drawings())
        translated.close()

    def test_pdf_large_centered_title_is_not_lost(self):
        source, output = self.root / "title.pdf", self.root / "title_ZH.pdf"
        document = fitz.open()
        page = document.new_page(width=400, height=300)
        page.insert_text(
            (45, 70),
            "Lube Oil Pump Installation Manual",
            fontname="helv",
            fontsize=22,
        )
        document.save(source); document.close()

        class TitleTranslator:
            usage = {"offline": True}
            def translate_many(self, texts, progress=None):
                return ["润滑油泵安装调试手册" for _ in texts]

        result = PdfEngine().translate(source, output, TitleTranslator(), self.options)
        self.assertEqual(result.status, "completed")
        translated = fitz.open(output)
        try:
            self.assertIn("润滑油泵安装调试手册", translated[0].get_text())
        finally:
            translated.close()

    def test_docx_preserves_table(self):
        source, output = self.root / "sample.docx", self.root / "sample_ZH.docx"
        document = Document(); document.add_heading("Installation manual", 1)
        table = document.add_table(rows=1, cols=2); table.cell(0, 0).text = "Equipment"; table.cell(0, 1).text = "Bearing"
        document.save(source)
        result = DocxEngine().translate(source, output, PrefixTranslator(), self.options)
        self.assertEqual(result.status, "completed")
        translated = Document(output)
        self.assertEqual(len(translated.tables), 1)
        self.assertTrue(translated.paragraphs[0].text.startswith("中译："))

    def test_docx_translates_split_runs_as_one_paragraph(self):
        source, output = self.root / "split.docx", self.root / "split_ZH.docx"
        document = Document()
        paragraph = document.add_paragraph()
        paragraph.add_run("Packliste / ").bold = True
        paragraph.add_run("Packing List")
        document.save(source)

        class ContextTranslator:
            usage = {"offline": True}
            seen = []
            def translate_many(inner, texts, progress=None):
                inner.seen.extend(texts)
                return ["装箱单"]

        translator = ContextTranslator()
        result = DocxEngine().translate(source, output, translator, self.options)
        self.assertEqual(result.status, "completed")
        self.assertEqual(translator.seen, ["Packliste / Packing List"])
        self.assertEqual(Document(output).paragraphs[0].text, "装箱单")

    def test_xlsx_preserves_formula(self):
        source, output = self.root / "sample.xlsx", self.root / "sample_ZH.xlsx"
        book = Workbook(); sheet = book.active; sheet["A1"] = "Cable description"; sheet["B1"] = 5; sheet["C1"] = "=B1*2"; book.save(source)
        result = XlsxEngine().translate(source, output, PrefixTranslator(), self.options)
        self.assertEqual(result.status, "completed")
        translated = load_workbook(output, data_only=False)
        self.assertTrue(translated.active["A1"].value.startswith("中译："))
        self.assertEqual(translated.active["C1"].value, "=B1*2")
        translated.close()

    def test_csv_preserves_shape(self):
        source, output = self.root / "sample.csv", self.root / "sample_ZH.csv"
        with source.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle, delimiter=";").writerows([["Equipment", "Value"], ["Pump", "6.3 kV"]])
        result = CsvEngine().translate(source, output, PrefixTranslator(), self.options)
        self.assertEqual(result.status, "completed")
        with output.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter=";"))
        self.assertEqual(len(rows), 2); self.assertEqual(len(rows[0]), 2)


if __name__ == "__main__":
    unittest.main()
