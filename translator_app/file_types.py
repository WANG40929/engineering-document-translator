from __future__ import annotations

import re
from pathlib import Path


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".csv", ".tsv"}

# Files produced by this application must not be picked up as new source files
# during a later folder import.  Keep this independent from the UI locale: the
# suffix is based on the translation target language.
_TRANSLATED_OUTPUT_RE = re.compile(
    r"(?:_|\.)(?:ZH(?:-CN)?|EN|RU|DE|FR|ES|PT|JA|KO)"
    r"(?:[_\.-](?:DUAL|MONO))*"
    r"(?:_\d+)?$",
    re.IGNORECASE,
)


def is_translated_output(path: Path) -> bool:
    return bool(_TRANSLATED_OUTPUT_RE.search(path.stem))


def collect_files(path: Path, recursive: bool = True) -> list[Path]:
    iterator = path.rglob("*") if recursive else path.glob("*")
    return sorted(
        item
        for item in iterator
        if item.is_file()
        and item.suffix.lower() in SUPPORTED_EXTENSIONS
        and not is_translated_output(item)
    )
