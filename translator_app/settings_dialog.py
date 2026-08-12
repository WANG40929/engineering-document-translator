from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import Qt, Signal
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
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .config import AppConfig, app_data_dir
from .i18n import I18n, get_language, normalize_language_code, tr
from .providers import PRESETS, ProviderProfile, get_preset, new_profile


class NoWheelComboBox(QComboBox):
    """Prevent accidental value changes while scrolling the settings page."""

    def wheelEvent(self, event):
        event.ignore()


class SettingsDialog(QDialog):
    """Compact settings window with a product introduction tab."""

    connection_tested = Signal(str, bool, str, list)

    def __init__(self, config: AppConfig, api_keys: dict[str, str], save_key: bool, parent=None):
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
        tabs.setObjectName("settingsTabs")
        self.profile_values = [item.to_dict() for item in config.profiles()]
        self.api_keys = dict(api_keys)
        self._current_profile_index = -1
        tabs.addTab(self._translation_tab(config, save_key), tr("settings.tab_translation"))
        tabs.addTab(self._advanced_tab(config), tr("settings.tab_advanced"))
        header_icon = Path(__file__).parent / "assets" / "header-mark.svg"
        tabs.addTab(
            self._about_tab(header_icon if header_icon.exists() else icon_path),
            tr("settings.tab_about"),
        )
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save_button = buttons.button(QDialogButtonBox.Save)
        self.save_button = save_button
        save_button.setText(tr("common.save"))
        save_button.setObjectName("saveButton")
        buttons.button(QDialogButtonBox.Cancel).setText(tr("common.cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        arrow_path = (Path(__file__).parent / "assets" / "chevron-down.svg").as_posix()
        self.setStyleSheet("""
            QDialog { background: #ffffff; color: #152033; }
            QWidget { font-size: 13px; }
            QWidget#settingsPage, QScrollArea#settingsScroll,
            QScrollArea#settingsScroll > QWidget > QWidget {
                background: #ffffff;
            }
            QTabWidget::pane { background: #ffffff; border: 1px solid #dfe6f1; border-radius: 12px; top: -1px; }
            QTabBar::tab { min-width: 72px; padding: 11px 20px; color: #667085; background: transparent; border-bottom: 2px solid transparent; }
            QTabBar::tab:hover { color: #1f67e8; background: #f7f9fe; }
            QTabBar::tab:selected { color: #1f67e8; border-bottom-color: #1f67e8; font-weight: 700; }
            QLineEdit, QSpinBox, QComboBox {
                min-height: 26px; padding: 6px 9px; background: #ffffff;
                border: 1px solid #d5deea; border-radius: 8px;
            }
            QComboBox { padding-right: 28px; }
            QComboBox::drop-down { width: 28px; border: none; background: transparent; }
            QComboBox::down-arrow { image: url("__ARROW_PATH__"); width: 10px; height: 6px; }
            QComboBox QAbstractItemView {
                background: #ffffff; color: #152033; border: 1px solid #d5deea;
                border-radius: 8px; selection-background-color: #eaf1ff;
                selection-color: #174ea6; outline: 0; padding: 4px;
            }
            QLineEdit:hover, QSpinBox:hover, QComboBox:hover { border-color: #aebed4; }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #5b84ed; }
            QLineEdit[invalid="true"], QComboBox[invalid="true"] { border-color: #e5484d; background: #fffafa; }
            QLineEdit:disabled { color: #8b96a8; background: #f6f8fb; }
            QPushButton { min-height: 28px; padding: 6px 15px; background: white; border: 1px solid #d7dee8; border-radius: 8px; }
            QPushButton:hover { border-color: #91a9e4; background: #f4f7ff; }
            QPushButton:pressed { background: #eaf0ff; }
            QPushButton:disabled { color: #a0a9b8; background: #f6f7f9; border-color: #e3e7ed; }
            QPushButton#saveButton { background:#1f67e8; color:white; border:none; font-weight:700; }
            QPushButton#saveButton:hover { background:#185bd4; }
            QScrollBar:vertical { width: 10px; background: transparent; margin: 4px 2px; }
            QScrollBar::handle:vertical { min-height: 28px; background: #cbd5e3; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #aebbd0; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """.replace("__ARROW_PATH__", arrow_path))

    def _translation_tab(self, config, save_key):
        tab = QScrollArea()
        tab.setObjectName("settingsScroll")
        tab.setWidgetResizable(True)
        tab.setFrameShape(QScrollArea.NoFrame)
        tab.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("settingsPage")
        content.setMinimumWidth(0)
        tab.setWidget(content)
        form = QFormLayout(content)
        form.setContentsMargins(22, 24, 22, 22)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.ui_language = QComboBox()
        self._configure_combo(self.ui_language)
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

        self.profile_combo = QComboBox()
        self._configure_combo(self.profile_combo)
        for item in self.profile_values:
            self.profile_combo.addItem(item["name"], item["id"])
        active_index = self.profile_combo.findData(config.active_provider_id)
        self.profile_combo.setCurrentIndex(max(0, active_index))
        add_profile = QPushButton(tr("settings.provider_add"))
        remove_profile = QPushButton(tr("settings.provider_remove"))
        self.remove_profile_button = remove_profile
        add_profile.clicked.connect(self._add_profile)
        remove_profile.clicked.connect(self._remove_profile)
        profile_box = QVBoxLayout()
        profile_box.setSpacing(7)
        profile_box.addWidget(self.profile_combo)
        profile_actions = QHBoxLayout()
        profile_actions.setSpacing(7)
        profile_actions.addStretch(1)
        profile_actions.addWidget(add_profile)
        profile_actions.addWidget(remove_profile)
        profile_box.addLayout(profile_actions)
        form.addRow(tr("settings.provider_profile"), profile_box)

        self.provider_combo = NoWheelComboBox()
        self._configure_combo(self.provider_combo)
        for preset in PRESETS:
            self.provider_combo.addItem(preset.name, preset.id)
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        form.addRow(tr("settings.provider"), self.provider_combo)

        self.profile_name_edit = QLineEdit()
        self.profile_name_edit.textEdited.connect(self._profile_name_edited)
        self.profile_name_edit.editingFinished.connect(self._profile_name_finished)
        form.addRow(tr("settings.profile_name"), self.profile_name_edit)
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("https://…/chat/completions")
        form.addRow(tr("settings.base_url"), self.base_url_edit)
        self.model_edit = QComboBox()
        self._configure_combo(self.model_edit)
        self.model_edit.setEditable(True)
        form.addRow(tr("settings.model"), self.model_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…")
        self.save_key = QCheckBox(tr("settings.save_key_windows"))
        self.save_key.setToolTip(tr("settings.save_key_tooltip"))
        self.save_key.setChecked(save_key)
        key_box = QVBoxLayout()
        key_box.setSpacing(6)
        key_box.addWidget(self.key_edit)
        key_box.addWidget(self.save_key)
        form.addRow(tr("settings.api_key"), key_box)

        test_button = QPushButton(tr("settings.test_connection"))
        test_button.setToolTip(tr("settings.test_connection_tooltip"))
        test_button.clicked.connect(self._test_connection)
        self.test_button = test_button
        form.addRow("", test_button)

        self.fallback_combo = QComboBox()
        self._configure_combo(self.fallback_combo)
        self._refresh_fallback_combo(config.fallback_provider_id)
        form.addRow(tr("settings.fallback_provider"), self.fallback_combo)

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
        self._style_form_labels(form)
        self.profile_combo.currentIndexChanged.connect(self._profile_changed)
        self.connection_tested.connect(self._connection_test_finished)
        self._load_profile(self.profile_combo.currentIndex())
        return tab

    def _store_current_profile(self):
        index = self._current_profile_index
        if index < 0 or index >= len(self.profile_values):
            return
        item = self.profile_values[index]
        item.update({
            "name": self.profile_name_edit.text().strip() or self.provider_combo.currentText(),
            "provider": self.provider_combo.currentData(),
            "api_style": get_preset(self.provider_combo.currentData()).api_style,
            "base_url": self.base_url_edit.text().strip(),
            "model": self.model_edit.currentText().strip(),
        })
        self.api_keys[item["id"]] = self.key_edit.text().strip()
        self.profile_combo.setItemText(index, item["name"])
        fallback_index = self.fallback_combo.findData(item["id"])
        if fallback_index >= 0:
            self.fallback_combo.setItemText(fallback_index, item["name"])

    def _load_profile(self, index):
        if index < 0 or index >= len(self.profile_values):
            return
        self._current_profile_index = index
        item = ProviderProfile.from_dict(self.profile_values[index])
        self.provider_combo.blockSignals(True)
        self.provider_combo.setCurrentIndex(max(0, self.provider_combo.findData(item.provider)))
        self.provider_combo.blockSignals(False)
        self.profile_name_edit.setText(item.name)
        self.base_url_edit.setText(item.base_url)
        self.model_edit.clear()
        if item.model:
            self.model_edit.addItem(item.model)
        self.model_edit.setCurrentText(item.model)
        self.key_edit.setText(self.api_keys.get(item.id, ""))
        self.key_edit.setEnabled(item.preset.requires_api_key)
        self.key_edit.setPlaceholderText(
            "sk-..." if item.preset.requires_api_key else tr("settings.api_key_not_required")
        )
        self._update_profile_controls()

    def _profile_changed(self, index):
        previous = self._current_profile_index
        if previous != index:
            fallback_id = self.fallback_combo.currentData() or ""
            self._store_current_profile()
            self._load_profile(index)
            self._refresh_fallback_combo(fallback_id)

    def _provider_changed(self):
        preset = get_preset(self.provider_combo.currentData())
        self.base_url_edit.setText(preset.base_url)
        self.model_edit.clear()
        self.model_edit.setCurrentText(preset.default_model)
        self.key_edit.setEnabled(preset.requires_api_key)
        self.key_edit.setPlaceholderText(
            "sk-..." if preset.requires_api_key else tr("settings.api_key_not_required")
        )
        self._clear_validation_state()

    def _profile_name_edited(self, text):
        index = self._current_profile_index
        name = text.strip()
        if index < 0 or index >= len(self.profile_values) or not name:
            return
        self.profile_values[index]["name"] = name
        self.profile_combo.setItemText(index, name)
        fallback_index = self.fallback_combo.findData(self.profile_values[index]["id"])
        if fallback_index >= 0:
            self.fallback_combo.setItemText(fallback_index, name)

    def _profile_name_finished(self):
        fallback_id = self.fallback_combo.currentData() or ""
        self._store_current_profile()
        self._refresh_fallback_combo(fallback_id)

    def _default_profile_name(self, number: int) -> str:
        return tr("settings.default_profile_name", number=number)

    def _next_default_profile_name(self) -> str:
        existing = {str(item.get("name") or "").casefold() for item in self.profile_values}
        number = len(self.profile_values) + 1
        while self._default_profile_name(number).casefold() in existing:
            number += 1
        return self._default_profile_name(number)

    def _refresh_fallback_combo(self, selected_id: str | None = None):
        if not hasattr(self, "fallback_combo"):
            return
        if selected_id is None:
            selected_id = self.fallback_combo.currentData() or ""
        active_id = self.profile_combo.currentData() if hasattr(self, "profile_combo") else ""
        self.fallback_combo.blockSignals(True)
        self.fallback_combo.clear()
        self.fallback_combo.addItem(tr("settings.no_fallback"), "")
        for item in self.profile_values:
            if item["id"] != active_id:
                self.fallback_combo.addItem(item["name"], item["id"])
        index = self.fallback_combo.findData(selected_id)
        self.fallback_combo.setCurrentIndex(index if index >= 0 else 0)
        self.fallback_combo.blockSignals(False)

    def _update_profile_controls(self):
        self.remove_profile_button.setEnabled(len(self.profile_values) > 1)

    @staticmethod
    def _style_form_labels(form: QFormLayout):
        """Keep translated labels readable without widening the whole dialog."""
        for row in range(form.rowCount()):
            item = form.itemAt(row, QFormLayout.LabelRole)
            label = item.widget() if item else None
            if isinstance(label, QLabel):
                label.setWordWrap(True)
                label.setMinimumWidth(120)
                label.setMaximumWidth(150)
                label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    @staticmethod
    def _configure_combo(combo: QComboBox):
        """Let long translated choices elide inside the available field width."""
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(14)
        combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _add_profile(self):
        self._store_current_profile()
        if len(self.profile_values) == 1:
            first = self.profile_values[0]
            preset = get_preset(str(first.get("provider") or ""))
            if first.get("id") == "deepseek-default" and first.get("name") == preset.name:
                first["name"] = self._default_profile_name(1)
                self.profile_combo.setItemText(0, first["name"])
                if self._current_profile_index == 0:
                    self.profile_name_edit.setText(first["name"])
        item = new_profile("deepseek").to_dict()
        item["name"] = self._next_default_profile_name()
        self.profile_values.append(item)
        self.profile_combo.addItem(item["name"], item["id"])
        self.profile_combo.setCurrentIndex(len(self.profile_values) - 1)
        self._refresh_fallback_combo()
        self._update_profile_controls()

    def _remove_profile(self):
        if len(self.profile_values) <= 1:
            return
        index = self.profile_combo.currentIndex()
        item = self.profile_values.pop(index)
        self.api_keys.pop(item["id"], None)
        self.profile_combo.blockSignals(True)
        self.profile_combo.removeItem(index)
        self.profile_combo.blockSignals(False)
        fallback_index = self.fallback_combo.findData(item["id"])
        if fallback_index >= 0:
            self.fallback_combo.removeItem(fallback_index)
        self._current_profile_index = -1
        self._load_profile(self.profile_combo.currentIndex())
        self._refresh_fallback_combo()
        self._update_profile_controls()

    @staticmethod
    def _set_invalid(widget, invalid: bool):
        widget.setProperty("invalid", invalid)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _clear_validation_state(self):
        self._set_invalid(self.base_url_edit, False)
        self._set_invalid(self.model_edit, False)
        self._set_invalid(self.key_edit, False)

    def _validate_current_profile(self) -> bool:
        self._clear_validation_state()
        preset = get_preset(self.provider_combo.currentData())
        base_url = self.base_url_edit.text().strip()
        parts = urlsplit(base_url)
        if not base_url or parts.scheme not in {"http", "https"} or not parts.netloc:
            self._set_invalid(self.base_url_edit, True)
            self.base_url_edit.setFocus()
            QMessageBox.warning(
                self,
                tr("settings.validation_title"),
                tr("settings.validation_base_url"),
            )
            return False
        if preset.api_style != "azure" and not self.model_edit.currentText().strip():
            self._set_invalid(self.model_edit, True)
            self.model_edit.setFocus()
            QMessageBox.warning(
                self,
                tr("settings.validation_title"),
                tr("settings.validation_model"),
            )
            return False
        if preset.requires_api_key and not self.key_edit.text().strip():
            self._set_invalid(self.key_edit, True)
            self.key_edit.setFocus()
            QMessageBox.warning(
                self,
                tr("settings.validation_title"),
                tr("settings.validation_api_key"),
            )
            return False
        return True

    def accept(self):
        if not self._validate_current_profile():
            return
        self._store_current_profile()
        super().accept()

    def _test_connection(self):
        if not self._validate_current_profile():
            return
        self._store_current_profile()
        item = ProviderProfile.from_dict(self.profile_values[self.profile_combo.currentIndex()])
        key = self.api_keys.get(item.id, "")
        self.test_button.setEnabled(False)
        self.test_button.setText(tr("settings.testing_connection"))

        def worker():
            try:
                from .deepseek import DeepSeekTranslator
                translator = DeepSeekTranslator.from_profile(item, key, timeout=30, quality_review=False)
                ok, message, models = translator.test_connection_details()
                self.connection_tested.emit(item.id, ok, message, models)
            except Exception as exc:
                self.connection_tested.emit(item.id, False, str(exc), [])

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _connection_test_finished(self, profile_id, ok, message, models):
        self.test_button.setEnabled(True)
        self.test_button.setText(tr("settings.test_connection"))
        if ok and models and self.profile_combo.currentData() == profile_id:
            current = self.model_edit.currentText()
            self.model_edit.clear()
            self.model_edit.addItems(models)
            index = self.model_edit.findText(current)
            self.model_edit.setCurrentIndex(max(0, index))
        box = QMessageBox.information if ok else QMessageBox.warning
        box(self, tr("settings.connection_test_title"), message)

    def _advanced_tab(self, config):
        tab = QWidget()
        tab.setObjectName("settingsPage")
        form = QFormLayout(tab)
        form.setContentsMargins(22, 24, 22, 22)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)
        form.setRowWrapPolicy(QFormLayout.DontWrapRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.pdf_mode = QComboBox()
        self._configure_combo(self.pdf_mode)
        self.pdf_mode.addItem(tr("settings.pdf_mode_auto"), "auto")
        self.pdf_mode.addItem(tr("settings.pdf_mode_smart"), "smart")
        self.pdf_mode.addItem(tr("settings.pdf_mode_strict"), "strict")
        mode_index = self.pdf_mode.findData(config.pdf_mode)
        self.pdf_mode.setCurrentIndex(max(0, mode_index))
        self.pdf_mode.setToolTip(tr("settings.pdf_mode_tooltip"))
        form.addRow(tr("settings.pdf_mode"), self.pdf_mode)

        self.pdf_output = QComboBox()
        self._configure_combo(self.pdf_output)
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
        self.batch_size.setButtonSymbols(QSpinBox.NoButtons)
        self.batch_size.setRange(1, 100)
        self.batch_size.setValue(config.batch_size)
        self.batch_size.setSuffix(tr("common.segments_per_batch_suffix"))
        form.addRow(tr("settings.batch_size"), self.batch_size)

        self.timeout = QSpinBox()
        self.timeout.setButtonSymbols(QSpinBox.NoButtons)
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
        self._style_form_labels(form)
        return tab

    def _about_tab(self, icon_path):
        tab = QWidget()
        tab.setObjectName("settingsPage")
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
        title.setWordWrap(True)
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
        self._store_current_profile()
        active_id = self.profile_combo.currentData()
        fallback_id = self.fallback_combo.currentData() or ""
        if fallback_id == active_id:
            fallback_id = ""
        return {
            "ui_language": self.ui_language.currentData(),
            "api_keys": dict(self.api_keys),
            "save_key": self.save_key.isChecked(),
            "provider_profiles": list(self.profile_values),
            "active_provider_id": active_id,
            "fallback_provider_id": fallback_id,
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
