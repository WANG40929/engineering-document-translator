from __future__ import annotations

import json
import csv
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import fitz

from ..models import FileResult, TranslationOptions
from .base import TranslationEngine


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%")
STAGE_NAMES = {
    "Parse PDF and Create Intermediate Representation": "解析 PDF",
    "DetectScannedFile": "检测扫描页面",
    "Parse Page Layout": "识别页面布局",
    "Parse Paragraphs": "重建段落",
    "Extract Terms": "提取术语",
    "Translate Paragraphs": "翻译段落",
    "Typesetting": "智能排版",
    "Add Fonts": "匹配字体",
    "Generate drawing instructions": "生成页面",
    "Subset font": "整理字体",
    "Save PDF": "保存 PDF",
}
STAGE_MILESTONES = {
    "Parse PDF and Create Intermediate Representation": 0.04,
    "DetectScannedFile": 0.14,
    "Parse Page Layout": 0.18,
    "Parse Paragraphs": 0.31,
    "Extract Terms": 0.38,
    "Translate Paragraphs": 0.48,
    "Typesetting": 0.82,
    "Add Fonts": 0.87,
    "Generate drawing instructions": 0.90,
    "Subset font": 0.94,
    "Save PDF": 0.97,
}


class BabelDocEngine(TranslationEngine):
    """Run the official BabelDOC layout engine as an isolated backend."""

    extensions = (".pdf",)

    @staticmethod
    def resolve_command(configured: Path | str | None = None) -> Path | None:
        candidates: list[Path] = []
        if configured:
            candidates.append(Path(configured).expanduser())
        env_value = os.environ.get("UDT_BABELDOC_PATH", "").strip()
        if env_value:
            candidates.append(Path(env_value).expanduser())
        for name in ("babeldoc.exe", "babeldoc"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        app_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            (
                app_dir / "backend" / "babeldoc.exe",
                app_dir / "babeldoc.exe",
                Path.cwd() / "backend" / "babeldoc.exe",
                Path.cwd() / ".babeldoc-env" / "Scripts" / "babeldoc.exe",
                app_dir.parent / ".babeldoc-env" / "Scripts" / "babeldoc.exe",
            )
        )
        return next((path.resolve() for path in candidates if path.is_file()), None)

    @classmethod
    def available(cls, options: TranslationOptions) -> bool:
        return cls.resolve_command(options.babeldoc_path) is not None

    @staticmethod
    def looks_like_prose(source: Path) -> bool:
        """Prefer paragraph reflow for reports, strict placement for drawings."""
        try:
            document = fitz.open(source)
            try:
                long_lines = 0
                text_lines = 0
                word_total = 0
                for page_index in range(min(4, document.page_count)):
                    page = document[page_index]
                    for line in page.get_text("text").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        text_lines += 1
                        word_total += len(line.split())
                        if len(line) >= 70 or len(line.split()) >= 10:
                            long_lines += 1
                if not text_lines:
                    return False
                return long_lines >= 3 or word_total / text_lines >= 6
            finally:
                document.close()
        except Exception:
            return False

    @staticmethod
    def _toml_string(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    def _write_config(self, path: Path, translator, options: TranslationOptions) -> None:
        base_url = getattr(translator, "base_url", "https://api.deepseek.com")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        values = {
            "openai": True,
            "openai-model": options.model,
            "openai-base-url": base_url,
            "openai-api-key": getattr(translator, "api_key", ""),
            "openai-thinking": "disabled",
            "watermark-output-mode": "no_watermark",
            "report-interval": 0.5,
            "qps": 2,
            "pool-max-workers": 2,
            "term-pool-max-workers": 2,
            "auto-enable-ocr-workaround": True,
            "max-pages-per-part": 40,
        }
        lines = ["[babeldoc]"]
        for key, value in values.items():
            if isinstance(value, bool):
                encoded = "true" if value else "false"
            elif isinstance(value, (int, float)):
                encoded = str(value)
            else:
                encoded = self._toml_string(str(value))
            lines.append(f"{key} = {encoded}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    @staticmethod
    def _write_glossary(path: Path, glossary: dict[str, str], target_language: str) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=("source", "target", "tgt_lng"))
            writer.writeheader()
            for source, target in glossary.items():
                if source.strip() and target.strip():
                    writer.writerow({"source": source, "target": target, "tgt_lng": target_language})

    @staticmethod
    def _prefix(executable: Path) -> list[str]:
        if executable.suffix.lower() == ".py":
            return [sys.executable, str(executable)]
        return [str(executable)]

    @staticmethod
    def _stage_message(output: str) -> str:
        clean = ANSI_RE.sub("", output).replace("\r", " ").strip()
        for english, chinese in STAGE_NAMES.items():
            if english.lower() in clean.lower():
                return chinese
        if "download" in clean.lower() or "asset" in clean.lower():
            return "首次使用：准备布局模型与字体"
        return "高质量 PDF 处理中"

    @staticmethod
    def _progress_from_output(output: str, current: float) -> float:
        percentages = [float(value) for value in PERCENT_RE.findall(output)]
        if percentages:
            return max(current, min(0.98, max(percentages) / 100.0))
        for stage, milestone in STAGE_MILESTONES.items():
            if stage.lower() in output.lower():
                return max(current, milestone)
        ratio = re.search(r"\btranslate\b.*?(\d+(?:\.\d+)?)\s*/\s*100(?:\.0+)?", output, re.I)
        if ratio:
            return max(current, min(0.98, float(ratio.group(1)) / 100.0))
        return current

    @staticmethod
    def _redact_output(output: str, secret: str) -> str:
        clean = output.replace(secret, "***") if secret else output
        return re.sub(
            r"(--openai[-_]api[-_]key(?:=|\s+))\S+",
            r"\1***",
            clean,
            flags=re.IGNORECASE,
        )

    @staticmethod
    def _select_generated(folder: Path, kind: str) -> Path | None:
        matches = sorted(folder.glob(f"*.{kind}.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            return None
        no_watermark = [path for path in matches if ".no_watermark." in path.name]
        return (no_watermark or matches)[0]

    @staticmethod
    def _unique_sibling(path: Path) -> Path:
        if not path.exists():
            return path
        number = 2
        while True:
            candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
            if not candidate.exists():
                return candidate
            number += 1

    def translate(self, source, destination, translator, options, progress=None) -> FileResult:
        started = time.monotonic()
        result = FileResult(str(source), str(destination), engine="BabelDOC smart layout")
        executable = self.resolve_command(options.babeldoc_path)
        if executable is None:
            result.status = "failed"
            result.errors.append(
                "未找到 BabelDOC 高质量 PDF 引擎。请在“设置 → 高级”中选择 babeldoc.exe，"
                "或把 PDF 模式改为“原位保版”。"
            )
            return result

        process = None
        output_tail: list[str] = []
        try:
            with tempfile.TemporaryDirectory(prefix="udt_babeldoc_") as temp_value:
                temp_dir = Path(temp_value)
                output_dir = temp_dir / "output"
                working_dir = temp_dir / "working"
                output_dir.mkdir()
                working_dir.mkdir()
                config_path = temp_dir / "babeldoc.toml"
                self._write_config(config_path, translator, options)
                api_key = getattr(translator, "api_key", "")
                source_language = options.source_language if options.source_language != "auto" else "en"
                command = self._prefix(executable) + [
                    "--config", str(config_path),
                    "--files", str(source),
                    "--output", str(output_dir),
                    "--working-dir", str(working_dir),
                    "--lang-in", source_language,
                    "--lang-out", options.target_language,
                ]
                if options.pdf_output == "mono":
                    command.append("--no-dual")
                elif options.pdf_output == "dual":
                    command.append("--no-mono")
                if options.force_refresh:
                    command.append("--ignore-cache")
                glossary = getattr(translator, "glossary", {})
                if glossary:
                    glossary_path = temp_dir / "user_glossary.csv"
                    self._write_glossary(glossary_path, glossary, options.target_language)
                    command.extend(("--glossary-files", str(glossary_path)))

                creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                )
                lines: queue.Queue[str | None] = queue.Queue()

                def read_output():
                    assert process is not None and process.stdout is not None
                    try:
                        for line in iter(process.stdout.readline, ""):
                            lines.put(line)
                    finally:
                        lines.put(None)

                threading.Thread(target=read_output, daemon=True).start()
                last_fraction = 0.01
                last_heartbeat = time.monotonic()
                if progress:
                    progress(str(source), last_fraction, "启动高质量 PDF 引擎")
                reader_done = False
                while not reader_done or process.poll() is None:
                    try:
                        line = lines.get(timeout=0.5)
                    except queue.Empty:
                        if progress and time.monotonic() - last_heartbeat >= 3:
                            progress(str(source), last_fraction, "高质量 PDF 处理中")
                            last_heartbeat = time.monotonic()
                        continue
                    if line is None:
                        reader_done = True
                        continue
                    clean = self._redact_output(ANSI_RE.sub("", line).strip(), api_key)
                    if clean:
                        output_tail.append(clean)
                        output_tail = output_tail[-30:]
                    last_fraction = self._progress_from_output(clean, last_fraction)
                    if progress:
                        progress(str(source), last_fraction, self._stage_message(clean))
                        last_heartbeat = time.monotonic()
                return_code = process.wait()
                if process.stdout is not None:
                    process.stdout.close()
                if return_code != 0:
                    details = "\n".join(output_tail[-8:])
                    raise RuntimeError(f"BabelDOC 处理失败（退出代码 {return_code}）。\n{details}")

                mono = self._select_generated(output_dir, "mono")
                dual = self._select_generated(output_dir, "dual")
                requested = options.pdf_output
                primary = dual if requested == "dual" else mono
                if primary is None:
                    raise RuntimeError("BabelDOC 已结束，但没有生成所需的 PDF 文件。")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(primary, destination)
                if requested == "both":
                    if dual is None:
                        result.warnings.append("未生成中英对照 PDF。")
                    else:
                        dual_destination = self._unique_sibling(
                            destination.with_name(f"{destination.stem}_DUAL{destination.suffix}")
                        )
                        shutil.copy2(dual, dual_destination)
                        result.additional_outputs.append(str(dual_destination))

                document = fitz.open(destination)
                try:
                    result.translated_units = document.page_count
                finally:
                    document.close()
                result.status = "completed"
                if progress:
                    progress(str(source), 1.0, "高质量 PDF 已生成")
        except Exception as exc:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            result.status = "failed"
            result.errors.append(str(exc))
            if Path(destination).exists():
                Path(destination).unlink()
        finally:
            result.elapsed_seconds = round(time.monotonic() - started, 2)
            result.usage = dict(getattr(translator, "usage", {}))
        return result
