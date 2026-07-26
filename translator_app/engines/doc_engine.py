from __future__ import annotations

import subprocess
import tempfile
import time
from pathlib import Path

from ..i18n import tr
from ..models import FileResult
from .base import TranslationEngine
from .docx_engine import DocxEngine


CONVERT_SCRIPT = r"""
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
try {
  $doc = $word.Documents.Open($args[0])
  $format = [int]$args[2]
  $doc.SaveAs([ref]$args[1], [ref]$format)
  $doc.Close($false)
} finally { $word.Quit() }
"""


def _word_convert(source: Path, destination: Path, format_number: int) -> None:
    process = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", CONVERT_SCRIPT, str(source), str(destination), str(format_number)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if process.returncode or not destination.exists():
        details = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(tr("error.word_required") + (f" {details}" if details else ""))


class DocEngine(TranslationEngine):
    extensions = (".doc",)

    def translate(self, source, destination, translator, options, progress=None) -> FileResult:
        started = time.monotonic()
        result = FileResult(str(source), str(destination), engine="Legacy DOC (Microsoft Word)")
        try:
            with tempfile.TemporaryDirectory(prefix="udt_doc_") as folder:
                temporary = Path(folder)
                input_docx = temporary / "source.docx"
                output_docx = temporary / "translated.docx"
                _word_convert(source.resolve(), input_docx.resolve(), 16)
                nested = DocxEngine().translate(input_docx, output_docx, translator, options, progress)
                if nested.status != "completed":
                    raise RuntimeError("；".join(nested.errors))
                destination.parent.mkdir(parents=True, exist_ok=True)
                _word_convert(output_docx.resolve(), destination.resolve(), 0)
                result.translated_units = nested.translated_units
                result.warnings.extend(nested.warnings)
                result.status = "completed"
        except Exception as exc:
            result.status = "failed"
            result.errors.append(str(exc))
            if destination.exists():
                destination.unlink()
        result.elapsed_seconds = round(time.monotonic() - started, 2)
        result.usage = dict(getattr(translator, "usage", {}))
        return result
