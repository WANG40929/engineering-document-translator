"""Performance-safety tests for v1.3.0.

The timing test uses a deterministic local fake API.  It is a regression
benchmark, not a claim about Internet speed: six 40 ms batches take about
240 ms serially and should complete in roughly two parallel waves while
preserving the exact input/output mapping.
"""

from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from translator_app.cache import TranslationCache
from translator_app.deepseek import AdaptiveRateLimiter, DeepSeekError, DeepSeekTranslator
from translator_app.engines.babeldoc_engine import BabelDocEngine, BabelDocProgress
from translator_app.engines.pdf_engine import PdfEngine
from translator_app.i18n import use_language
from translator_app.models import TranslationOptions


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="udt_performance_")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_independent_batches_run_concurrently_and_keep_mapping(self):
        class TimedTranslator(DeepSeekTranslator):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                inner.calls = 0
                inner.active = 0
                inner.max_active = 0
                inner.lock = threading.Lock()

            def _request(inner, items, review=False):
                with inner.lock:
                    inner.calls += 1
                    inner.active += 1
                    inner.max_active = max(inner.max_active, inner.active)
                try:
                    time.sleep(0.04)
                    return {
                        int(item["id"]): f"译文：{item['text']}"
                        for item in items
                    }
                finally:
                    with inner.lock:
                        inner.active -= 1

        cache = TranslationCache(self.root / "parallel.sqlite3")
        translator = TimedTranslator(
            "test-key",
            cache=cache,
            batch_size=2,
            pure_target_language=False,
            quality_review=False,
        )
        unique = [f"ordinary sentence number {index} for translation" for index in range(12)]
        texts = unique + [unique[2], unique[7]]
        updates = []
        started = time.monotonic()
        output = translator.translate_many(
            texts,
            lambda done, total: updates.append((done, total)),
        )
        elapsed = time.monotonic() - started

        self.assertEqual(
            output,
            [f"译文：{text}" for text in texts],
        )
        self.assertEqual(translator.calls, 6)
        self.assertGreaterEqual(translator.max_active, 2)
        self.assertLess(elapsed, 6 * 0.04 * 0.85)
        self.assertEqual(updates[-1], (12, 12))
        self.assertEqual(
            [done for done, _total in updates],
            sorted(done for done, _total in updates),
        )

        translator.translate_many(texts)
        self.assertEqual(translator.calls, 6, "第二次应完全复用译文缓存")

    def test_completed_parallel_batches_are_checkpointed_after_failure(self):
        class PartlyFailingTranslator(DeepSeekTranslator):
            def _request(inner, items, review=False):
                if any("failure marker" in item["text"] for item in items):
                    raise DeepSeekError("simulated batch failure")
                time.sleep(0.02)
                return {int(item["id"]): f"完成：{item['text']}" for item in items}

        class HealthyTranslator(DeepSeekTranslator):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                inner.received = []

            def _request(inner, items, review=False):
                inner.received.extend(item["text"] for item in items)
                return {int(item["id"]): f"完成：{item['text']}" for item in items}

        cache = TranslationCache(self.root / "checkpoint.sqlite3")
        texts = [
            "ordinary alpha sentence",
            "ordinary beta sentence",
            "failure marker sentence",
            "failure marker paragraph",
            "ordinary gamma sentence",
            "ordinary delta sentence",
        ]
        failing = PartlyFailingTranslator(
            "test-key",
            cache=cache,
            batch_size=2,
            pure_target_language=False,
            quality_review=False,
        )
        with self.assertRaises(DeepSeekError):
            failing.translate_many(texts)

        healthy = HealthyTranslator(
            "test-key",
            cache=cache,
            batch_size=2,
            pure_target_language=False,
            quality_review=False,
        )
        result = healthy.translate_many(texts)
        self.assertEqual(result, [f"完成：{text}" for text in texts])
        self.assertEqual(len(healthy.received), 2)
        self.assertTrue(all("failure marker" in text for text in healthy.received))

    def test_long_segment_isolated_so_short_results_are_checkpointed(self):
        class LongFailingTranslator(DeepSeekTranslator):
            def _request(inner, items, review=False):
                if any(len(item["text"]) > 1200 for item in items):
                    raise DeepSeekError("simulated long-segment failure")
                return {
                    int(item["id"]): f"完成：{item['text']}"
                    for item in items
                }

        class HealthyTranslator(DeepSeekTranslator):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                inner.received = []

            def _request(inner, items, review=False):
                inner.received.extend(item["text"] for item in items)
                return {
                    int(item["id"]): f"完成：{item['text']}"
                    for item in items
                }

        cache = TranslationCache(self.root / "long-isolation.sqlite3")
        short = [f"ordinary packing-list field {index}" for index in range(27)]
        long_text = ("long bilingual legal statement " * 55).strip()
        options = dict(
            cache=cache,
            batch_size=40,
            pure_target_language=False,
            quality_review=False,
        )
        with self.assertRaises(DeepSeekError):
            LongFailingTranslator("test-key", **options).translate_many(
                [*short, long_text]
            )

        healthy = HealthyTranslator("test-key", **options)
        result = healthy.translate_many([*short, long_text])
        self.assertEqual(result[-1], f"完成：{long_text}")
        self.assertEqual(healthy.received, [long_text])

    def test_permanent_failure_does_not_launch_the_entire_queue(self):
        class FailingTranslator(DeepSeekTranslator):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                inner.calls = 0
                inner.lock = threading.Lock()

            def _request(inner, items, review=False):
                with inner.lock:
                    inner.calls += 1
                    call_number = inner.calls
                if call_number == 1:
                    raise DeepSeekError("permanent failure")
                time.sleep(0.02)
                return {int(item["id"]): f"完成：{item['text']}" for item in items}

        translator = FailingTranslator(
            "test-key",
            cache=TranslationCache(self.root / "bounded-failure.sqlite3"),
            batch_size=1,
            pure_target_language=False,
            quality_review=False,
        )
        with self.assertRaises(DeepSeekError):
            translator.translate_many(
                [f"ordinary queued sentence {index}" for index in range(20)]
            )
        self.assertLessEqual(
            translator.calls,
            translator._worker_limit,
            "永久错误后不得继续启动整份文档的剩余API请求",
        )

    def test_rate_limiter_reduces_then_cautiously_recovers(self):
        limiter = AdaptiveRateLimiter(initial_qps=4, maximum_qps=4)
        limiter.throttle()
        self.assertEqual(limiter.qps, 2)
        for _ in range(8):
            limiter.record_success()
        self.assertEqual(limiter.qps, 2.5)

    def test_api_errors_redact_the_actual_key(self):
        translator = DeepSeekTranslator(
            "sk-sensitive-value",
            cache=TranslationCache(self.root / "redact.sqlite3"),
        )
        redacted = translator._redact_error(
            "Authorization: Bearer sk-sensitive-value api_key=sk-sensitive-value"
        )
        self.assertNotIn("sk-sensitive-value", redacted)
        self.assertIn("***", redacted)

    def test_babeldoc_uses_official_safe_parallelism(self):
        config_path = self.root / "babeldoc.toml"

        class Translator:
            api_key = "test-key"
            base_url = "https://api.deepseek.com/chat/completions"

        with patch("translator_app.engines.babeldoc_engine.os.cpu_count", return_value=8):
            BabelDocEngine()._write_config(
                config_path,
                Translator(),
                TranslationOptions(model="deepseek-v4-flash"),
            )
        config = config_path.read_text(encoding="utf-8")
        self.assertIn("qps = 4", config)
        self.assertIn("pool-max-workers = 4", config)
        self.assertIn("term-pool-max-workers = 3", config)

    def test_babeldoc_progress_is_monotonic_and_shows_real_units(self):
        with use_language("zh-CN"):
            tracker = BabelDocProgress()
            first, message = tracker.update("Parse Page Layout (1/2) 2/10")
            self.assertIn("第 2/10 页", message)
            self.assertIn("第 1/2 部分", message)

            second, message = tracker.update("Translate Paragraphs (1/2) 12/40")
            self.assertGreater(second, first)
            self.assertIn("12/40 段", message)

            third, _message = tracker.update("translate 63.0/100")
            self.assertGreaterEqual(third, second)
            percentage, _message = tracker.update("translate 71%")
            self.assertEqual(percentage, 0.71)
            fourth, _message = tracker.update("Parse PDF and Create Intermediate Representation 1%")
            self.assertEqual(fourth, percentage, "后端刷新旧阶段时总进度不得倒退")
            _fraction, message = tracker.update("Save PDF 1/2")
            _fraction, repeated_early_stage = tracker.update("Parse Page Layout 4/4")
            self.assertEqual(repeated_early_stage, message, "Rich 重绘旧任务时阶段文字不得倒退")

    def test_translation_engine_release_folder_is_discovered(self):
        engine = self.root / "TranslationEngine" / "babeldoc.exe"
        engine.parent.mkdir()
        engine.touch()
        fake_executable = self.root / "DocumentTranslator.exe"
        with (
            patch("translator_app.engines.babeldoc_engine.sys.executable", str(fake_executable)),
            patch("translator_app.engines.babeldoc_engine.shutil.which", return_value=None),
        ):
            self.assertEqual(BabelDocEngine.resolve_command(), engine.resolve())

    def test_bundled_engine_takes_precedence_over_system_path(self):
        bundled = self.root / "TranslationEngine" / "babeldoc.exe"
        bundled.parent.mkdir()
        bundled.touch()
        stale_global = self.root / "old-system-babeldoc.exe"
        stale_global.touch()
        fake_executable = self.root / "DocumentTranslator.exe"
        with (
            patch("translator_app.engines.babeldoc_engine.sys.executable", str(fake_executable)),
            patch(
                "translator_app.engines.babeldoc_engine.shutil.which",
                return_value=str(stale_global),
            ),
        ):
            self.assertEqual(BabelDocEngine.resolve_command(), bundled.resolve())

    def test_strict_pdf_aggregates_pages_and_uses_core_concurrency(self):
        source = self.root / "multi-page.pdf"
        destination = self.root / "multi-page_ZH.pdf"
        document = fitz.open()
        for page_index in range(4):
            page = document.new_page(width=500, height=300)
            for line_index in range(3):
                page.insert_text(
                    (35, 45 + line_index * 45),
                    f"ordinary safety sentence page {page_index} line {line_index}",
                    fontsize=10,
                )
        document.save(source)
        document.close()

        class ConcurrentTranslator(DeepSeekTranslator):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                inner.translate_many_calls = 0
                inner.active = 0
                inner.max_active = 0
                inner.lock = threading.Lock()

            def translate_many(inner, texts, progress=None):
                inner.translate_many_calls += 1
                return super().translate_many(texts, progress)

            def _request(inner, items, review=False):
                with inner.lock:
                    inner.active += 1
                    inner.max_active = max(inner.max_active, inner.active)
                try:
                    time.sleep(0.03)
                    return {
                        int(item["id"]): f"Translated {item['text']}"
                        for item in items
                    }
                finally:
                    with inner.lock:
                        inner.active -= 1

        translator = ConcurrentTranslator(
            "test-key",
            cache=TranslationCache(self.root / "strict-pdf.sqlite3"),
            batch_size=2,
            pure_target_language=False,
            quality_review=False,
        )
        updates = []
        result = PdfEngine().translate(
            source,
            destination,
            translator,
            TranslationOptions(target_language="zh"),
            lambda _file, fraction, message: updates.append((fraction, message)),
        )
        self.assertEqual(result.status, "completed", result.errors)
        self.assertEqual(result.translated_units, 12)
        self.assertEqual(translator.translate_many_calls, 1)
        self.assertGreaterEqual(translator.max_active, 2)
        self.assertEqual(updates[-1][0], 1.0)
        self.assertEqual(
            [fraction for fraction, _message in updates],
            sorted(fraction for fraction, _message in updates),
        )
        self.assertTrue(any("PDF 全文" in message for _fraction, message in updates))
        self.assertTrue(any("正在写回 PDF" in message for _fraction, message in updates))

    def test_strict_pdf_aggregate_failure_falls_back_to_exact_page(self):
        source = self.root / "fallback-pages.pdf"
        destination = self.root / "fallback-pages_ZH.pdf"
        document = fitz.open()
        document.new_page(width=400, height=250).insert_text(
            (30, 50),
            "First page ordinary text",
            fontsize=11,
        )
        document.new_page(width=400, height=250).insert_text(
            (30, 50),
            "Second page failure text",
            fontsize=11,
        )
        document.save(source)
        document.close()

        class LocatingTranslator(DeepSeekTranslator):
            def __init__(inner, *args, **kwargs):
                super().__init__(*args, **kwargs)
                inner.translate_many_calls = 0

            def translate_many(inner, texts, progress=None):
                inner.translate_many_calls += 1
                if inner.translate_many_calls == 1:
                    raise DeepSeekError("simulated aggregate failure")
                if any("Second page" in text for text in texts):
                    raise DeepSeekError("simulated persistent page failure")
                if progress:
                    progress(len(texts), len(texts))
                return list(texts)

        translator = LocatingTranslator(
            "test-key",
            cache=TranslationCache(self.root / "fallback.sqlite3"),
            quality_review=False,
        )
        updates = []
        result = PdfEngine().translate(
            source,
            destination,
            translator,
            TranslationOptions(target_language="zh"),
            lambda _file, fraction, message: updates.append((fraction, message)),
        )
        self.assertEqual(result.status, "failed")
        self.assertIn("PDF 第 2/2 页翻译失败", result.errors[0])
        self.assertEqual(translator.translate_many_calls, 3)
        self.assertLess(updates[-1][0], 1.0)
        self.assertEqual(
            [fraction for fraction, _message in updates],
            sorted(fraction for fraction, _message in updates),
        )


if __name__ == "__main__":
    unittest.main()
