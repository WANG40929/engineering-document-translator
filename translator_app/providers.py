from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    id: str
    name: str
    api_style: str
    base_url: str
    default_model: str
    requires_api_key: bool = True
    supports_json_mode: bool = True
    supports_thinking_control: bool = False
    supports_model_listing: bool = True
    babeldoc_compatible: bool = True


PRESETS: tuple[ProviderPreset, ...] = (
    ProviderPreset("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/chat/completions", "deepseek-v4-flash", supports_thinking_control=True),
    ProviderPreset("openai", "OpenAI", "openai", "https://api.openai.com/v1/chat/completions", "gpt-5-mini"),
    ProviderPreset("anthropic", "Anthropic Claude", "anthropic", "https://api.anthropic.com/v1/messages", "claude-sonnet-4-5", supports_json_mode=False, babeldoc_compatible=False),
    ProviderPreset("gemini", "Google Gemini", "openai", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "gemini-2.5-flash"),
    ProviderPreset("qwen", "Alibaba Model Studio / Qwen", "openai", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions", "qwen-plus"),
    ProviderPreset("azure_openai", "Azure OpenAI", "azure", "", "", supports_model_listing=False),
    ProviderPreset("moonshot", "Moonshot / Kimi", "openai", "https://api.moonshot.cn/v1/chat/completions", "moonshot-v1-auto"),
    ProviderPreset("zhipu", "Zhipu GLM", "openai", "https://open.bigmodel.cn/api/paas/v4/chat/completions", "glm-4-flash"),
    ProviderPreset("volcengine", "Volcengine Ark / Doubao", "openai", "https://ark.cn-beijing.volces.com/api/v3/chat/completions", "", supports_model_listing=False),
    ProviderPreset("siliconflow", "SiliconFlow", "openai", "https://api.siliconflow.cn/v1/chat/completions", "deepseek-ai/DeepSeek-V3"),
    ProviderPreset("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1/chat/completions", "openai/gpt-4.1-mini", supports_json_mode=False),
    ProviderPreset("mistral", "Mistral AI", "openai", "https://api.mistral.ai/v1/chat/completions", "mistral-small-latest"),
    ProviderPreset("groq", "Groq", "openai", "https://api.groq.com/openai/v1/chat/completions", "llama-3.3-70b-versatile"),
    ProviderPreset("together", "Together AI", "openai", "https://api.together.xyz/v1/chat/completions", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    ProviderPreset("ollama", "Ollama (local)", "openai", "http://127.0.0.1:11434/v1/chat/completions", "qwen2.5:7b", requires_api_key=False, supports_json_mode=False),
    ProviderPreset("lm_studio", "LM Studio (local)", "openai", "http://127.0.0.1:1234/v1/chat/completions", "local-model", requires_api_key=False, supports_json_mode=False),
    ProviderPreset("vllm", "vLLM (local)", "openai", "http://127.0.0.1:8000/v1/chat/completions", "", requires_api_key=False, supports_json_mode=False),
    ProviderPreset("custom_openai", "Custom OpenAI-compatible", "openai", "", "", supports_json_mode=False),
)

PRESETS_BY_ID = {item.id: item for item in PRESETS}


@dataclass(slots=True)
class ProviderProfile:
    id: str
    name: str
    provider: str
    api_style: str
    base_url: str
    model: str
    azure_api_version: str = "2024-10-21"
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "ProviderProfile":
        preset = get_preset(str(value.get("provider") or "deepseek"))
        return cls(
            id=str(value.get("id") or uuid4().hex),
            name=str(value.get("name") or preset.name),
            provider=preset.id,
            api_style=str(value.get("api_style") or preset.api_style),
            base_url=str(value.get("base_url") or preset.base_url),
            model=str(value.get("model") or preset.default_model),
            azure_api_version=str(value.get("azure_api_version") or "2024-10-21"),
            enabled=bool(value.get("enabled", True)),
        )

    @property
    def preset(self) -> ProviderPreset:
        return get_preset(self.provider)


def get_preset(provider_id: str) -> ProviderPreset:
    return PRESETS_BY_ID.get(provider_id, PRESETS_BY_ID["custom_openai"])


def new_profile(provider_id: str = "deepseek", *, profile_id: str | None = None) -> ProviderProfile:
    preset = get_preset(provider_id)
    return ProviderProfile(
        id=profile_id or uuid4().hex,
        name=preset.name,
        provider=preset.id,
        api_style=preset.api_style,
        base_url=preset.base_url,
        model=preset.default_model,
    )


def default_profile(model: str = "deepseek-v4-flash") -> ProviderProfile:
    profile = new_profile("deepseek", profile_id="deepseek-default")
    return replace(profile, model=model or profile.model)


def normalize_url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value:
        return ""
    parts = urlsplit(value)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def models_url(profile: ProviderProfile) -> str | None:
    if not profile.preset.supports_model_listing or profile.api_style == "anthropic":
        return None
    endpoint = normalize_url(profile.base_url)
    suffix = "/chat/completions"
    if endpoint.endswith(suffix):
        return endpoint[: -len(suffix)] + "/models"
    return endpoint.rstrip("/") + "/models"


def babeldoc_base_url(profile: ProviderProfile) -> str | None:
    if not profile.preset.babeldoc_compatible or profile.api_style not in {"openai", "azure"}:
        return None
    endpoint = normalize_url(profile.base_url)
    suffix = "/chat/completions"
    return endpoint[: -len(suffix)] if endpoint.endswith(suffix) else endpoint
