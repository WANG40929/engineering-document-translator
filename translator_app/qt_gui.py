from __future__ import annotations

import threading
import os
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from .cache import TranslationCache
from .config import AppConfig, ConfigStore
from .deepseek import DeepSeekTranslator
from .models import LANGUAGES, TranslationOptions
from .pipeline import SUPPORTED_EXTENSIONS, TranslationPipeline, collect_files, write_report
from .secret_store import SecretStore
from .text_utils import load_glossary


class Bridge(QObject):
    progress = Signal(float, str)
    done = Signal(object, str)
    error = Signal(str)


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


class TranslatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("工程文档智能翻译器")
        icon_path = Path(__file__).parent / "assets" / "app_icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1100, 780)
        self.setMinimumSize(880, 620)
        self.config_store, self.secret_store = ConfigStore(), SecretStore()
        self.saved = self.config_store.load()
        self.bridge = Bridge()
        self.bridge.progress.connect(self._on_progress)
        self.bridge.done.connect(self._on_done)
        self.bridge.error.connect(self._on_error)
        self.running = False
        self._build()

    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        layout = QVBoxLayout(root); layout.setContentsMargins(24, 20, 24, 20); layout.setSpacing(14)
        heading = QHBoxLayout()
        icon_label = QLabel(); icon_label.setObjectName("appIcon"); icon_label.setFixedSize(54, 54)
        icon_file = Path(__file__).parent / "assets" / "app_icon.png"
        if icon_file.exists():
            icon_label.setPixmap(QPixmap(str(icon_file)).scaled(46, 46, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title_box = QVBoxLayout(); title_box.setSpacing(2)
        title = QLabel("工程文档智能翻译器"); title.setObjectName("title")
        subtitle = QLabel("保留原有版式 · 仅处理文字层 · 适合工程图纸与技术文件"); subtitle.setObjectName("subtitle")
        title_box.addWidget(title); title_box.addWidget(subtitle)
        version = QLabel("v1.0.0"); version.setObjectName("versionBadge")
        heading.addWidget(icon_label); heading.addLayout(title_box); heading.addStretch(); heading.addWidget(version); layout.addLayout(heading)

        panel = QFrame(); panel.setObjectName("panel"); grid = QGridLayout(panel); grid.setHorizontalSpacing(12); grid.setVerticalSpacing(10); grid.setContentsMargins(16, 14, 16, 14)
        section_title = QLabel("翻译设置"); section_title.setObjectName("sectionTitle"); grid.addWidget(section_title, 0, 0, 1, 6)
        self.key_edit = QLineEdit(self.secret_store.load()); self.key_edit.setEchoMode(QLineEdit.Password)
        self.key_edit.setPlaceholderText("sk-…")
        self.save_key = QCheckBox("在本机加密保存"); self.save_key.setChecked(True)
        grid.addWidget(QLabel("DeepSeek API Key"), 1, 0); grid.addWidget(self.key_edit, 1, 1, 1, 4); grid.addWidget(self.save_key, 1, 5)
        self.source_combo = self._language_combo(True, self.saved.source_language)
        self.target_combo = self._language_combo(False, self.saved.target_language)
        self.model_combo = QComboBox(); self.model_combo.setEditable(True)
        self.model_combo.addItems(["deepseek-v4-flash", "deepseek-v4-pro"])
        self.model_combo.setCurrentText(self.saved.model or "deepseek-v4-flash")
        self.model_combo.setToolTip("Flash：推荐，速度快且成本低；Pro：复杂内容质量优先")
        grid.addWidget(QLabel("源语言"), 2, 0); grid.addWidget(self.source_combo, 2, 1)
        grid.addWidget(QLabel("目标语言"), 2, 2); grid.addWidget(self.target_combo, 2, 3)
        grid.addWidget(QLabel("模型"), 2, 4); grid.addWidget(self.model_combo, 2, 5)
        self.output_edit = QLineEdit(self.saved.output_dir); output_button = QPushButton("选择…"); output_button.clicked.connect(self._choose_output)
        self.output_edit.setPlaceholderText("留空则输出到原文件所在目录")
        grid.addWidget(QLabel("输出目录"), 3, 0); grid.addWidget(self.output_edit, 3, 1, 1, 4); grid.addWidget(output_button, 3, 5)
        self.glossary_edit = QLineEdit(self.saved.glossary_path); glossary_button = QPushButton("选择…"); glossary_button.clicked.connect(self._choose_glossary)
        self.glossary_edit.setPlaceholderText("可选：CSV / TSV / XLSX")
        grid.addWidget(QLabel("术语表"), 4, 0); grid.addWidget(self.glossary_edit, 4, 1, 1, 4); grid.addWidget(glossary_button, 4, 5)
        option_box = QHBoxLayout(); option_box.setSpacing(18)
        self.pure_target = QCheckBox("纯目标语言"); self.pure_target.setChecked(self.saved.pure_target_language)
        self.pure_target.setToolTip("双语原文也只输出目标语言，避免保留 Packing List 等源语言")
        self.quality_review = QCheckBox("自动检查残留源语言"); self.quality_review.setChecked(self.saved.quality_review)
        self.quality_review.setToolTip("对疑似遗漏的普通词和物料名称自动复核一次")
        self.force_refresh = QCheckBox("忽略旧缓存"); self.force_refresh.setChecked(self.saved.force_refresh)
        self.force_refresh.setToolTip("重新调用 DeepSeek，不复用以前保存的译文")
        option_box.addWidget(self.pure_target); option_box.addWidget(self.quality_review); option_box.addWidget(self.force_refresh); option_box.addStretch()
        grid.addWidget(QLabel("质量选项"), 5, 0); grid.addLayout(option_box, 5, 1, 1, 5)
        grid.setColumnStretch(1, 1); grid.setColumnStretch(3, 1); grid.setColumnStretch(5, 1); layout.addWidget(panel)

        list_header = QHBoxLayout(); list_title = QLabel("待处理文件"); list_title.setObjectName("sectionTitle")
        drop_tip = QLabel("支持拖入文件或文件夹"); drop_tip.setObjectName("subtitle")
        list_header.addWidget(list_title); list_header.addStretch(); list_header.addWidget(drop_tip); layout.addLayout(list_header)
        actions = QHBoxLayout(); actions.setSpacing(8)
        for text, slot in (("添加文件", self._add_files), ("添加文件夹", self._add_folder), ("重新处理所选", self._retry_selected), ("移除所选", self._remove), ("清空", self._clear)):
            button = QPushButton(text); button.clicked.connect(slot); actions.addWidget(button)
        actions.addStretch(); layout.addLayout(actions)
        self.table = FileDropTable(0, 4); self.table.setHorizontalHeaderLabels(["状态", "格式", "大小", "文件"])
        self.table.files_dropped.connect(self._handle_dropped)
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True); self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False); self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 90); self.table.setColumnWidth(1, 70); self.table.setColumnWidth(2, 100); layout.addWidget(self.table, 1)

        footer = QHBoxLayout(); progress_box = QVBoxLayout()
        self.progress = QProgressBar(); self.progress.setRange(0, 1000)
        self.status = QLabel("就绪 · 可添加或拖入文档"); self.status.setObjectName("statusText")
        progress_box.addWidget(self.progress); progress_box.addWidget(self.status); footer.addLayout(progress_box, 1)
        self.start_button = QPushButton("开始翻译"); self.start_button.setObjectName("primary"); self.start_button.setMinimumSize(140, 44); self.start_button.clicked.connect(self._start)
        footer.addWidget(self.start_button); layout.addLayout(footer)
        self.setStyleSheet("""
            QWidget { font-family: 'Microsoft YaHei UI'; font-size: 13px; color: #24364b; background: #f4f7fb; }
            #title { font-size: 23px; font-weight: 700; color: #17365d; }
            #subtitle { color: #6b7d90; }
            #sectionTitle { font-size: 14px; font-weight: 700; color: #24496f; }
            #statusText { color: #536b82; }
            #versionBadge { color: #1769c2; background: #e8f2ff; border-radius: 10px; padding: 4px 9px; font-weight: 600; }
            #panel { background: white; border: 1px solid #dce5ee; border-radius: 10px; }
            QLineEdit, QComboBox { min-height: 22px; background: white; border: 1px solid #cbd7e2; border-radius: 6px; padding: 6px 8px; selection-background-color: #2676cf; }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #4388d1; }
            QTableWidget { background: white; alternate-background-color: #f8fafc; border: 1px solid #dce5ee; border-radius: 8px; padding: 0; }
            QPushButton { background: white; border: 1px solid #bdcad6; border-radius: 6px; padding: 7px 13px; }
            QPushButton:hover { background: #edf5ff; border-color: #4f8edc; }
            QPushButton:disabled { color: #9aa8b5; background: #eef1f4; }
            QPushButton#primary { background: #1769c2; color: white; border: none; font-weight: 700; border-radius: 7px; }
            QPushButton#primary:hover { background: #105cad; }
            QProgressBar { min-height: 8px; max-height: 8px; border: none; border-radius: 4px; background: #dfe7ef; text-align: center; color: transparent; }
            QProgressBar::chunk { background: #1d9a9a; border-radius: 4px; }
            QHeaderView::section { background: #edf3f8; color: #40566d; border: none; border-bottom: 1px solid #d6e0e9; padding: 8px; font-weight: 700; }
        """)

    def center_on_active_screen(self):
        """Place the window in the center of the monitor currently in use."""
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if not screen:
            return
        frame = self.frameGeometry()
        frame.moveCenter(screen.availableGeometry().center())
        self.move(frame.topLeft())

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
            status = self.table.item(row, 0).text()
            if pending_only and status in {"已完成", "处理中", "排队中"}:
                continue
            paths.append(Path(self.table.item(row, 3).text()))
        return paths

    def _insert_paths(self, paths):
        existing = {str(path.resolve()) for path in self._paths()}
        for value in paths:
            path = Path(value).resolve()
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS or str(path) in existing: continue
            row = self.table.rowCount(); self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem("待处理"))
            self.table.setItem(row, 1, QTableWidgetItem(path.suffix[1:].upper()))
            self.table.setItem(row, 2, QTableWidgetItem(self._human_size(path.stat().st_size)))
            self.table.setItem(row, 3, QTableWidgetItem(str(path))); existing.add(str(path))

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
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True): self.table.removeRow(row)

    def _retry_selected(self):
        rows = {index.row() for index in self.table.selectedIndexes()}
        for row in rows:
            self.table.item(row, 0).setText("待处理")
        if rows:
            self.status.setText(f"已将 {len(rows)} 个文件重新设为待处理")

    def _clear(self): self.table.setRowCount(0)

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if path: self.output_edit.setText(path)

    def _choose_glossary(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择术语表", "", "术语表 (*.csv *.tsv *.txt *.xlsx);;所有文件 (*.*)")
        if path: self.glossary_edit.setText(path)

    def _start(self):
        if self.running: return
        paths = self._paths(pending_only=True)
        if not paths: QMessageBox.information(self, "没有待处理文件", "列表中的文件都已完成，请添加新文件或把失败文件重新排队。"); return
        key = self.key_edit.text().strip()
        if not key: QMessageBox.warning(self, "缺少 API Key", "请输入 DeepSeek API Key。"); return
        output = Path(self.output_edit.text()) if self.output_edit.text().strip() else None
        glossary = Path(self.glossary_edit.text()) if self.glossary_edit.text().strip() else None
        source, target, model = self.source_combo.currentData(), self.target_combo.currentData(), self.model_combo.currentText().strip()
        self.config_store.save(AppConfig(
            model, source, target, str(output or ""), str(glossary or ""),
            pure_target_language=self.pure_target.isChecked(),
            quality_review=self.quality_review.isChecked(),
            force_refresh=self.force_refresh.isChecked(),
        ))
        if self.save_key.isChecked(): self.secret_store.save(key)
        else: self.secret_store.clear()
        options = TranslationOptions(
            source, target, model, output_dir=output, glossary_path=glossary,
            pure_target_language=self.pure_target.isChecked(),
            quality_review=self.quality_review.isChecked(),
            force_refresh=self.force_refresh.isChecked(),
        )
        pending = {str(path.resolve()) for path in paths}
        for row in range(self.table.rowCount()):
            if str(Path(self.table.item(row, 3).text()).resolve()) in pending:
                self.table.item(row, 0).setText("排队中")
        self.running = True; self.start_button.setEnabled(False); self.progress.setValue(0)
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
            results = TranslationPipeline().run(paths, translator, options, lambda _f, p, m: self.bridge.progress.emit(p, m))
            report = write_report(results, options.output_dir or paths[0].parent)
            self.bridge.done.emit(results, str(report))
        except Exception as exc: self.bridge.error.emit(str(exc))

    def _on_progress(self, fraction, message): self.progress.setValue(round(fraction * 1000)); self.status.setText(message)

    def _on_done(self, results, report):
        self.running = False; self.start_button.setEnabled(True); self.progress.setValue(1000)
        result_by_path = {str(Path(result.input_path).resolve()): result for result in results}
        for row in range(self.table.rowCount()):
            path = str(Path(self.table.item(row, 3).text()).resolve())
            result = result_by_path.get(path)
            if result:
                label = "已完成" if result.status == "completed" else "失败"
                self.table.item(row, 0).setText(label)
        completed = sum(r.status == "completed" for r in results); failed = sum(r.status == "failed" for r in results)
        self.status.setText(f"完成：成功 {completed}，失败 {failed}。报告：{report}")
        QMessageBox.information(self, "翻译完成", f"成功：{completed}\n失败：{failed}\n\n报告：{report}")

    def _on_error(self, message):
        self.running = False; self.start_button.setEnabled(True)
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text() in {"排队中", "处理中"}:
                self.table.item(row, 0).setText("失败")
        self.status.setText("任务失败"); QMessageBox.critical(self, "错误", message)


def main():
    app = QApplication.instance() or QApplication([])
    window = TranslatorWindow(); window.show()
    QTimer.singleShot(0, window.center_on_active_screen)
    if os.environ.get("UDT_SMOKE_TEST") == "1":
        QTimer.singleShot(800, app.quit)
    return app.exec()


if __name__ == "__main__": raise SystemExit(main())
