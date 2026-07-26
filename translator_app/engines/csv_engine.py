from __future__ import annotations

import csv
import time

from ..i18n import tr
from ..models import FileResult
from ..text_utils import is_translatable
from .base import TranslationEngine


def _encoding(path):
    prefix = path.read_bytes()[:4]
    if prefix.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    try:
        path.read_text(encoding="utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "gb18030"


class CsvEngine(TranslationEngine):
    extensions = (".csv", ".tsv")

    def translate(self, source, destination, translator, options, progress=None) -> FileResult:
        started = time.monotonic()
        result = FileResult(str(source), str(destination), engine="CSV/TSV")
        try:
            encoding = _encoding(source)
            with source.open("r", encoding=encoding, newline="") as handle:
                sample = handle.read(8192)
                handle.seek(0)
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
                except csv.Error:
                    dialect = csv.excel_tab if source.suffix.lower() == ".tsv" else csv.excel
                rows = list(csv.reader(handle, dialect))
            positions, texts = [], []
            for row_index, row in enumerate(rows):
                for column_index, value in enumerate(row):
                    if is_translatable(value):
                        positions.append((row_index, column_index))
                        texts.append(value)
            translations = translator.translate_many(
                texts,
                lambda done, total: (
                    progress(
                        str(source),
                        done / max(total, 1),
                        tr("progress.table", done=done, total=total),
                    )
                    if progress
                    else None
                ),
            )
            for (row_index, column_index), value in zip(positions, translations):
                rows[row_index][column_index] = value
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("w", encoding=encoding, newline="") as handle:
                csv.writer(handle, dialect).writerows(rows)
            result.translated_units = len(texts)
            result.status = "completed"
        except Exception as exc:
            result.status = "failed"
            result.errors.append(str(exc))
            if destination.exists():
                destination.unlink()
        result.elapsed_seconds = round(time.monotonic() - started, 2)
        result.usage = dict(getattr(translator, "usage", {}))
        return result
