from __future__ import annotations

import threading
import os
import re
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPolygon
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from . import __version__
from .cache import TranslationCache
from .config import AppConfig, ConfigStore
from .deepseek import DeepSeekTranslator
from .models import LANGUAGES, TranslationOptions
from .pipeline import SUPPORTED_EXTENSIONS, TranslationPipeline, collect_files, write_report
from .secret_store import SecretStore
from .settings_dialog import SettingsDialog
from .text_utils import load_glossary


class Bridge(QObject):
    progress = Signal(str, float, str)
    done = Signal(object, str)
    error = Signal(str)
    stopped = Signal()


class TranslationStopped(Exception):
    """Internal signal used to stop a running batch between API operations."""


class TitleBar(QFrame):
    """Draggable title area for the frameless main window."""

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            window = self.window()
            if hasattr(window, "_toggle_maximize"):
                window._toggle_maximize()
            else:
                window.showNormal() if window.isMaximized() else window.showMaximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ResizeHandle(QWidget):
    """Thin Qt-native resize zone for a frameless window."""

    def __init__(self, edges, cursor, parent=None):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle and handle.startSystemResize(self.edges):
                event.accept()
                return
        super().mousePressEvent(event)


class LineGlyph(QWidget):
    """Crisp vector glyphs matching the approved blue preview."""

    def __init__(self, kind, size=24, color="#1f67e8", parent=None):
        super().__init__(parent)
        self.kind = kind
        self.color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.color, 1.7, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        w, h = self.width(), self.height()
        if self.kind == "clock":
            p.drawEllipse(2, 2, w - 4, h - 4)
            p.drawLine(w // 2, 5, w // 2, h // 2)
            p.drawLine(w // 2, h // 2, w - 6, h // 2 + 3)
        elif self.kind == "trash":
            p.drawRoundedRect(6, 7, w - 12, h - 10, 2, 2)
            p.drawLine(4, 6, w - 4, 6)
            p.drawLine(9, 3, w - 9, 3)
            p.drawLine(10, 10, 10, h - 6)
            p.drawLine(w - 10, 10, w - 10, h - 6)


class SvgGlyph(QWidget):
    """Render a fixed SVG asset without raster scaling or DPI blur."""

    def __init__(self, filename, size, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(str(Path(__file__).parent / "assets" / filename))
        if isinstance(size, tuple):
            self.setFixedSize(*size)
        else:
            self.setFixedSize(size, size)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self.renderer.render(painter, QRectF(self.rect()))


class IconButton(QPushButton):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(38, 38)
        self.setObjectName("iconButton")

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("#1f67e8" if self.underMouse() else "#637083")
        p.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)
        if self.kind == "trash":
            p.drawRoundedRect(13, 13, 12, 16, 2, 2)
            p.drawLine(11, 11, 27, 11)
            p.drawLine(16, 8, 22, 8)
            p.drawLine(17, 16, 17, 25)
            p.drawLine(21, 16, 21, 25)


class SettingsButton(QPushButton):
    """Preview-matched settings control with a vector gear."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("settingsButton")
        self.setFixedSize(92, 38)
        self.renderer = QSvgRenderer(str(Path(__file__).parent / "assets" / "settings.svg"))

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("#1f67e8" if self.underMouse() else "#607087")
        self.renderer.render(p, QRectF(7, 5, 28, 28))
        p.setPen(color)
        p.drawText(39, 0, self.width() - 42, self.height(), Qt.AlignVCenter | Qt.AlignLeft, "设置")


class FileDropTable(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self, rows=0, columns=0, parent=None):
        super().__init__(rows, columns, parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QTableWidget.DropOnly)
        self.setDefaultDropAction(Qt.CopyAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

class DropZone(QFrame):
    files_dropped = Signal(list)
    choose_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(24)
        layout.addStretch(1)
        layout.addWidget(UploadIcon(), 0, Qt.AlignVCenter)
        text_container = QWidget()
        text_container.setFixedHeight(66)
        text_box = QVBoxLayout(text_container)
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(8)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title = QLabel("拖拽文件到此处  或")
        title.setObjectName("dropTitle")
        choose = QPushButton("点击选择文件")
        choose.setObjectName("chooseLink")
        choose.setCursor(Qt.PointingHandCursor)
        choose.clicked.connect(self.choose_requested.emit)
        detail = QLabel("支持 PDF、Word、Excel、CSV 等文档")
        detail.setObjectName("dropDetail")
        title_row.addWidget(title)
        title_row.addWidget(choose)
        title_row.addStretch()
        text_box.addLayout(title_row)
        text_box.addWidget(detail)
        layout.addWidget(text_container, 0, Qt.AlignVCenter)
        layout.addStretch(1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.choose_requested.emit()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()


class UploadIcon(SvgGlyph):
    def __init__(self, parent=None):
        super().__init__("upload-file.svg", 76, parent)


class FileTypeIcon(QWidget):
    def __init__(self, extension, parent=None):
        super().__init__(parent)
        self.extension = extension.upper()
        self.setFixedSize(48, 56)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        color = QColor("#e54955" if self.extension == "PDF" else "#2e6edb" if self.extension in {"DOC", "DOCX"} else "#23936b")
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(4, 2, 40, 52, 4, 4)
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(QPolygon([QPoint(32, 2), QPoint(44, 14), QPoint(32, 14)]))
        p.setPen(QColor("white"))
        font = p.font()
        font.setBold(True)
        font.setPixelSize(11 if self.extension == "PDF" else 15)
        p.setFont(font)
        label = "PDF" if self.extension == "PDF" else "W" if self.extension in {"DOC", "DOCX"} else self.extension[:3]
        p.drawText(4, 22, 40, 27, Qt.AlignCenter, label)


class FileNameCell(QWidget):
    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 6, 5)
        layout.setSpacing(11)
        extension = path.suffix[1:].upper() or "FILE"
        badge = FileTypeIcon(extension)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        name = QLabel(path.name)
        name.setStyleSheet("font-size:14px; font-weight:600; color:#152033;")
        location = QLabel(str(path.parent))
        location.setStyleSheet("font-size:11px; color:#7f8a9b;")
        location.setToolTip(str(path))
        texts.addWidget(name)
        texts.addWidget(location)
        layout.addWidget(badge)
        layout.addLayout(texts, 1)


class TaskProgressCell(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 9, 12, 9)
        layout.setSpacing(7)
        self.detail = QLabel("等待开始")
        self.detail.setStyleSheet("font-size:11px; color:#667085;")
        meter = QHBoxLayout()
        meter.setSpacing(10)
        self.bar = QProgressBar()
        self.bar.setObjectName("taskBar")
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setFormat("")
        self.percent = QLabel("0%")
        self.percent.setObjectName("taskPercent")
        self.percent.setFixedWidth(42)
        self.percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.detail)
        meter.addWidget(self.bar, 1)
        meter.addWidget(self.percent)
        layout.addLayout(meter)

    def set_progress(self, fraction: float, text: str = ""):
        fraction = min(1.0, max(0.0, float(fraction)))
        self.bar.setValue(round(fraction * 1000))
        self.detail.setText(text or f"{fraction * 100:.1f}%")
        self.percent.setText(f"{fraction * 100:.0f}%")


class StatusCell(QWidget):
    COLORS = {
        "待处理": "#98a2b3", "排队中": "#98a2b3",
        "翻译中": "#1f67e8", "处理中": "#1f67e8",
        "已完成": "#16865c", "失败": "#d14343",
    }
    DISPLAY = {"待处理": "等待中", "排队中": "等待中"}

    def __init__(self, text="待处理", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(7)
        self.dot = QLabel()
        self.dot.setFixedSize(8, 8)
        self.label = QLabel()
        layout.addWidget(self.dot)
        layout.addWidget(self.label)
        layout.addStretch()
        self.set_status(text)

    def set_status(self, text):
        color = self.COLORS.get(text, "#98a2b3")
        self.dot.setStyleSheet(f"background:{color}; border-radius:4px;")
        self.label.setText(self.DISPLAY.get(text, text))
        self.label.setStyleSheet(f"color:{color}; font-weight:600;")

class TranslatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle("文档智能翻译器")
        icon_path = Path(__file__).parent / "assets" / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1080, 700)
        self.setMinimumSize(900, 620)
        self.config_store, self.secret_store = ConfigStore(), SecretStore()
        self.saved = self.config_store.load()
        self.api_key = self.secret_store.load()
        self.save_key_enabled = bool(self.api_key)
        self.bridge = Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.done.connect(self._on_done)
        self.bridge.error.connect(self._on_error)
        self.bridge.stopped.connect(self._on_stopped)
        self.running = False
        self.stop_requested = False
        self.task_started = 0.0
        self.progress_fraction = 0.0
        self.progress_message = ""
        self.progress_rate = 0.0
        self.progress_sample_time = 0.0
        self.progress_sample_fraction = 0.0
        self.progress_timer = QTimer(self)
        self.progress_timer.setInterval(1000)
        self.progress_timer.timeout.connect(self._refresh_progress_text)
        self._build()

    def _build(self):
        root = QWidget()
        root.setObjectName("windowFrame")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        title_bar = TitleBar()
        title_bar.setObjectName("titleBar")
        title_bar.setFixedHeight(108)
        heading = QHBoxLayout(title_bar)
        heading.setContentsMargins(22, 16, 14, 13)
        heading.setSpacing(14)
        icon_label = SvgGlyph("header-mark.svg", (58, 70))
        icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("文档智能翻译器")
        title.setObjectName("title")
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        subtitle = QLabel("保留版式的多格式文档批量翻译工具")
        subtitle.setObjectName("subtitle")
        subtitle.setAttribute(Qt.WA_TransparentForMouseEvents)
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        version = QLabel(f"v{__version__}")
        version.setObjectName("versionBadge")
        version.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.settings_button = SettingsButton()
        self.settings_button.clicked.connect(self._open_settings)
        heading.addWidget(icon_label)
        heading.addLayout(title_box)
        heading.addWidget(version, 0, Qt.AlignVCenter)
        heading.addStretch()

        right_box = QVBoxLayout()
        right_box.setSpacing(8)
        controls = QHBoxLayout()
        controls.setSpacing(0)
        controls.addStretch()
        self.min_button = QPushButton("−")
        self.max_button = QPushButton("□")
        self.close_button = QPushButton("×")
        for button in (self.min_button, self.max_button, self.close_button):
            button.setObjectName("windowButton")
            button.setFixedSize(42, 30)
        self.close_button.setObjectName("closeButton")
        self.min_button.clicked.connect(self.showMinimized)
        self.max_button.clicked.connect(self._toggle_maximize)
        self.close_button.clicked.connect(self.close)
        controls.addWidget(self.min_button)
        controls.addWidget(self.max_button)
        controls.addWidget(self.close_button)
        right_box.addLayout(controls)
        right_box.addWidget(self.settings_button, 0, Qt.AlignRight)
        heading.addLayout(right_box)
        layout.addWidget(title_bar)

        body = QWidget()
        body.setObjectName("body")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(22, 0, 22, 18)
        body_layout.setSpacing(20)

        summary = QFrame()
        summary.setObjectName("summaryPanel")
        summary.setFixedHeight(64)
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(58, 8, 58, 8)
        summary_layout.setSpacing(18)
        self.source_combo = self._language_combo(True, self.saved.source_language)
        self.target_combo = self._language_combo(False, self.saved.target_language)
        language_group = QWidget()
        language_box = QHBoxLayout(language_group)
        language_box.setContentsMargins(0, 0, 0, 0)
        language_box.setSpacing(5)
        language_box.addStretch()
        language_box.addWidget(SvgGlyph("language.svg", 22))
        language_box.addWidget(self.source_combo)
        arrow = QLabel("→")
        arrow.setObjectName("summaryIcon")
        arrow.setFixedWidth(18)
        arrow.setAlignment(Qt.AlignCenter)
        language_box.addWidget(arrow)
        language_box.addWidget(self.target_combo)
        language_box.addStretch()
        summary_layout.addWidget(language_group, 3)
        summary_layout.addWidget(self._separator())
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItem("DeepSeek V4 Flash", "deepseek-v4-flash")
        self.model_combo.addItem("DeepSeek V4 Pro", "deepseek-v4-pro")
        saved_model_index = self.model_combo.findData(self.saved.model or "deepseek-v4-flash")
        if saved_model_index >= 0:
            self.model_combo.setCurrentIndex(saved_model_index)
        else:
            self.model_combo.setCurrentText(self.saved.model)
        self.model_combo.setToolTip("Flash：推荐，速度快且成本低；Pro：复杂内容质量优先")
        model_group = QWidget()
        model_box = QHBoxLayout(model_group)
        model_box.setContentsMargins(0, 0, 0, 0)
        model_box.setSpacing(5)
        model_box.addStretch()
        model_box.addWidget(SvgGlyph("brain.svg", 24))
        model_box.addWidget(self.model_combo)
        model_box.addStretch()
        summary_layout.addWidget(model_group, 3)
        summary_layout.addWidget(self._separator())
        self.output_edit = QLineEdit(self.saved.output_dir)
        self.output_edit.hide()
        self.output_button = QPushButton()
        self.output_button.setObjectName("summaryButton")
        self.output_button.clicked.connect(self._choose_output)
        self._update_output_button()
        output_group = QWidget()
        output_box = QHBoxLayout(output_group)
        output_box.setContentsMargins(0, 0, 0, 0)
        output_box.setSpacing(10)
        output_box.addStretch()
        output_box.addWidget(SvgGlyph("folder.svg", 24))
        output_box.addWidget(self.output_button)
        output_box.addStretch()
        summary_layout.addWidget(output_group, 2)
        body_layout.addWidget(summary)

        self.drop_zone = DropZone()
        self.drop_zone.setFixedHeight(194)
        self.drop_zone.files_dropped.connect(self._handle_dropped)
        self.drop_zone.choose_requested.connect(self._add_files)
        body_layout.addWidget(self.drop_zone)

        self.table = FileDropTable(0, 6)
        self.table.setHorizontalHeaderLabels(["文件任务（0）", "页数 / 大小", "状态", "进度", "操作", "路径"])
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.hideColumn(5)
        self.table.files_dropped.connect(self._handle_dropped)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(84)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(4, 78)
        body_layout.addWidget(self.table)
        body_layout.addStretch(1)
        layout.addWidget(body, 1)

        footer = QFrame()
        footer.setObjectName("footer")
        footer.setFixedHeight(88)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(24, 14, 22, 14)
        footer_layout.setSpacing(14)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFormat("")
        self.progress.hide()
        footer_layout.addWidget(LineGlyph("clock", 26, "#637083"))
        self.status = QLabel("就绪 · 可添加或拖入文档")
        self.status.setObjectName("statusText")
        footer_layout.addWidget(self.status, 1)
        self.stop_button = QPushButton("停止")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setFixedSize(144, 52)
        self.stop_button.clicked.connect(self._request_stop)
        self.stop_button.hide()
        footer_layout.addWidget(self.stop_button)
        self.start_button = QPushButton("开始翻译")
        self.start_button.setObjectName("primary")
        self.start_button.setFixedSize(180, 52)
        self.start_button.clicked.connect(self._start)
        footer_layout.addWidget(self.start_button)
        layout.addWidget(footer)

        self.setStyleSheet("""
            #windowFrame { background: #ffffff; border: 1px solid #d8dee8; }
            #body, #titleBar { background: #ffffff; }
            QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #182131; }
            #title { font-size: 25px; font-weight: 700; color: #172033; }
            #subtitle { color: #687588; font-size: 13px; }
            #versionBadge { color: #536174; background: #f6f8fb; border: 1px solid #d7dee8; border-radius: 6px; padding: 3px 7px; }
            #summaryPanel { background: #ffffff; border: 1px solid #dce2eb; border-radius: 6px; }
            #summaryPanel QComboBox { min-height: 28px; background: transparent; border: none; padding: 2px 5px; font-size: 14px; }
            #summaryButton { min-height: 26px; text-align: left; background: transparent; border: none; color: #23324a; padding: 1px 4px; font-weight: 600; }
            #summaryButton:hover { color: #1f67e8; }
            #summaryIcon { color: #647184; font-size: 18px; }
            #dropZone { background: #ffffff; border: 1px dashed #9ba9bd; border-radius: 7px; }
            #dropZone:hover { background: #fbfdff; border-color: #1f67e8; }
            #dropTitle { color: #202a3b; font-size: 16px; }
            QPushButton#chooseLink { color: #1f67e8; background: transparent; border: none; padding: 0; font-size: 16px; }
            QPushButton#chooseLink:hover { color: #1558ce; background: transparent; border: none; }
            #dropDetail { color: #748094; font-size: 13px; }
            #statusText { color: #263142; font-size: 14px; }
            QTableWidget { background: white; border: 1px solid #dce2eb; border-radius: 6px; selection-background-color: #f7f9fd; selection-color: #172033; }
            QTableWidget::item { border-bottom: 1px solid #e5e9f0; padding: 8px; }
            QHeaderView::section { background: #ffffff; color: #596679; border: none; border-bottom: 1px solid #dce2eb; padding: 12px; font-weight: 500; }
            QPushButton { background: white; border: 1px solid #d3dae5; border-radius: 6px; padding: 7px 13px; }
            QPushButton:hover { background: #f6f8fc; border-color: #91a9e4; }
            QPushButton:disabled { color: #a2aab5; background: #f0f2f5; border-color: #e1e4e8; }
            QPushButton#settingsButton { border: none; background: transparent; padding: 0; }
            QPushButton#settingsButton:hover { background: #f4f7fd; }
            QPushButton#windowButton, QPushButton#closeButton { border: none; border-radius: 0; background: transparent; font-size: 18px; padding: 0; }
            QPushButton#windowButton:hover { background: #f0f3f7; }
            QPushButton#closeButton:hover { background: #e5484d; color: white; }
            QPushButton#iconButton { border: none; background: transparent; padding: 0; }
            QPushButton#iconButton:hover { background: #f1f5fb; }
            #footer { background: #ffffff; border-top: 1px solid #dce2eb; }
            QPushButton#primary { background: #1f67e8; color: white; border: none; font-weight: 600; border-radius: 5px; font-size: 15px; }
            QPushButton#primary:hover { background: #1558ce; }
            QPushButton#stopButton { background: #ffffff; color: #263142; border: 1px solid #aeb9c9; border-radius: 5px; font-size: 15px; }
            QPushButton#stopButton:hover { background: #f6f8fb; border-color: #78879b; }
            QProgressBar { min-height: 8px; max-height: 8px; border: none; border-radius: 4px; background: #e4e8ee; color: transparent; }
            QProgressBar::chunk { background: #1f67e8; border-radius: 4px; }
            QProgressBar#rowProgress { min-height: 16px; max-height: 16px; color: #5d6978; text-align: center; font-size: 11px; }
            QProgressBar#taskBar { min-height: 7px; max-height: 7px; background: #e7eaf0; }
            #taskPercent { color: #5f6c7d; font-size: 12px; }
        """)
        self._fit_combo_to_text(self.source_combo, 86, 150)
        self._fit_combo_to_text(self.target_combo, 94, 150)
        self._fit_combo_to_text(self.model_combo, 164, 250)
        self._update_file_count()
        self._create_resize_handles(root)

    def _create_resize_handles(self, parent):
        self.resize_handles = {
            "left": ResizeHandle(Qt.LeftEdge, Qt.SizeHorCursor, parent),
            "right": ResizeHandle(Qt.RightEdge, Qt.SizeHorCursor, parent),
            "top": ResizeHandle(Qt.TopEdge, Qt.SizeVerCursor, parent),
            "bottom": ResizeHandle(Qt.BottomEdge, Qt.SizeVerCursor, parent),
            "top_left": ResizeHandle(Qt.TopEdge | Qt.LeftEdge, Qt.SizeFDiagCursor, parent),
            "top_right": ResizeHandle(Qt.TopEdge | Qt.RightEdge, Qt.SizeBDiagCursor, parent),
            "bottom_left": ResizeHandle(Qt.BottomEdge | Qt.LeftEdge, Qt.SizeBDiagCursor, parent),
            "bottom_right": ResizeHandle(Qt.BottomEdge | Qt.RightEdge, Qt.SizeFDiagCursor, parent),
        }
        self._position_resize_handles()

    def _position_resize_handles(self):
        if not hasattr(self, "resize_handles"):
            return
        width, height = self.width(), self.height()
        edge, corner = 7, 14
        geometries = {
            "left": (0, corner, edge, max(0, height - 2 * corner)),
            "right": (width - edge, corner, edge, max(0, height - 2 * corner)),
            "top": (corner, 0, max(0, width - 2 * corner), edge),
            "bottom": (corner, height - edge, max(0, width - 2 * corner), edge),
            "top_left": (0, 0, corner, corner),
            "top_right": (width - corner, 0, corner, corner),
            "bottom_left": (0, height - corner, corner, corner),
            "bottom_right": (width - corner, height - corner, corner, corner),
        }
        visible = not self.isMaximized()
        for name, handle in self.resize_handles.items():
            handle.setGeometry(*geometries[name])
            handle.setVisible(visible)
            handle.raise_()

    @staticmethod
    def _separator():
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setStyleSheet("color:#e2e6eb;")
        return line

    @staticmethod
    def _fit_combo_to_text(combo, minimum, maximum):
        """Keep the native arrow close while reserving enough room for all text."""
        def update_width(text):
            required = combo.fontMetrics().horizontalAdvance(text or " ") + 38
            combo.setFixedWidth(max(minimum, min(maximum, required)))

        combo.currentTextChanged.connect(update_width)
        update_width(combo.currentText())

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.max_button.setText("□")
        else:
            self.showMaximized()
            self.max_button.setText("❐")

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange and hasattr(self, "max_button"):
            self.max_button.setText("❐" if self.isMaximized() else "□")
            QTimer.singleShot(0, self._position_resize_handles)
        super().changeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_resize_handles()

    @staticmethod
    def _field_box(label_text, control):
        box = QVBoxLayout()
        box.setSpacing(2)
        label = QLabel(label_text)
        label.setObjectName("fieldLabel")
        box.addWidget(label)
        box.addWidget(control)
        return box

    def _update_output_button(self):
        value = self.output_edit.text().strip()
        if not value:
            label = "原文件所在目录"
        else:
            path = Path(value)
            label = path.name or str(path)
        self.output_button.setText(f"输出到：{label}")
        self.output_button.setToolTip(value or "翻译结果保存在原文件所在目录")

    def _open_settings(self):
        dialog = SettingsDialog(self.saved, self.api_key, self.save_key_enabled, self)
        if not dialog.exec():
            return
        values = dialog.values()
        self.api_key = values["api_key"]
        self.save_key_enabled = values["save_key"]
        self.saved.glossary_path = values["glossary_path"]
        self.saved.pure_target_language = values["pure_target_language"]
        self.saved.quality_review = values["quality_review"]
        self.saved.force_refresh = values["force_refresh"]
        self.saved.batch_size = values["batch_size"]
        self.saved.request_timeout = values["request_timeout"]
        self.saved.model = self.model_combo.currentData() or self.model_combo.currentText().strip()
        self.saved.source_language = self.source_combo.currentData()
        self.saved.target_language = self.target_combo.currentData()
        self.saved.output_dir = self.output_edit.text().strip()
        self.config_store.save(self.saved)
        if self.save_key_enabled and self.api_key:
            self.secret_store.save(self.api_key)
        else:
            self.secret_store.clear()
        self.status.setText("设置已保存")

    def center_on_active_screen(self):
        """Place the window in the center of the monitor currently in use."""
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

    def showEvent(self, event):
        """Center after Windows has applied DPI scaling and the real frame size."""
        super().showEvent(event)
        if not getattr(self, "_initial_center_done", False):
            self._initial_center_done = True
            QTimer.singleShot(30, self.center_on_active_screen)

    def _language_combo(self, allow_auto, selected):
        combo = QComboBox()
        for code, label in LANGUAGES.items():
            if allow_auto or code != "auto": combo.addItem(label, code)
        index = combo.findData(selected); combo.setCurrentIndex(max(0, index)); return combo

    @staticmethod
    def _human_size(value):
        for unit in ("B", "KB", "MB", "GB"):
            if value < 1024 or unit == "GB": return f"{value:.1f} {unit}"
            value /= 1024

    def _paths(self, pending_only=False):
        paths = []
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 2).data(Qt.UserRole) or "待处理"
            if pending_only and status in {"已完成", "处理中", "排队中"}:
                continue
            paths.append(Path(self.table.item(row, 5).text()))
        return paths

    def _insert_paths(self, paths):
        existing = {str(path.resolve()) for path in self._paths()}
        for value in paths:
            path = Path(value).resolve()
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS or str(path) in existing: continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            name = QTableWidgetItem(path.name)
            name.setToolTip(str(path))
            name.setText("")
            self.table.setItem(row, 0, name)
            self.table.setCellWidget(row, 0, FileNameCell(path))
            self.table.setItem(row, 1, QTableWidgetItem(self._human_size(path.stat().st_size)))
            status_item = QTableWidgetItem("")
            status_item.setData(Qt.UserRole, "待处理")
            self.table.setItem(row, 2, status_item)
            self.table.setCellWidget(row, 2, StatusCell("待处理"))
            self.table.setCellWidget(row, 3, TaskProgressCell())
            remove = IconButton("trash")
            remove.setToolTip("移除")
            remove.clicked.connect(lambda _checked=False, value=str(path): self._remove_path(value))
            self.table.setCellWidget(row, 4, remove)
            self.table.setItem(row, 5, QTableWidgetItem(str(path)))
            existing.add(str(path))
        self._update_file_count()

    def _update_file_count(self):
        count = self.table.rowCount()
        header_item = self.table.horizontalHeaderItem(0)
        if header_item:
            header_item.setText(f"文件任务（{count}）")
        visible_rows = min(max(count, 2), 4)
        self.table.setFixedHeight(68 + visible_rows * 84)
        self.start_button.setEnabled(not self.running and self.table.rowCount() > 0)

    def _remove_path(self, value):
        target = str(Path(value).resolve())
        for row in range(self.table.rowCount() - 1, -1, -1):
            if str(Path(self.table.item(row, 5).text()).resolve()) == target:
                self.table.removeRow(row)
        self._update_file_count()

    def _set_row_progress(self, row, fraction, text=""):
        cell = self.table.cellWidget(row, 3)
        if not isinstance(cell, TaskProgressCell):
            return
        cell.set_progress(fraction, text)

    def _set_row_status(self, row, text):
        item = self.table.item(row, 2)
        if item:
            item.setText("")
            item.setData(Qt.UserRole, text)
        cell = self.table.cellWidget(row, 2)
        if isinstance(cell, StatusCell):
            cell.set_status(text)

    def _handle_dropped(self, dropped_paths):
        files = []
        for value in dropped_paths:
            path = Path(value)
            if path.is_dir():
                files.extend(collect_files(path))
            elif path.is_file():
                files.append(path)
        before = self.table.rowCount()
        self._insert_paths(files)
        added = self.table.rowCount() - before
        self.status.setText(f"拖入成功：新增 {added} 个文件")

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择文档", "", "支持的文档 (*.pdf *.docx *.doc *.xlsx *.xlsm *.csv *.tsv);;所有文件 (*.*)")
        self._insert_paths(paths)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            paths = collect_files(Path(folder)); self._insert_paths(paths); self.status.setText(f"已找到 {len(paths)} 个支持的文件")

    def _remove(self):
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)
        self._update_file_count()

    def _retry_selected(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        for row in rows:
            self._set_row_status(row, "待处理")
            self._set_row_progress(row, 0, "等待")
        if rows:
            self.status.setText(f"已将 {len(rows)} 个文件重新设为待处理")

    def _clear(self):
        self.table.setRowCount(0)
        self._update_file_count()

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path:
            self.output_edit.setText(path)
            self._update_output_button()

    def _start(self):
        if self.running: return
        paths = self._paths(pending_only=True)
        if not paths: QMessageBox.information(self, "没有待处理文件", "列表中的文件都已完成，请添加新文件或把失败文件重新排队。"); return
        key = self.api_key.strip()
        if not key:
            self._open_settings()
            key = self.api_key.strip()
        if not key: QMessageBox.warning(self, "缺少 API Key", "请在设置中输入 DeepSeek API Key。"); return
        output = Path(self.output_edit.text()) if self.output_edit.text().strip() else None
        glossary = Path(self.saved.glossary_path) if self.saved.glossary_path.strip() else None
        source, target = self.source_combo.currentData(), self.target_combo.currentData()
        model = self.model_combo.currentData() or self.model_combo.currentText().strip()
        self.saved.model = model
        self.saved.source_language = source
        self.saved.target_language = target
        self.saved.output_dir = str(output or "")
        self.config_store.save(self.saved)
        if self.save_key_enabled: self.secret_store.save(key)
        else: self.secret_store.clear()
        options = TranslationOptions(
            source, target, model, output_dir=output, glossary_path=glossary,
            batch_size=self.saved.batch_size,
            request_timeout=self.saved.request_timeout,
            pure_target_language=self.saved.pure_target_language,
            quality_review=self.saved.quality_review,
            force_refresh=self.saved.force_refresh,
        )
        pending = {str(path.resolve()) for path in paths}
        for row in range(self.table.rowCount()):
            if str(Path(self.table.item(row, 5).text()).resolve()) in pending:
                self._set_row_status(row, "排队中")
                self._set_row_progress(row, 0, "等待")
        self.stop_requested = False
        self.running = True; self.start_button.setEnabled(False); self.progress.setValue(0)
        self.settings_button.setEnabled(False)
        self.stop_button.setText("停止")
        self.stop_button.setEnabled(True)
        self.stop_button.show()
        self.task_started = time.monotonic()
        self.progress_fraction = 0.0
        self.progress_message = "正在分析文档"
        self.progress_rate = 0.0
        self.progress_sample_time = self.task_started
        self.progress_sample_fraction = 0.0
        self.progress_timer.start()
        self._refresh_progress_text()
        threading.Thread(target=self._worker, args=(paths, key, options), daemon=True).start()

    def _worker(self, paths, key, options):
        try:
            translator = DeepSeekTranslator(
                key, options.model, options.source_language, options.target_language,
                load_glossary(options.glossary_path), TranslationCache(), options.request_timeout, options.batch_size,
                pure_target_language=options.pure_target_language,
                quality_review=options.quality_review,
                force_refresh=options.force_refresh,
            )
            def publish_progress(file_path, fraction, message):
                if self.stop_requested:
                    raise TranslationStopped()
                self.bridge.progress.emit(file_path, fraction, message)

            results = TranslationPipeline().run(paths, translator, options, publish_progress)
            if self.stop_requested:
                raise TranslationStopped()
            report = write_report(results, options.output_dir or paths[0].parent)
            self.bridge.done.emit(results, str(report))
        except TranslationStopped:
            self.bridge.stopped.emit()
        except Exception as exc: self.bridge.error.emit(str(exc))

    def _request_stop(self):
        if not self.running or self.stop_requested:
            return
        self.stop_requested = True
        self.stop_button.setEnabled(False)
        self.stop_button.setText("正在停止…")
        self.status.setText("正在停止 · 当前接口请求结束后停止任务")

    @staticmethod
    def _duration_text(seconds):
        seconds = max(0, int(round(seconds)))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}小时{minutes:02d}分"
        if minutes:
            return f"{minutes}分{seconds:02d}秒"
        return f"{seconds}秒"

    def _on_progress(self, file_path, fraction, message):
        now = time.monotonic()
        fraction = min(1.0, max(self.progress_fraction, float(fraction)))
        elapsed = now - self.progress_sample_time
        advanced = fraction - self.progress_sample_fraction
        if elapsed >= 0.5 and advanced > 0:
            rate = advanced / elapsed
            self.progress_rate = rate if self.progress_rate <= 0 else self.progress_rate * 0.72 + rate * 0.28
            self.progress_sample_time = now
            self.progress_sample_fraction = fraction
        self.progress_fraction = fraction
        self.progress_message = message
        self.progress.setValue(round(fraction * 1000))
        if file_path:
            target = str(Path(file_path).resolve())
            for row in range(self.table.rowCount()):
                if str(Path(self.table.item(row, 5).text()).resolve()) != target:
                    continue
                self._set_row_status(row, "翻译中")
                segment = re.search(r"(\d+)\s*/\s*(\d+)\s*段", message)
                page = re.search(r"第\s*(\d+)\s*/\s*(\d+)\s*页", message)
                if segment and int(segment.group(2)):
                    local = int(segment.group(1)) / int(segment.group(2))
                elif page and int(page.group(2)):
                    local = int(page.group(1)) / int(page.group(2))
                else:
                    local = fraction if len(self._paths()) == 1 else 0.0
                detail = message
                if "第" in detail:
                    detail = detail[detail.find("第"):]
                self._set_row_progress(row, local, detail)
                self.table.cellWidget(row, 3).setToolTip(message)
                break
        self._refresh_progress_text()

    def _refresh_progress_text(self):
        if not self.running or not self.task_started:
            return
        elapsed = time.monotonic() - self.task_started
        if self.progress_rate > 0 and self.progress_fraction < 1:
            remaining = (1.0 - self.progress_fraction) / self.progress_rate
            eta = f"预计剩余约 {self._duration_text(remaining)}"
        else:
            eta = "预计剩余时间计算中"
        percent = round(self.progress_fraction * 100, 1)
        self.status.setText(
            f"{self.progress_message} · {percent}% · 已用时 {self._duration_text(elapsed)} · {eta}"
        )

    def _on_done(self, results, report):
        self.progress_timer.stop()
        self.running = False; self.start_button.setEnabled(True); self.settings_button.setEnabled(True)
        self.stop_requested = False
        self.stop_button.hide()
        result_by_path = {str(Path(result.input_path).resolve()): result for result in results}
        for row in range(self.table.rowCount()):
            path = str(Path(self.table.item(row, 5).text()).resolve())
            result = result_by_path.get(path)
            if result:
                label = "已完成" if result.status == "completed" else "失败"
                self._set_row_status(row, label)
                if result.status == "completed":
                    self._set_row_progress(row, 1.0, "100%")
        completed = sum(r.status == "completed" for r in results); failed = sum(r.status == "failed" for r in results)
        if not failed:
            self.progress_fraction = 1.0
            self.progress.setValue(1000)
        self.status.setText(f"完成：成功 {completed}，失败 {failed}。报告：{report}")
        QMessageBox.information(self, "翻译完成", f"成功：{completed}\n失败：{failed}\n\n报告：{report}")

    def _on_error(self, message):
        self.progress_timer.stop()
        self.running = False; self.start_button.setEnabled(True); self.settings_button.setEnabled(True)
        self.stop_requested = False
        self.stop_button.hide()
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 2).data(Qt.UserRole)
            if status in {"排队中", "处理中", "翻译中"}:
                self._set_row_status(row, "失败")
        self.status.setText("任务失败"); QMessageBox.critical(self, "错误", message)

    def _on_stopped(self):
        self.progress_timer.stop()
        self.running = False
        self.stop_requested = False
        self.stop_button.hide()
        self.settings_button.setEnabled(True)
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 2).data(Qt.UserRole)
            if status in {"排队中", "处理中", "翻译中", "失败"}:
                self._set_row_status(row, "待处理")
        self._update_file_count()
        self.status.setText("任务已停止 · 未完成文件可重新开始")


def main():
    app = QApplication.instance() or QApplication([])
    window = TranslatorWindow(); window.show()
    QTimer.singleShot(0, window.center_on_active_screen)
    if os.environ.get("UDT_SMOKE_TEST") == "1":
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__": raise SystemExit(main())
