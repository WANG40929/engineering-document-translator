from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from translator_app.cache import TranslationCache
from translator_app.config import ConfigStore
from translator_app.deepseek import DeepSeekError, DeepSeekTranslator, FallbackTranslator
from translator_app.models import FileResult, TranslationOptions
from translator_app.pipeline import TranslationPipeline
from translator_app.providers import PRESETS_BY_ID, ProviderProfile, default_profile, new_profile
from translator_app.secret_store import ProviderSecretStore, SecretStore


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _translation_payload(style="openai"):
    text = json.dumps({"translations": [{"id": 0, "text": "[[UDT_SEGMENT_0000]] 你好"}]})
    if style == "anthropic":
        return {
            "content": [{"type": "text", "text": f"```json\n{text}\n```"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="udt_provider_")
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def _translator(self, profile, key="key"):
        return DeepSeekTranslator.from_profile(
            profile,
            key,
            cache=TranslationCache(self.root / f"{profile.id}.sqlite3"),
            quality_review=False,
        )

    def test_mainstream_and_local_presets_are_registered(self):
        required = {
            "deepseek", "openai", "anthropic", "gemini", "qwen", "azure_openai",
            "moonshot", "zhipu", "volcengine", "siliconflow", "openrouter",
            "mistral", "groq", "together", "ollama", "lm_studio", "vllm",
            "custom_openai",
        }
        self.assertTrue(required <= set(PRESETS_BY_ID))
        self.assertFalse(PRESETS_BY_ID["ollama"].requires_api_key)

    def test_v4_config_migrates_to_deepseek_profile(self):
        path = self.root / "config.json"
        path.write_text(json.dumps({"config_version": 4, "model": "deepseek-v4-pro"}), encoding="utf-8")
        config = ConfigStore(path).load()
        self.assertEqual(config.config_version, 5)
        self.assertEqual(config.active_profile().provider, "deepseek")
        self.assertEqual(config.active_profile().model, "deepseek-v4-pro")

    def test_cache_signature_is_isolated_by_provider_and_url(self):
        first = self._translator(default_profile())
        second_profile = new_profile("openai")
        second_profile.model = first.model
        second = self._translator(second_profile)
        third_profile = new_profile("custom_openai")
        third_profile.model = first.model
        third_profile.base_url = "https://gateway.example/v1/chat/completions"
        third = self._translator(third_profile)
        self.assertNotEqual(first._cache_signature, second._cache_signature)
        self.assertNotEqual(first._cache_signature, third._cache_signature)

    def test_openai_compatible_omits_deepseek_only_thinking(self):
        profile = new_profile("openai")
        translator = self._translator(profile)
        captured = {}

        def fake_open(request, timeout):
            captured["body"] = json.loads(request.data)
            return _Response(_translation_payload())

        with patch("urllib.request.urlopen", side_effect=fake_open):
            translator._request([{"id": 0, "text": "Hello"}])
        self.assertNotIn("thinking", captured["body"])
        self.assertIn("response_format", captured["body"])

    def test_anthropic_native_body_headers_parser_and_usage(self):
        profile = new_profile("anthropic")
        translator = self._translator(profile)
        captured = {}

        def fake_open(request, timeout):
            captured["body"] = json.loads(request.data)
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            return _Response(_translation_payload("anthropic"))

        with patch("urllib.request.urlopen", side_effect=fake_open):
            result = translator._request([{"id": 0, "text": "Hello"}])
        self.assertEqual(result, {0: "你好"})
        self.assertIn("system", captured["body"])
        self.assertNotIn("response_format", captured["body"])
        self.assertEqual(captured["headers"]["x-api-key"], "key")
        self.assertEqual(translator.usage["total_tokens"], 15)

    def test_azure_uses_api_key_header_and_url_version(self):
        profile = ProviderProfile(
            "azure", "Azure", "azure_openai", "azure",
            "https://example.openai.azure.com/openai/deployments/demo/chat/completions",
            "demo", "2024-10-21",
        )
        translator = self._translator(profile)
        captured = {}

        def fake_open(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)
            captured["headers"] = {key.lower(): value for key, value in request.header_items()}
            return _Response(_translation_payload())

        with patch("urllib.request.urlopen", side_effect=fake_open):
            translator._request([{"id": 0, "text": "Hello"}])
        self.assertIn("api-version=2024-10-21", captured["url"])
        self.assertEqual(captured["headers"]["api-key"], "key")
        self.assertNotIn("model", captured["body"])

    def test_local_provider_does_not_require_key(self):
        translator = self._translator(new_profile("ollama"), key="")
        self.assertEqual(translator.api_key, "")

    def test_fallback_switches_after_terminal_primary_failure(self):
        primary = self._translator(default_profile())
        fallback = self._translator(new_profile("openai"))
        primary.translate_many = lambda *_args, **_kwargs: (_ for _ in ()).throw(DeepSeekError("down"))
        fallback.translate_many = lambda values, _progress=None: ["备用"] * len(values)
        translator = FallbackTranslator(primary, fallback)
        self.assertEqual(translator.translate_many(["hello"]), ["备用"])
        self.assertTrue(translator.fallback_used)

    def test_smart_pdf_failure_falls_back_to_strict_engine(self):
        source = self.root / "source.pdf"
        source.write_bytes(b"pdf")
        pipeline = TranslationPipeline()
        pipeline.smart_pdf_engine.translate = lambda *_args, **_kwargs: FileResult(
            str(source), status="failed", errors=["provider unavailable"]
        )
        pipeline.strict_pdf_engine.translate = lambda _s, destination, *_args, **_kwargs: FileResult(
            str(source), str(destination), status="completed", engine="strict"
        )
        with patch.object(pipeline, "engine_for", return_value=pipeline.smart_pdf_engine):
            result = pipeline.run([source], object(), TranslationOptions(pdf_mode="smart"))[0]
        self.assertEqual(result.status, "completed")
        self.assertTrue(result.warnings)

    @unittest.skipUnless(__import__("os").name == "nt", "Windows DPAPI test")
    def test_provider_keys_are_encrypted_separately_and_ignore_legacy_env_override(self):
        legacy = SecretStore(self.root / "legacy.key")
        store = ProviderSecretStore(self.root / "providers.dat", legacy=legacy)
        with patch.dict("os.environ", {"DEEPSEEK_API_KEY": "legacy-env"}):
            store.save_all({"profile-a": "key-a", "profile-b": "key-b"})
            self.assertEqual(store.load_all(), {"profile-a": "key-a", "profile-b": "key-b"})
        self.assertNotIn(b"key-a", (self.root / "providers.dat").read_bytes())

    @unittest.skipUnless(__import__("os").name == "nt", "Windows DPAPI test")
    def test_clearing_provider_keys_does_not_resurrect_legacy_key(self):
        legacy = SecretStore(self.root / "legacy.key", env_name=None)
        legacy.save("old-key")
        store = ProviderSecretStore(self.root / "providers.dat", legacy=legacy)
        self.assertEqual(store.load_all(), {"deepseek-default": "old-key"})
        store.clear()
        self.assertEqual(store.load_all(), {})
        self.assertFalse(legacy.path.exists())


if __name__ == "__main__":
    unittest.main()
