from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .providers import ProviderProfile, default_profile


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
    ui_language: str = "auto"
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
    provider_profiles: list[dict] | None = None
    active_provider_id: str = "deepseek-default"
    fallback_provider_id: str = ""
    config_version: int = 5

    def profiles(self) -> list[ProviderProfile]:
        raw = self.provider_profiles or [default_profile(self.model).to_dict()]
        profiles = [ProviderProfile.from_dict(item) for item in raw if isinstance(item, dict)]
        return profiles or [default_profile(self.model)]

    def active_profile(self) -> ProviderProfile:
        profiles = self.profiles()
        return next((item for item in profiles if item.id == self.active_provider_id), profiles[0])

    def fallback_profile(self) -> ProviderProfile | None:
        if not self.fallback_provider_id:
            return None
        return next((item for item in self.profiles() if item.id == self.fallback_provider_id), None)


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
            if int(data.get("config_version", 0)) < 4:
                allowed.setdefault("ui_language", "auto")
            if int(data.get("config_version", 0)) < 5:
                profile = default_profile(str(allowed.get("model") or "deepseek-v4-flash"))
                allowed.setdefault("provider_profiles", [profile.to_dict()])
                allowed.setdefault("active_provider_id", profile.id)
                allowed.setdefault("fallback_provider_id", "")
            allowed["config_version"] = 5
            return AppConfig(**allowed)
        except Exception:
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.path)
