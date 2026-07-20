from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
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


class SettingsDialog(QDialog):
    """Compact settings window with a product introduction tab."""

    def __init__(self, config: AppConfig, api_key: str, save_key: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(640, 520)
        icon_path = Path(__file__).parent / "assets" / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(14)
        tabs = QTabWidget()
        tabs.addTab(self._translation_tab(config, api_key, save_key), "翻译设置")
        tabs.addTab(self._advanced_tab(config), "高级")
        header_icon = Path(__file__).parent / "assets" / "header-mark.svg"
        tabs.addTab(self._about_tab(header_icon if header_icon.exists() else icon_path), "介绍")
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet("""
            QDialog { background: #f5f7fb; color: #152033; }
            QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; }
            QTabWidget::pane { background: white; border: 1px solid #e2e8f0; border-radius: 12px; top: -1px; }
            QTabBar::tab { padding: 10px 20px; color: #718096; border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: #1f67e8; border-bottom-color: #1f67e8; font-weight: 700; }
            QLineEdit, QSpinBox { min-height: 26px; padding: 6px 9px; background: white; border: 1px solid #d8e0eb; border-radius: 8px; }
            QLineEdit:focus, QSpinBox:focus { border-color: #7d9dec; }
            QPushButton { min-height: 28px; padding: 6px 15px; background: white; border: 1px solid #d7dee8; border-radius: 8px; }
            QPushButton:hover { border-color: #91a9e4; background: #f4f7ff; }
            QDialogButtonBox QPushButton[text="保存"] { background:#1f67e8; color:white; border:none; font-weight:700; }
        """)

    def _translation_tab(self, config, api_key, save_key):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(22, 24, 22, 22)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self.key_edit = QLineEdit(api_key)
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…")
        self.save_key = QCheckBox("使用 Windows 加密保存在本机")
        self.save_key.setChecked(save_key)
        key_box = QVBoxLayout()
        key_box.setSpacing(6)
        key_box.addWidget(self.key_edit)
        key_box.addWidget(self.save_key)
        form.addRow("DeepSeek API Key", key_box)

        self.glossary_edit = QLineEdit(config.glossary_path)
        self.glossary_edit.setPlaceholderText("可选：CSV / TSV / XLSX")
        choose = QPushButton("选择…")
        choose.clicked.connect(self._choose_glossary)
        glossary_row = QHBoxLayout()
        glossary_row.addWidget(self.glossary_edit, 1)
        glossary_row.addWidget(choose)
        form.addRow("术语表", glossary_row)

        self.pure_target = QCheckBox("纯目标语言")
        self.pure_target.setChecked(config.pure_target_language)
        self.quality_review = QCheckBox("自动检查残留源语言")
        self.quality_review.setChecked(config.quality_review)
        self.force_refresh = QCheckBox("忽略旧缓存并重新翻译")
        self.force_refresh.setChecked(config.force_refresh)
        options = QVBoxLayout()
        options.setSpacing(9)
        options.addWidget(self.pure_target)
        options.addWidget(self.quality_review)
        options.addWidget(self.force_refresh)
        form.addRow("质量选项", options)
        return tab

    def _advanced_tab(self, config):
        tab = QWidget()
        form = QFormLayout(tab)
        form.setContentsMargins(22, 24, 22, 22)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(14)

        self.batch_size = QSpinBox()
        self.batch_size.setRange(1, 100)
        self.batch_size.setValue(config.batch_size)
        self.batch_size.setSuffix(" 段/批")
        form.addRow("批量大小", self.batch_size)

        self.timeout = QSpinBox()
        self.timeout.setRange(30, 600)
        self.timeout.setValue(config.request_timeout)
        self.timeout.setSuffix(" 秒")
        form.addRow("接口超时", self.timeout)

        cache_path = app_data_dir() / "translations.sqlite3"
        cache_size = cache_path.stat().st_size / (1024 * 1024) if cache_path.exists() else 0
        cache = QLabel(
            f"当前约 {cache_size:.1f} MB\n上限 100 MB，超过后自动按时间清理最早的记录。"
        )
        cache.setWordWrap(True)
        cache.setStyleSheet("color:#667085; line-height:1.45;")
        form.addRow("翻译缓存", cache)
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
        title = QLabel("文档智能翻译器")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:20px; font-weight:700; color:#172033;")
        layout.addWidget(title)
        version = QLabel(f"Document Translator · v{__version__}")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color:#667085;")
        layout.addWidget(version)

        intro = QLabel(
            "用于批量翻译带文字层的 PDF、Word、Excel 与 CSV 文档，"
            "尽量保留原有版式、表格、图片、数字、单位和技术编号。\n\n"
            "支持格式：PDF、DOCX、DOC、XLSX、XLSM、CSV、TSV。\n"
            "隐私说明：文件在本机解析，仅待翻译文字发送到所配置的 DeepSeek API；API Key 可使用 Windows 加密保存。"
        )
        intro.setWordWrap(True)
        intro.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        intro.setStyleSheet("color:#465263; line-height:1.55; background:#f8faff; border:1px solid #e1e8f5; border-radius:10px; padding:15px;")
        layout.addWidget(intro)

        link = QLabel('<a href="https://github.com/WANG40929/engineering-document-translator">访问 GitHub 项目主页</a>')
        link.setOpenExternalLinks(True)
        link.setAlignment(Qt.AlignCenter)
        layout.addWidget(link)
        layout.addStretch()
        return tab

    def _choose_glossary(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择术语表", "", "术语表 (*.csv *.tsv *.txt *.xlsx);;所有文件 (*.*)"
        )
        if path:
            self.glossary_edit.setText(path)

    def values(self) -> dict:
        return {
            "api_key": self.key_edit.text().strip(),
            "save_key": self.save_key.isChecked(),
            "glossary_path": self.glossary_edit.text().strip(),
            "pure_target_language": self.pure_target.isChecked(),
            "quality_review": self.quality_review.isChecked(),
            "force_refresh": self.force_refresh.isChecked(),
            "batch_size": self.batch_size.value(),
            "request_timeout": self.timeout.value(),
        }
