from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import FileResult, ProgressCallback, TranslationOptions


class TranslationEngine(ABC):
    extensions: tuple[str, ...] = ()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    @abstractmethod
    def translate(
        self,
        source: Path,
        destination: Path,
        translator,
        options: TranslationOptions,
        progress: ProgressCallback | None = None,
    ) -> FileResult:
        raise NotImplementedError

