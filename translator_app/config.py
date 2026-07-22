from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


APP_NAME = "UniversalDocumentTranslator"


def app_data_dir() -> Path:
    override = os.environ.get("UDT_DATA_DIR")
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        path = Path(base) / APP_NAME
    else:
        path = Path.home() / f".{APP_NAME.lower()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class AppConfig:
    model: str = "deepseek-v4-flash"
    source_language: str = "auto"
    target_language: str = "zh"
    output_dir: str = ""
    glossary_path: str = ""
    batch_size: int = 40
    request_timeout: int = 180
    pure_target_language: bool = False
    quality_review: bool = True
    force_refresh: bool = False
    pdf_mode: str = "auto"
    pdf_output: str = "mono"
    babeldoc_path: str = ""
    config_version: int = 3


class ConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = path or app_data_dir() / "config.json"

    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            allowed = {key: data[key] for key in AppConfig.__annotations__ if key in data}
            if allowed.get("model") in {"deepseek-chat", "deepseek-reasoner"}:
                allowed["model"] = "deepseek-v4-flash"
            # v2 changes pure-target translation from opt-out to opt-in.
            # Migrate once, then continue respecting the user's saved choice.
            if int(data.get("config_version", 0)) < 2:
                allowed["pure_target_language"] = False
            if int(data.get("config_version", 0)) < 3:
                allowed.setdefault("pdf_mode", "auto")
                allowed.setdefault("pdf_output", "mono")
                allowed.setdefault("babeldoc_path", "")
            allowed["config_version"] = 3
            return AppConfig(**allowed)
        except Exception:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
