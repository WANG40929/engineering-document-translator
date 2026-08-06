from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("UDT_NO_SPLASH", "1")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QAbstractItemView, QApplication, QProgressBar

    from translator_app.config import AppConfig, ConfigStore
    from translator_app.i18n import I18n, set_language
    from translator_app.models import FileResult, TranslationOptions
    from translator_app.qt_gui import NoFocusRectDelegate, TranslatorWindow
    from translator_app.secret_store import SecretStore
    from translator_app.task_queue import PreemptiveTaskQueue

    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, "PySide6 is not installed in this test environment")
class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, language: str) -> TranslatorWindow:
        config = AppConfig(ui_language=language)
        with (
            patch.object(ConfigStore, "load", return_value=config),
            patch.object(SecretStore, "load", return_value=""),
        ):
            return TranslatorWindow()

    def test_all_interface_languages_build_without_raw_resource_keys(self):
        for language in ("zh-CN", "en", "ru", "es", "fr", "de"):
            with self.subTest(language=language):
                catalog = I18n(language)
                window = self._window(language)
                try:
                    self.assertEqual(window.windowTitle(), catalog.t("app.name"))
                    self.assertEqual(window.title_label.text(), catalog.t("app.name"))
                    self.assertEqual(
                        window.start_button.text(),
                        catalog.t("main.start_translation"),
                    )
                    self.assertEqual(
                        window.table.horizontalHeaderItem(2).text(),
                        catalog.t("main.column_status"),
                    )
                    self.assertNotIn("language.", window.source_combo.currentText())
                    available_text_width = window.settings_button.width() - 42
                    self.assertLessEqual(
                        window.settings_button.fontMetrics().horizontalAdvance(
                            window.settings_button.label
                        ),
                        available_text_width,
                    )
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()

    def test_runtime_language_switch_retranslates_existing_task_cells(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_")
        try:
            source = Path(temporary.name) / "sample.pdf"
            source.touch()
            window._insert_paths([source])
            window.saved.ui_language = "de"
            set_language("de")
            window._retranslate_ui()
            catalog = I18n("de")
            self.assertEqual(window.windowTitle(), catalog.t("app.name"))
            self.assertEqual(
                window.table.horizontalHeaderItem(0).text(),
                catalog.t("main.tasks_count", count=1),
            )
            self.assertEqual(
                window.table.cellWidget(0, 2).label.text(),
                catalog.t("status.pending"),
            )
            self.assertEqual(
                window.table.cellWidget(0, 3).detail.text(),
                catalog.t("status.waiting_start"),
            )
        finally:
            set_language("auto")
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_close_during_translation_waits_for_worker_cleanup(self):
        window = self._window("zh-CN")
        try:
            window.running = True
            event = QCloseEvent()
            with patch.object(window, "_request_stop") as request_stop:
                window.closeEvent(event)
            self.assertFalse(event.isAccepted())
            self.assertTrue(window._close_when_stopped)
            request_stop.assert_called_once_with()

            with patch.object(window, "close") as close:
                window._on_stopped()
                self.app.processEvents()
                close.assert_called_once_with()
            self.assertFalse(window._close_when_stopped)
        finally:
            window.running = False
            window._close_when_stopped = False
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_minimum_window_width_keeps_summary_labels_visible(self):
        expected = {
            "zh-CN": ("自动识别", "简体中文", "输出到：原文件夹"),
            "en": ("Auto", "Chinese", "Output: Source folder"),
            "ru": ("Авто", "Китайский", "Выход: Исходная папка"),
            "es": ("Auto", "Chino", "Salida: Carpeta fuente"),
            "fr": ("Auto", "Chinois", "Sortie : Dossier source"),
            "de": ("Auto", "Chinesisch", "Ziel: Quellordner"),
        }
        for language, labels in expected.items():
            with self.subTest(language=language):
                window = self._window(language)
                try:
                    self.assertEqual(window.source_combo.currentText(), labels[0])
                    self.assertEqual(window.target_combo.currentText(), labels[1])
                    self.assertEqual(window.output_button.text(), labels[2])
                    self.assertLessEqual(len(labels[0]), 6)
                    self.assertLessEqual(len(labels[1]), 10)
                    self.assertLessEqual(len(labels[2]), 23)
                finally:
                    window.close()
                    window.deleteLater()
                    self.app.processEvents()

    def test_minimum_window_height_keeps_drop_zone_and_table_separate(self):
        window = self._window("zh-CN")
        try:
            window.resize(window.minimumSize())
            window.show()
            self.app.processEvents()
            self.assertLess(
                window.drop_zone.geometry().bottom(),
                window.table.geometry().top(),
            )
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_no_orphan_progress_bar_can_become_a_popup(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_")
        try:
            source = Path(temporary.name) / "sample.docx"
            source.touch()
            window._insert_paths([source])
            self.assertFalse(
                any(
                    isinstance(widget, QProgressBar) and widget.isWindow()
                    for widget in QApplication.allWidgets()
                )
            )
            self.assertFalse(hasattr(window, "progress"))
        finally:
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_task_table_keeps_row_selection_without_cell_focus_frame(self):
        window = self._window("zh-CN")
        try:
            self.assertIsInstance(window.table.itemDelegate(), NoFocusRectDelegate)
            self.assertEqual(
                window.table.selectionBehavior(),
                QAbstractItemView.SelectionBehavior.SelectRows,
            )
        finally:
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_urgent_task_pauses_current_and_moves_to_front(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_priority_")
        try:
            sources = [Path(temporary.name) / f"{name}.pdf" for name in ("current", "normal", "urgent")]
            for source in sources:
                source.touch()
            window._insert_paths(sources)
            window.run_queue = PreemptiveTaskQueue(sources)
            current = window.run_queue.pop_next()
            window.active_run_paths = window.run_queue.snapshot()
            window.running = True
            window._set_row_status(0, "translating")
            window._set_row_status(1, "queued")
            window._set_row_status(2, "queued")

            window._prioritize_path(str(sources[2]))

            table_order = [
                Path(window.table.item(row, 5).text()).stem
                for row in range(window.table.rowCount())
            ]
            self.assertEqual(table_order, ["current", "urgent", "normal"])
            self.assertTrue(window._should_preempt(str(sources[0])))
            self.assertEqual(
                window.table.item(window._row_for_path(sources[0]), 2).data(Qt.UserRole),
                "pausing",
            )
            urgent_row = window._row_for_path(sources[2])
            self.assertEqual(
                window.table.item(urgent_row, 2).data(Qt.UserRole),
                "priority",
            )

            self.assertTrue(window._consume_preempt(str(sources[0])))
            window.run_queue.requeue_current(current)
            window._on_preempted(str(sources[0]))
            resumed_order = [
                Path(window.table.item(row, 5).text()).stem
                for row in range(window.table.rowCount())
            ]
            self.assertEqual(resumed_order, ["urgent", "current", "normal"])
            paused_row = window._row_for_path(sources[0])
            self.assertEqual(
                window.table.item(paused_row, 2).data(Qt.UserRole),
                "paused",
            )
        finally:
            window.running = False
            window.run_queue = None
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_newly_added_urgent_file_joins_running_queue(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_priority_new_")
        try:
            current = Path(temporary.name) / "current.docx"
            urgent = Path(temporary.name) / "urgent.docx"
            current.touch()
            urgent.touch()
            window._insert_paths([current])
            window.run_queue = PreemptiveTaskQueue([current])
            window.run_queue.pop_next()
            window.active_run_paths = window.run_queue.snapshot()
            window.running = True
            window._set_row_status(0, "translating")

            window._insert_paths([urgent])
            window._prioritize_path(str(urgent))

            self.assertEqual(window.run_queue.total_count, 2)
            self.assertIn(str(urgent.resolve()), window.run_queue.pending_snapshot())
            self.assertTrue(window._should_preempt(str(current)))
        finally:
            window.running = False
            window.run_queue = None
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_worker_preempts_then_resumes_original_file(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_worker_priority_")
        try:
            root = Path(temporary.name)
            current = root / "current.docx"
            urgent = root / "urgent.docx"
            current.touch()
            urgent.touch()
            window._insert_paths([current, urgent])
            window.run_queue = PreemptiveTaskQueue([current, urgent])
            window.active_run_paths = window.run_queue.snapshot()
            window.running = True
            window._set_row_status(0, "queued")
            window._set_row_status(1, "queued")
            calls = []

            def fake_run(_pipeline, paths, _translator, _options, progress):
                source = Path(paths[0])
                calls.append(source.name)
                if source == current and calls.count(current.name) == 1:
                    window._prioritize_path(str(urgent))
                    progress(str(source), 0.4, "checkpoint")
                    self.fail("The urgent request should interrupt at the checkpoint")
                output = root / f"{source.stem}_ZH{source.suffix}"
                output.touch()
                progress(str(source), 1.0, "done")
                return [
                    FileResult(
                        str(source),
                        str(output),
                        status="completed",
                        translated_units=1,
                    )
                ]

            with (
                patch("translator_app.deepseek.DeepSeekTranslator", return_value=object()),
                patch("translator_app.cache.TranslationCache", return_value=object()),
                patch("translator_app.text_utils.load_glossary", return_value={}),
                patch("translator_app.pipeline.TranslationPipeline.run", new=fake_run),
                patch(
                    "translator_app.pipeline.write_report",
                    return_value=root / "translation_report.json",
                ),
                patch("translator_app.qt_gui.QMessageBox.information"),
            ):
                window._worker(
                    window.run_queue,
                    "test-key",
                    TranslationOptions(output_dir=root),
                )

            self.assertEqual(calls, ["current.docx", "urgent.docx", "current.docx"])
            self.assertFalse(window.running)
            for source in (current, urgent):
                row = window._row_for_path(source)
                self.assertEqual(window.table.item(row, 2).data(Qt.UserRole), "completed")
        finally:
            window.running = False
            window.run_queue = None
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_removing_last_idle_file_restores_ready_state(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_")
        try:
            source = Path(temporary.name) / "sample.docx"
            source.touch()
            window._insert_paths([source])
            window.status.setText("old task text")
            window._remove_path(str(source))
            self.assertEqual(window.table.rowCount(), 0)
            self.assertEqual(window.status.text(), I18n("zh-CN").t("status.ready"))
            self.assertFalse(window.start_button.isEnabled())
        finally:
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()

    def test_deleting_active_file_stops_without_stale_progress_text(self):
        window = self._window("zh-CN")
        temporary = tempfile.TemporaryDirectory(prefix="udt_gui_")
        try:
            source = Path(temporary.name) / "sample.docx"
            source.touch()
            window._insert_paths([source])
            window.running = True
            window.task_started = time.monotonic()
            window.active_run_paths = [str(source.resolve())]
            window.progress_timer.start()

            window._remove_path(str(source))
            stopping = I18n("zh-CN").t("status.stopping")
            self.assertTrue(window.stop_requested)
            self.assertFalse(window.progress_timer.isActive())
            self.assertEqual(window.status.text(), stopping)
            window._refresh_progress_text()
            self.assertEqual(window.status.text(), stopping)

            window._on_stopped()
            self.assertEqual(window.table.rowCount(), 0)
            self.assertEqual(window.status.text(), I18n("zh-CN").t("status.ready"))
            self.assertFalse(window.start_button.isEnabled())
        finally:
            window.running = False
            temporary.cleanup()
            window.close()
            window.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
