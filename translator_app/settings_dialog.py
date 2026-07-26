from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import AppConfig, app_data_dir
from .i18n import I18n, get_language, normalize_language_code, tr


class SettingsDialog(QDialog):
    """Compact settings window with a product introduction tab."""

    def __init__(self, config: AppConfig, api_key: str, save_key: bool, parent=None):
        super().__init__(parent)
        self.setFont(
            QFont("Microsoft YaHei UI" if get_language() == "zh-CN" else "Segoe UI")
        )
        self.setWindowTitle(tr("settings.title"))
        self.setModal(True)
        self.resize(700, 640)
        icon_path = Path(__file__).parent / "assets" / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(14)
        tabs = QTabWidget()
        tabs.addTab(self._translation_tab(config, api_key, save_key), tr("settings.tab_translation"))
        tabs.addTab(self._advanced_tab(config), tr("settings.tab_advanced"))
        header_icon = Path(__file__).parent / "assets" / "header-mark.svg"
        tabs.addTab(
            self._about_tab(header_icon if header_icon.exists() else icon_path),
            tr("settings.tab_about"),
        )
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        save_button.setText(tr("common.save"))
        save_button.setObjectName("saveButton")
        buttons.button(QDialogButtonBox.Cancel).setText(tr("common.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog { background: #f5f7fb; color: #152033; }
            QWidget { font-size: 13px; }
            QTabWidget::pane { background: white; border: 1px solid #e2e8f0; border-radius: 12px; top: -1px; }
            QTabBar::tab { padding: 10px 20px; color: #718096; border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: #1f67e8; border-bottom-color: #1f67e8; font-weight: 700; }
            QLineEdit, QSpinBox { min-height: 26px; padding: 6px 9px; background: white; border: 1px solid #d8e0eb; border-radius: 8px; }
            QLineEdit:focus, QSpinBox:focus { border-color: #7d9dec; }
            QPushButton { min-height: 28px; padding: 6px 15px; background: white; border: 1px solid #d7dee8; border-radius: 8px; }
            QPushButton:hover { border-color: #91a9e4; background: #f4f7ff; }
            QPushButton#saveButton { background:#1f67e8; color:white; border:none; font-weight:700; }
        """)

    def _translation_tab(self, config, api_key, save_key):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(22, 24, 22, 22)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)

        self.ui_language = QComboBox()
        language_catalog = I18n(config.ui_language)
        for code, label in language_catalog.language_choices():
            self.ui_language.addItem(label, code)
        language_index = self.ui_language.findData(normalize_language_code(config.ui_language))
        self.ui_language.setCurrentIndex(max(0, language_index))
        language_box = QVBoxLayout()
        language_box.setSpacing(5)
        language_box.addWidget(self.ui_language)
        language_note = QLabel(tr("settings.interface_language_restart"))
        language_note.setWordWrap(True)
        language_note.setStyleSheet("color:#667085;")
        language_box.addWidget(language_note)
        form.addRow(tr("language.interface"), language_box)

        self.key_edit = QLineEdit(api_key)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…")
        self.save_key = QCheckBox(tr("settings.save_key_windows"))
        self.save_key.setChecked(save_key)
        key_box = QVBoxLayout()
        key_box.setSpacing(6)
        key_box.addWidget(self.key_edit)
        key_box.addWidget(self.save_key)
        form.addRow(tr("settings.api_key"), key_box)

        self.glossary_edit = QLineEdit(config.glossary_path)
        self.glossary_edit.setPlaceholderText(tr("settings.glossary_placeholder"))
        choose = QPushButton(tr("common.choose"))
        choose.clicked.connect(self._choose_glossary)
        glossary_row = QHBoxLayout()
        glossary_row.addWidget(self.glossary_edit, 1)
        glossary_row.addWidget(choose)
        form.addRow(tr("settings.glossary"), glossary_row)

        self.pure_target = QCheckBox(tr("settings.pure_target"))
        self.pure_target.setChecked(config.pure_target_language)
        self.quality_review = QCheckBox(tr("settings.quality_review"))
        self.quality_review.setChecked(config.quality_review)
        self.force_refresh = QCheckBox(tr("settings.force_refresh"))
        self.force_refresh.setChecked(config.force_refresh)
        options = QVBoxLayout()
        options.setSpacing(9)
        options.addWidget(self.pure_target)
        options.addWidget(self.quality_review)
        options.addWidget(self.force_refresh)
        form.addRow(tr("settings.quality_options"), options)
        return tab

    def _advanced_tab(self, config):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(22, 24, 22, 22)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)

        self.pdf_mode = QComboBox()
        self.pdf_mode.addItem(tr("settings.pdf_mode_auto"), "auto")
        self.pdf_mode.addItem(tr("settings.pdf_mode_smart"), "smart")
        self.pdf_mode.addItem(tr("settings.pdf_mode_strict"), "strict")
        mode_index = self.pdf_mode.findData(config.pdf_mode)
        self.pdf_mode.setCurrentIndex(max(0, mode_index))
        self.pdf_mode.setToolTip(tr("settings.pdf_mode_tooltip"))
        form.addRow(tr("settings.pdf_mode"), self.pdf_mode)

        self.pdf_output = QComboBox()
        self.pdf_output.addItem(tr("settings.pdf_output_mono"), "mono")
        self.pdf_output.addItem(tr("settings.pdf_output_dual"), "dual")
        self.pdf_output.addItem(tr("settings.pdf_output_both"), "both")
        output_index = self.pdf_output.findData(config.pdf_output)
        self.pdf_output.setCurrentIndex(max(0, output_index))
        form.addRow(tr("settings.pdf_output"), self.pdf_output)

        self.babeldoc_edit = QLineEdit(config.babeldoc_path)
        self.babeldoc_edit.setPlaceholderText(tr("settings.babeldoc_placeholder"))
        choose_backend = QPushButton(tr("common.choose"))
        choose_backend.clicked.connect(self._choose_babeldoc)
        backend_row = QHBoxLayout()
        backend_row.addWidget(self.babeldoc_edit, 1)
        backend_row.addWidget(choose_backend)
        form.addRow(tr("settings.babeldoc_engine"), backend_row)

        backend_note = QLabel(tr("settings.babeldoc_note"))
        backend_note.setWordWrap(True)
        backend_note.setStyleSheet("color:#667085;")
        form.addRow("", backend_note)

        self.batch_size = QSpinBox()
        self.batch_size.setRange(1, 100)
        self.batch_size.setValue(config.batch_size)
        self.batch_size.setSuffix(tr("common.segments_per_batch_suffix"))
        form.addRow(tr("settings.batch_size"), self.batch_size)

        self.timeout = QSpinBox()
        self.timeout.setRange(30, 600)
        self.timeout.setValue(config.request_timeout)
        self.timeout.setSuffix(tr("common.seconds_suffix"))
        form.addRow(tr("settings.request_timeout"), self.timeout)

        cache_path = app_data_dir() / "translations.sqlite3"
        cache_size = cache_path.stat().st_size / (1024 * 1024) if cache_path.exists() else 0
        cache = QLabel(tr("settings.cache_note", size=cache_size))
        cache.setWordWrap(True)
        cache.setStyleSheet("color:#667085; line-height:1.45;")
        form.addRow(tr("settings.translation_cache"), cache)
        return tab

    def _about_tab(self, icon_path):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setAlignment(Qt.AlignCenter)
        if icon_path.exists():
            icon.setPixmap(QIcon(str(icon_path)).pixmap(62, 62))
        layout.addWidget(icon)
        title = QLabel(tr("app.name"))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:20px; font-weight:700; color:#172033;")
        layout.addWidget(title)
        version = QLabel(tr("about.product_line", version=__version__))
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color:#667085;")
        layout.addWidget(version)

        intro = QLabel(
            "\n\n".join(
                (
                    tr("about.description"),
                    tr("about.formats"),
                    tr("about.privacy"),
                )
            )
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        intro.setStyleSheet("color:#465263; line-height:1.55; background:#f8faff; border:1px solid #e1e8f5; border-radius:10px; padding:15px;")
        layout.addWidget(intro)

        link = QLabel(
            '<a href="https://github.com/WANG40929/engineering-document-translator">'
            f'{tr("about.github")}</a>'
        )
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignCenter)
        layout.addWidget(link)
        layout.addStretch()
        return tab

    def _choose_glossary(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.select_glossary"),
            "",
            f'{tr("dialog.filter_glossary")};;{tr("common.all_files")} (*.*)',
        )
        if path:
            self.glossary_edit.setText(path)

    def _choose_babeldoc(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr("dialog.select_babeldoc"),
            "",
            (
                f'{tr("dialog.filter_babeldoc")};;'
                f'{tr("common.executable_files")} (*.exe);;'
                f'{tr("common.all_files")} (*.*)'
            ),
        )
        if path:
            self.babeldoc_edit.setText(path)

    def values(self) -> dict:
        return {
            "ui_language": self.ui_language.currentData(),
            "api_key": self.key_edit.text().strip(),
            "save_key": self.save_key.isChecked(),
            "glossary_path": self.glossary_edit.text().strip(),
            "pure_target_language": self.pure_target.isChecked(),
            "quality_review": self.quality_review.isChecked(),
            "force_refresh": self.force_refresh.isChecked(),
            "batch_size": self.batch_size.value(),
            "request_timeout": self.timeout.value(),
            "pdf_mode": self.pdf_mode.currentData(),
            "pdf_output": self.pdf_output.currentData(),
            "babeldoc_path": self.babeldoc_edit.text().strip(),
        }
