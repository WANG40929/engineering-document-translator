from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("UDT_NO_SPLASH", "1")

try:
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication

    from translator_app.config import AppConfig, ConfigStore
    from translator_app.i18n import I18n, set_language
    from translator_app.qt_gui import TranslatorWindow
    from translator_app.secret_store import SecretStore

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


if __name__ == "__main__":
    unittest.main()
