from __future__ import annotations

import json
import hashlib
import random
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence

from .cache import TranslationCache
from .text_utils import glossary_signature, is_translatable, protect_text


LANGUAGE_NAMES = {
    "auto": "自动识别的源语言",
    "zh": "简体中文",
    "en": "English",
    "ru": "Русский",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "pt": "Português",
    "ja": "日本語",
    "ko": "한국어",
}

CACHE_POLICY_VERSION = "v2-paragraph-target-only-review"
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]{1,}")
PLACEHOLDER_RE = re.compile(r"__UDT_\d{4}__")


class DeepSeekError(RuntimeError):
    pass


class IncompleteResponseError(DeepSeekError):
    """The API returned valid JSON, but omitted one or more requested IDs."""

    def __init__(self, missing: set[int], partial: dict[int, str], finish_reason: str = ""):
        self.missing = missing
        self.partial = partial
        self.finish_reason = finish_reason
        reason = f"，结束原因：{finish_reason}" if finish_reason else ""
        super().__init__(f"接口返回缺少段落：{sorted(missing)}{reason}")


class DeepSeekTranslator:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-v4-flash",
        source_language: str = "auto",
        target_language: str = "zh",
        glossary: dict[str, str] | None = None,
        cache: TranslationCache | None = None,
        timeout: int = 180,
        batch_size: int = 40,
        base_url: str = "https://api.deepseek.com/chat/completions",
        pure_target_language: bool = True,
        quality_review: bool = True,
        force_refresh: bool = False,
    ):
        if not api_key.strip():
            raise ValueError("请输入 DeepSeek API Key。")
        self.api_key = api_key.strip()
        self.model = model.strip() or "deepseek-v4-flash"
        self.source_language = source_language
        self.target_language = target_language
        self.glossary = glossary or {}
        self.cache = cache or TranslationCache()
        self.timeout = timeout
        self.batch_size = max(1, min(batch_size, 100))
        self.base_url = base_url
        self.pure_target_language = pure_target_language
        self.quality_review = quality_review
        self.force_refresh = force_refresh
        self.usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "requests": 0,
            "api_attempts": 0,
            "cache_hits": 0,
            "quality_retries": 0,
            "schema_failures": 0,
            "repair_requests": 0,
            "split_retries": 0,
            "recovered_segments": 0,
            "transport_retries": 0,
            "finish_reasons": {},
            "thinking_mode": "disabled",
        }
        policy = "|".join((
            CACHE_POLICY_VERSION,
            self.model,
            f"pure={int(self.pure_target_language)}",
            f"review={int(self.quality_review)}",
            glossary_signature(self.glossary),
        ))
        self._cache_signature = hashlib.sha256(policy.encode("utf-8")).hexdigest()

    def _system_prompt(self) -> str:
        source = LANGUAGE_NAMES.get(self.source_language, self.source_language)
        target = LANGUAGE_NAMES.get(self.target_language, self.target_language)
        glossary = "\n".join(f"- {a} => {b}" for a, b in list(self.glossary.items())[:500])
        target_only = (
            "输出必须只使用目标语言。若原文是德语/英语等双语并用斜杠分隔，必须翻译两部分，"
            "合并为自然且不重复的目标语言，不得保留源语言对照。"
            if self.pure_target_language else
            "按原文的单语或双语结构翻译。"
        )
        return (
            "你是严谨的工程技术文档翻译器。"
            f"把每段从{source}翻译成{target}。保持原意、数字、单位、标点层次和换行；"
            f"{target_only}"
            "物料名称、标题、字段标签和普通技术词必须翻译；注册公司名、地址、型号、图号、物料号、标准号、材料牌号、单位及短缩写保持原样。"
            "不得翻译或改写 __UDT_0000__ 形式的占位符；不解释、不补充。"
            "返回严格 JSON：{\"translations\":[{\"id\":0,\"text\":\"...\"}]}，id 必须与输入一致。"
            + (f"\n必须采用以下术语表：\n{glossary}" if glossary else "")
        )

    def _request(self, items: list[dict], review: bool = False) -> dict[int, str]:
        system_prompt = self._system_prompt()
        if review:
            system_prompt += (
                "\n这是质量复核：上次结果可能残留了源语言。重新翻译每一段，确保普通词、物料名称和双语字段完全转换为目标语言，"
                "同时仍须保留代码、单位、型号、公司名和地址。"
            )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps({"segments": items}, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            # V4 enables thinking by default. Translation is a deterministic
            # transformation task, so thinking only adds latency and tokens.
            "thinking": {"type": "disabled"},
            # Give JSON enough room while keeping accidental runaway output
            # bounded. DeepSeek may otherwise return a truncated JSON object.
            "max_tokens": max(2048, min(16384, sum(len(str(item.get("text", ""))) for item in items) * 2 + 1024)),
            "stream": False,
        }
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                self.usage["api_attempts"] += 1
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self.usage["requests"] += 1
                for key, value in payload.get("usage", {}).items():
                    if key in self.usage and isinstance(value, int):
                        self.usage[key] += value
                choice = payload["choices"][0]
                finish_reason = str(choice.get("finish_reason") or "unknown")
                reasons = self.usage["finish_reasons"]
                reasons[finish_reason] = reasons.get(finish_reason, 0) + 1
                content = choice["message"]["content"]
                parsed = json.loads(content)
                translations = parsed.get("translations", parsed if isinstance(parsed, list) else [])
                result = {int(item["id"]): str(item["text"]) for item in translations}
                missing = {int(item["id"]) for item in items} - set(result)
                if missing:
                    self.usage["schema_failures"] += 1
                    # Do not repeat the same large request four times. The
                    # caller will preserve valid items and repair only missing
                    # IDs, splitting the batch when necessary.
                    raise IncompleteResponseError(missing, result, finish_reason)
                return result
            except IncompleteResponseError:
                raise
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = DeepSeekError(f"DeepSeek HTTP {exc.code}: {detail}")
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    break
            except (
                urllib.error.URLError,
                TimeoutError,
                json.JSONDecodeError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                DeepSeekError,
            ) as exc:
                last_error = exc
            if attempt < 3:
                self.usage["transport_retries"] += 1
                time.sleep((2**attempt) + random.random())
        raise DeepSeekError(f"DeepSeek 请求失败：{last_error}")

    def _request_resilient(
        self,
        items: list[dict],
        review: bool = False,
        depth: int = 0,
        single_retry: int = 0,
    ) -> dict[int, str]:
        """Recover omitted IDs and recursively split batches that remain invalid."""
        if not items:
            return {}
        try:
            result = self._request(items, review=True) if review else self._request(items)
            missing = {int(item["id"]) for item in items} - set(result)
            if missing:
                raise IncompleteResponseError(missing, result)
            return result
        except IncompleteResponseError as exc:
            result = dict(exc.partial)
            missing_items = [item for item in items if int(item["id"]) in exc.missing]
            self.usage["recovered_segments"] += len(result)
            if result and missing_items:
                self.usage["repair_requests"] += 1
                result.update(self._request_resilient(missing_items, review, depth + 1))
                return result
            if len(items) > 1:
                midpoint = len(items) // 2
                self.usage["split_retries"] += 1
                left = self._request_resilient(items[:midpoint], review, depth + 1)
                right = self._request_resilient(items[midpoint:], review, depth + 1)
                left.update(right)
                return left
            # A single segment can still be a transient model-format failure.
            # Retry it twice before surfacing a precise terminal error.
            if single_retry < 2:
                self.usage["repair_requests"] += 1
                return self._request_resilient(items, review, depth + 1, single_retry + 1)
            raise DeepSeekError(f"单段翻译仍未返回，段落编号：{items[0]['id']}") from exc

    def translate_many(
        self,
        texts: Sequence[str],
        progress: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        output = list(texts)
        indexes_by_text: dict[str, list[int]] = {}
        for index, text in enumerate(texts):
            if not is_translatable(text):
                continue
            indexes_by_text.setdefault(text, []).append(index)
        cached_values = {} if self.force_refresh else self.cache.get_many(
            self.source_language, self.target_language, list(indexes_by_text), self._cache_signature
        )
        pending: list[str] = []
        for text, indexes in indexes_by_text.items():
            if text in cached_values:
                for index in indexes:
                    output[index] = cached_values[text]
                self.usage["cache_hits"] += len(indexes)
            else:
                pending.append(text)
        total = len(pending)
        for start in range(0, total, self.batch_size):
            batch = pending[start : start + self.batch_size]
            protected = [protect_text(text) for text in batch]
            items = [{"id": i, "text": value.text} for i, value in enumerate(protected)]
            translated = self._request_resilient(items)
            cache_pairs = []
            for local_index, (source, protected_text) in enumerate(zip(batch, protected)):
                value = protected_text.restore(translated[local_index]).strip()
                for output_index in indexes_by_text[source]:
                    output[output_index] = value
                cache_pairs.append((source, value))
            self.cache.put_many(self.source_language, self.target_language, cache_pairs, self._cache_signature)
            if progress:
                progress(min(start + len(batch), total), total)
        if self.quality_review and self.pure_target_language:
            self._review_residuals(texts, output, indexes_by_text)
        return output

    def _needs_review(self, source: str, translated: str) -> bool:
        if self.target_language != "zh" or not is_translatable(source):
            return False
        protected = protect_text(translated).text
        visible = PLACEHOLDER_RE.sub("", protected)
        words = LATIN_WORD_RE.findall(visible)
        if not words:
            return False
        # Short all-caps tokens are normally units, Incoterms or engineering abbreviations.
        if not CJK_RE.search(translated) and all(word.isupper() and len(word) <= 5 for word in words):
            return False
        if CJK_RE.search(translated):
            return True
        return normalize_for_compare(source) == normalize_for_compare(translated) or len(" ".join(words)) >= 6

    def _review_residuals(self, sources: Sequence[str], output: list[str], indexes_by_text: dict[str, list[int]]) -> None:
        suspects = []
        for source in indexes_by_text:
            first_index = indexes_by_text[source][0]
            if self._needs_review(source, output[first_index]):
                suspects.append(source)
        for start in range(0, len(suspects), self.batch_size):
            batch = suspects[start : start + self.batch_size]
            protected = [protect_text(text) for text in batch]
            items = [{"id": i, "text": value.text} for i, value in enumerate(protected)]
            reviewed = self._request_resilient(items, review=True)
            cache_pairs = []
            for local_index, (source, protected_text) in enumerate(zip(batch, protected)):
                value = protected_text.restore(reviewed[local_index]).strip()
                for output_index in indexes_by_text[source]:
                    output[output_index] = value
                cache_pairs.append((source, value))
            self.cache.put_many(self.source_language, self.target_language, cache_pairs, self._cache_signature)
            self.usage["quality_retries"] += len(batch)


def normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


class IdentityTranslator:
    """Offline translator used by layout tests; deliberately makes no network calls."""

    usage: dict = {}

    def translate_many(self, texts: Sequence[str], progress=None) -> list[str]:
        if progress:
            progress(len(texts), len(texts))
        return list(texts)
