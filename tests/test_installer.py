from __future__ import annotations

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InstallerLocalizationTests(unittest.TestCase):
    def test_simplified_chinese_catalog_is_vendored_and_valid(self):
        catalog_path = (
            PROJECT_ROOT
            / "installer"
            / "languages"
            / "ChineseSimplified.isl"
        )
        catalog = catalog_path.read_text(encoding="utf-8")

        self.assertIn("LanguageName=简体中文", catalog)
        self.assertIn("LanguageID=$0804", catalog)
        self.assertIn("SelectLanguageTitle=选择安装语言", catalog)
        self.assertIn("ButtonInstall=安装(&I)", catalog)

    def test_installer_always_includes_chinese_and_redetects_windows_language(self):
        script = (
            PROJECT_ROOT / "installer" / "DocumentTranslator.iss"
        ).read_text(encoding="utf-8")

        self.assertIn(
            'Name: "chinesesimplified"; '
            'MessagesFile: "compiler:Default.isl,'
            'languages\\ChineseSimplified.isl"',
            script,
        )
        language_section = script.split("[Languages]", 1)[1].split("[Tasks]", 1)[0]
        self.assertLess(
            language_section.index('Name: "english"'),
            language_section.index('Name: "chinesesimplified"'),
            "Unsupported Windows languages must fall back to English.",
        )
        self.assertIn("LanguageDetectionMethod=uilanguage", script)
        self.assertIn("UsePreviousLanguage=no", script)
        self.assertNotIn(
            '#if FileExists(CompilerPath + "Languages\\ChineseSimplified.isl")',
            script,
        )


if __name__ == "__main__":
    unittest.main()
