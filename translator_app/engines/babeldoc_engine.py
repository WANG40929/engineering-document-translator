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

from ..i18n import tr
from ..models import FileResult, TranslationOptions
from .base import TranslationEngine


ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
PERCENT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%")
COUNT_RE = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?!\d)")
OVERALL_RE = re.compile(
    r"(?:^|[\r\n])\s*translate(?!\s+paragraphs)\b[^\r\n]*?"
    r"(\d+(?:\.\d+)?)\s*/\s*100(?:\.0+)?",
)
OVERALL_PERCENT_RE = re.compile(
    r"(?:^|[\r\n])\s*translate(?!\s+paragraphs)\b[^\r\n]*?"
    r"(\d{1,3}(?:\.\d+)?)\s*%",
)
OVERALL_FIELD_RE = re.compile(
    r"""["']?overall[_ -]?progress["']?\s*[:=]\s*(\d+(?:\.\d+)?)""",
    re.IGNORECASE,
)
PART_RE = re.compile(r"\((\d+)\s*/\s*(\d+)\)")
STAGE_NAMES = {
    "Parse PDF and Create Intermediate Representation": "progress.pdf_parse",
    "DetectScannedFile": "progress.pdf_detect_scan",
    "Parse Page Layout": "progress.pdf_layout",
    "Parse Table": "progress.pdf_table",
    "Parse Paragraphs": "progress.pdf_paragraphs",
    "Parse Formulas and Styles": "progress.pdf_formulas",
    "Automatic Term Extraction": "progress.pdf_terms",
    "Extract Terms": "progress.pdf_terms",  # compatibility with older BabelDOC builds
    "Translate Paragraphs": "progress.pdf_translate",
    "Typesetting": "progress.pdf_typeset",
    "Add Fonts": "progress.pdf_fonts",
    "Generate drawing instructions": "progress.pdf_render",
    "Subset font": "progress.pdf_subset_fonts",
    "Save PDF": "progress.pdf_save",
}
STAGE_ORDER = {stage: index for index, stage in enumerate(STAGE_NAMES)}
STAGE_MILESTONES = {
    "Parse PDF and Create Intermediate Representation": 0.04,
    "DetectScannedFile": 0.14,
    "Parse Page Layout": 0.18,
    "Parse Table": 0.29,
    "Parse Paragraphs": 0.31,
    "Parse Formulas and Styles": 0.35,
    "Automatic Term Extraction": 0.38,
    "Extract Terms": 0.38,
    "Translate Paragraphs": 0.48,
    "Typesetting": 0.82,
    "Add Fonts": 0.87,
    "Generate drawing instructions": 0.90,
    "Subset font": 0.94,
    "Save PDF": 0.97,
}

STAGE_ENDS = {
    "Parse PDF and Create Intermediate Representation": 0.14,
    "DetectScannedFile": 0.18,
    "Parse Page Layout": 0.29,
    "Parse Table": 0.31,
    "Parse Paragraphs": 0.35,
    "Parse Formulas and Styles": 0.38,
    "Automatic Term Extraction": 0.48,
    "Extract Terms": 0.48,
    "Translate Paragraphs": 0.82,
    "Typesetting": 0.87,
    "Add Fonts": 0.90,
    "Generate drawing instructions": 0.94,
    "Subset font": 0.97,
    "Save PDF": 0.98,
}

PAGE_STAGES = {
    "Parse PDF and Create Intermediate Representation",
    "DetectScannedFile",
    "Parse Page Layout",
}


class BabelDocProgress:
    """Parse BabelDOC's Rich console output into truthful monotonic progress."""

    def __init__(self, current: float = 0.01):
        self.fraction = min(0.98, max(0.0, float(current)))
        self.message = tr("progress.pdf_smart_processing")
        self.stage = ""
        self.current: float | None = None
        self.total: float | None = None
        self._seen_overall = False

    @staticmethod
    def _clean(output: str) -> str:
        return ANSI_RE.sub("", output).replace("\r", "\n").strip()

    @staticmethod
    def _detect_stage(clean: str) -> str:
        lowered = clean.casefold()
        # Longest first prevents "Extract Terms" style compatibility aliases
        # from shadowing a more specific stage.
        for stage in sorted(STAGE_NAMES, key=len, reverse=True):
            if stage.casefold() in lowered:
                return stage
        return ""

    @staticmethod
    def _last_count(clean: str) -> tuple[float, float] | None:
        part_spans = [match.span() for match in PART_RE.finditer(clean)]
        matches = [
            match
            for match in COUNT_RE.finditer(clean)
            if not any(
                match.start() >= part_start and match.end() <= part_end
                for part_start, part_end in part_spans
            )
        ]
        if not matches:
            return None
        current, total = matches[-1].groups()
        total_value = float(total)
        if total_value <= 0:
            return None
        return float(current), total_value

    def _message_for(
        self,
        clean: str,
        stage: str,
        count: tuple[float, float] | None,
    ) -> str:
        if "download" in clean.casefold() or "asset" in clean.casefold():
            return tr("progress.pdf_first_use")
        if not stage:
            # The separate lowercase "translate" Rich task carries accurate
            # overall progress but no stage description. Keep the last useful
            # stage/unit message while accepting its global percentage.
            return self.message
        base = tr(STAGE_NAMES.get(stage, "progress.pdf_smart_processing"))
        details = ""
        if count:
            current, total = count
            current_text = f"{current:g}"
            total_text = f"{total:g}"
            if stage in PAGE_STAGES:
                details = " · " + tr(
                    "progress.page_counter",
                    current=current_text,
                    total=total_text,
                )
            elif stage == "Translate Paragraphs":
                details = " · " + tr(
                    "progress.segment_counter",
                    current=current_text,
                    total=total_text,
                )
            else:
                details = f" · {current_text}/{total_text}"
        part = PART_RE.search(clean)
        part_details = ""
        if part and int(part.group(2)) > 1:
            part_details = " · " + tr(
                "progress.part_counter",
                current=part.group(1),
                total=part.group(2),
            )
        return f"{base}{details}{part_details}"

    def update(self, output: str) -> tuple[float, str]:
        clean = self._clean(output)
        if not clean:
            return self.fraction, self.message

        stage = self._detect_stage(clean)
        count = self._last_count(clean) if stage else None
        candidate = self.fraction

        overall = OVERALL_RE.search(clean)
        if overall:
            self._seen_overall = True
            candidate = float(overall.group(1)) / 100.0
        else:
            overall_percent = OVERALL_PERCENT_RE.search(clean)
            overall_field = OVERALL_FIELD_RE.search(clean)
            if overall_percent:
                self._seen_overall = True
                candidate = float(overall_percent.group(1)) / 100.0
            elif overall_field:
                self._seen_overall = True
                candidate = float(overall_field.group(1)) / 100.0
            elif stage and not self._seen_overall:
                start = STAGE_MILESTONES.get(stage, self.fraction)
                end = STAGE_ENDS.get(stage, min(0.98, start + 0.03))
                local_ratio = None
                if count:
                    local_ratio = min(1.0, max(0.0, count[0] / count[1]))
                else:
                    percentages = [float(value) for value in PERCENT_RE.findall(clean)]
                    if percentages:
                        local_ratio = min(1.0, max(0.0, percentages[-1] / 100.0))
                candidate = start if local_ratio is None else start + (end - start) * local_ratio

        self.fraction = max(self.fraction, min(0.98, candidate))
        accepted_stage = stage
        if (
            stage
            and self.stage
            and STAGE_ORDER.get(stage, -1) < STAGE_ORDER.get(self.stage, -1)
        ):
            # Rich redraws every task on each refresh. Once processing has
            # advanced, do not let completed early tasks replace the useful
            # current-stage message.
            accepted_stage = ""

        if accepted_stage:
            self.stage = stage
            self.current, self.total = count or (None, None)
            self.message = self._message_for(clean, stage, count)
        return self.fraction, self.message

    def heartbeat_message(self) -> str:
        if self.message == tr("progress.pdf_smart_processing"):
            return self.message
        return f"{self.message} · {tr('progress.stalled')}"


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
        app_dir = Path(sys.executable).resolve().parent
        candidates.extend(
            (
                app_dir / "TranslationEngine" / "babeldoc.exe",
                app_dir / "backend" / "babeldoc.exe",
                app_dir / "babeldoc.exe",
                Path.cwd() / "TranslationEngine" / "babeldoc.exe",
                Path.cwd() / "backend" / "babeldoc.exe",
                Path.cwd() / ".babeldoc-env" / "Scripts" / "babeldoc.exe",
                app_dir.parent / ".babeldoc-env" / "Scripts" / "babeldoc.exe",
            )
        )
        # A Full/Setup release must use the engine shipped and tested with that
        # release. A stale global PATH installation remains a final fallback,
        # but must never silently shadow the bundled runtime.
        for name in ("babeldoc.exe", "babeldoc"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
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

    @staticmethod
    def _recommended_workers(model: str = "") -> int:
        """Restore safe BabelDOC parallelism without exposing quality levels."""
        override = os.environ.get("UDT_BABELDOC_CONCURRENCY", "").strip()
        if override:
            try:
                return max(1, min(6, int(override)))
            except ValueError:
                pass
        if "reasoner" in model.casefold():
            return 2
        cpu_count = os.cpu_count() or 4
        if cpu_count <= 1:
            return 2
        if cpu_count <= 3:
            return 3
        # BabelDOC itself defaults to 4 QPS. This removes the old artificial
        # limit of 2 while keeping provider bursts conservative.
        return 4

    def _write_config(self, path: Path, translator, options: TranslationOptions) -> None:
        base_url = getattr(translator, "base_url", "https://api.deepseek.com")
        if base_url.endswith("/chat/completions"):
            base_url = base_url[: -len("/chat/completions")]
        workers = self._recommended_workers(options.model)
        values = {
            "openai": True,
            "openai-model": options.model,
            "openai-base-url": base_url,
            "openai-api-key": getattr(translator, "api_key", ""),
            "openai-thinking": "disabled",
            "watermark-output-mode": "no_watermark",
            "report-interval": 0.25,
            "qps": workers,
            "pool-max-workers": workers,
            "term-pool-max-workers": min(workers, 3),
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
        return BabelDocProgress().update(output)[1]

    @staticmethod
    def _progress_from_output(output: str, current: float) -> float:
        return BabelDocProgress(current).update(output)[0]

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
            result.errors.append(tr("error.babeldoc_missing"))
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
                backend_environment = os.environ.copy()
                # BabelDOC renders its detailed progress only when Rich sees a
                # terminal. Our stdout pipe is intentionally not a real
                # console, so opt in to terminal-compatible rendering and
                # parse the emitted stage/page/paragraph counters below.
                backend_environment.update(
                    {
                        "TTY_COMPATIBLE": "1",
                        "TERM": "xterm-256color",
                        "COLUMNS": "160",
                        "PYTHONUNBUFFERED": "1",
                    }
                )
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                    env=backend_environment,
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
                progress_state = BabelDocProgress(0.01)
                last_fraction = progress_state.fraction
                last_heartbeat = time.monotonic()
                last_emit_time = last_heartbeat
                last_emitted_fraction = last_fraction
                last_emitted_message = progress_state.message
                if progress:
                    progress(
                        str(source),
                        last_fraction,
                        tr("progress.pdf_start_engine"),
                    )
                reader_done = False
                while not reader_done or process.poll() is None:
                    try:
                        line = lines.get(timeout=0.5)
                    except queue.Empty:
                        if progress and time.monotonic() - last_heartbeat >= 3:
                            progress(
                                str(source),
                                progress_state.fraction,
                                progress_state.heartbeat_message(),
                            )
                            last_heartbeat = time.monotonic()
                        continue
                    if line is None:
                        reader_done = True
                        continue
                    clean = self._redact_output(ANSI_RE.sub("", line).strip(), api_key)
                    if clean:
                        output_tail.append(clean)
                        output_tail = output_tail[-30:]
                    last_fraction, stage_message = progress_state.update(clean)
                    now = time.monotonic()
                    changed = (
                        last_fraction >= last_emitted_fraction + 0.002
                        or stage_message != last_emitted_message
                    )
                    if progress and changed and now - last_emit_time >= 0.25:
                        progress(str(source), last_fraction, stage_message)
                        last_emit_time = now
                        last_heartbeat = now
                        last_emitted_fraction = last_fraction
                        last_emitted_message = stage_message
                return_code = process.wait()
                if process.stdout is not None:
                    process.stdout.close()
                if return_code != 0:
                    details = "\n".join(output_tail[-8:])
                    raise RuntimeError(
                        tr(
                            "error.babeldoc_failed",
                            code=return_code,
                            details=details,
                        )
                    )

                mono = self._select_generated(output_dir, "mono")
                dual = self._select_generated(output_dir, "dual")
                requested = options.pdf_output
                primary = dual if requested == "dual" else mono
                if primary is None:
                    raise RuntimeError(tr("error.babeldoc_no_output"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(primary, destination)
                if requested == "both":
                    if dual is None:
                        result.warnings.append(tr("warning.babeldoc_no_dual"))
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
                    progress(str(source), 1.0, tr("progress.pdf_generated"))
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
