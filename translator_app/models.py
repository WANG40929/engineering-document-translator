from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable


LANGUAGES = {
    "auto": "自动识别",
    "zh": "中文（简体）",
    "en": "英语",
    "ru": "俄语",
    "de": "德语",
    "fr": "法语",
    "es": "西班牙语",
    "pt": "葡萄牙语",
    "ja": "日语",
    "ko": "韩语",
}


@dataclass(slots=True)
class TranslationOptions:
    source_language: str = "auto"
    target_language: str = "zh"
    model: str = "deepseek-v4-flash"
    output_mode: str = "replace"
    output_dir: Path | None = None
    glossary_path: Path | None = None
    minimum_pdf_font_size: float = 3.2
    batch_size: int = 40
    request_timeout: int = 180
    preserve_technical_tokens: bool = True
    skip_textless_pdf_pages: bool = True
    pure_target_language: bool = False
    quality_review: bool = True
    force_refresh: bool = False
    pdf_mode: str = "auto"
    pdf_output: str = "mono"
    babeldoc_path: Path | None = None


@dataclass(slots=True)
class FileResult:
    input_path: str
    output_path: str | None = None
    status: str = "pending"
    engine: str = ""
    translated_units: int = 0
    skipped_units: int = 0
    skipped_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    additional_outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


ProgressCallback = Callable[[str, float, str], None]
