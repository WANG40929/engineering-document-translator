from __future__ import annotations

import unittest
from unittest.mock import patch

from translator_app.i18n import (
    I18n,
    SUPPORTED_LANGUAGE_CODES,
    detect_system_language,
    format_message,
    get_language,
    message_placeholders,
    normalize_language_code,
    resolve_language,
    set_language,
    use_language,
    validate_catalogs,
)
from translator_app.locales import CATALOGS


class I18nTests(unittest.TestCase):
    def test_supported_language_set_is_stable(self):
        self.assertEqual(
            SUPPORTED_LANGUAGE_CODES,
            ("zh-CN", "en", "ru", "es", "fr", "de"),
        )

    def test_manual_language_codes_are_normalized(self):
        examples = {
            "zh_Hans_CN.UTF-8": "zh-CN",
            "zh-TW": "zh-CN",
            "EN_us": "en",
            "ru_KZ": "ru",
            "es-MX": "es",
            "fr_CA": "fr",
            "de-DE": "de",
            "system": "auto",
            None: "auto",
        }
        for value, expected in examples.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_language_code(value), expected)
        self.assertEqual(normalize_language_code("pt-BR"), "en")
        self.assertEqual(normalize_language_code("pt-BR", default="fr"), "fr")

    def test_system_language_detection_uses_first_supported_candidate(self):
        self.assertEqual(detect_system_language(["pt-BR", "ru_KZ", "en-US"]), "ru")
        self.assertEqual(detect_system_language(["zh-Hant-TW"]), "zh-CN")
        self.assertEqual(detect_system_language(["unsupported"]), "en")
        with patch("translator_app.i18n.detect_system_language", return_value="de"):
            self.assertEqual(resolve_language("auto"), "de")

    def test_catalogs_are_complete_and_placeholder_compatible(self):
        self.assertGreaterEqual(len(CATALOGS["en"]), 180)
        self.assertEqual(validate_catalogs(), ())
        for code, catalog in CATALOGS.items():
            with self.subTest(code=code):
                self.assertTrue(all(isinstance(value, str) and value for value in catalog.values()))

    def test_each_language_has_native_core_labels(self):
        expected_settings = {
            "zh-CN": "设置",
            "en": "Settings",
            "ru": "Настройки",
            "es": "Configuración",
            "fr": "Paramètres",
            "de": "Einstellungen",
        }
        for code, label in expected_settings.items():
            with self.subTest(code=code):
                catalog = I18n(code)
                self.assertEqual(catalog.language, code)
                self.assertEqual(catalog.t("settings.title"), label)

    def test_missing_key_falls_back_to_english_then_chinese(self):
        catalogs = {
            "de": {},
            "en": {"english_key": "English fallback"},
            "zh-CN": {
                "english_key": "中文后备",
                "chinese_key": "中文后备",
            },
        }
        catalog = I18n("de", catalogs)
        self.assertEqual(catalog.t("english_key"), "English fallback")
        self.assertEqual(catalog.t("chinese_key"), "中文后备")
        self.assertEqual(catalog.t("unknown_key"), "unknown_key")
        self.assertEqual(catalog.t("unknown_key", "Visible default"), "Visible default")

    def test_placeholder_formatting_is_safe(self):
        self.assertEqual(
            format_message("Done {done}/{total}", done=3, total=8),
            "Done 3/8",
        )
        self.assertEqual(
            format_message("Done {done}/{total}", done=3),
            "Done 3/{total}",
        )
        self.assertEqual(format_message("Size {size:.1f}", size="unknown"), "Size unknown")
        self.assertEqual(format_message("JSON {{value}}: {value}", value=2), "JSON {value}: 2")
        self.assertEqual(format_message("Malformed {value", value=2), "Malformed {value")
        self.assertEqual(message_placeholders("{done}/{total:02d}"), frozenset({"done", "total"}))

    def test_instance_and_process_wide_api(self):
        catalog = I18n("ru")
        self.assertEqual(catalog.t("main.tasks_count", count=4), "Задания (4)")
        choices = dict(catalog.language_choices())
        self.assertEqual(choices["auto"], "Как в системе")
        self.assertEqual(choices["de"], "Немецкий")

        previous = get_language()
        try:
            self.assertEqual(set_language("es_MX"), "es")
            self.assertEqual(get_language(), "es")
            with use_language("fr") as temporary:
                self.assertEqual(temporary.language, "fr")
                self.assertEqual(get_language(), "fr")
            self.assertEqual(get_language(), "es")
        finally:
            set_language(previous)


if __name__ == "__main__":
    unittest.main()
