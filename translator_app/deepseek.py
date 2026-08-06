from __future__ import annotations

import json
import hashlib
import os
import random
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed

from .cache import TranslationCache
from .i18n import tr
from .providers import ProviderProfile, models_url, normalize_url
from .text_utils import (
    glossary_signature,
    has_internal_placeholder,
    is_translatable,
    placeholder_indexes,
    protect_text,
)


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

CACHE_POLICY_VERSION = "v5-segment-identity"
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LATIN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z-]{1,}")
PLACEHOLDER_RE = re.compile(r"__UDT_\d{4}__")
SEGMENT_MARKER_RE = re.compile(r"\[\[UDT_SEGMENT_(\d{4})\]\]")
SEGMENT_MARKER_FLEX_RE = re.compile(
    r"\[\s*\[\s*UDT\s*[_\s-]*SEGMENT\s*[_\s-]*(\d{4})\s*\]\s*\]",
    re.IGNORECASE,
)


def _decode_json_content(content: object):
    """Accept strict JSON and the fenced JSON returned by non-JSON-mode APIs."""
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, count=1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise
RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504}
LONG_SEGMENT_BATCH_THRESHOLD = 1200


class AdaptiveRateLimiter:
    """Small thread-safe limiter that backs off on 429 without user tuning.

    Translation requests are I/O bound, so a few in-flight batches reduce idle
    network time without changing prompts or model settings. Starts are still
    spaced to avoid a burst, and a provider-side rate-limit response
    immediately lowers the rate for every worker.
    """

    def __init__(self, initial_qps: float, minimum_qps: float = 1.0, maximum_qps: float | None = None):
        initial = max(minimum_qps, float(initial_qps))
        self.minimum_qps = max(0.25, float(minimum_qps))
        self.maximum_qps = max(initial, float(maximum_qps or initial))
        self._qps = min(self.maximum_qps, initial)
        self._next_start = 0.0
        self._successes_since_throttle = 0
        self._generation = 0
        self._lock = threading.Lock()

    @property
    def qps(self) -> float:
        with self._lock:
            return self._qps

    def acquire(self) -> None:
        while True:
            with self._lock:
                generation = self._generation
                now = time.monotonic()
                scheduled = max(now, self._next_start)
                self._next_start = scheduled + (1.0 / self._qps)
            delay = scheduled - now
            if delay > 0:
                time.sleep(delay)
            with self._lock:
                if generation == self._generation:
                    return

    def throttle(self, retry_after: float | None = None) -> None:
        with self._lock:
            self._qps = max(self.minimum_qps, self._qps * 0.5)
            self._successes_since_throttle = 0
            pause = retry_after if retry_after is not None else 1.0 / self._qps
            self._generation += 1
            # Invalidate starts reserved under the old rate. Waiting workers
            # notice the generation change and reserve again at the lower QPS.
            self._next_start = time.monotonic() + max(0.0, pause)

    def record_success(self) -> None:
        with self._lock:
            self._successes_since_throttle += 1
            # Recover cautiously after a temporary provider-side slowdown.
            if self._successes_since_throttle >= 8 and self._qps < self.maximum_qps:
                self._qps = min(self.maximum_qps, self._qps + 0.5)
                self._successes_since_throttle = 0


class DeepSeekError(RuntimeError):
    pass


class IncompleteResponseError(DeepSeekError):
    """The API returned valid JSON, but omitted one or more requested IDs."""

    def __init__(self, missing: set[int], partial: dict[int, str], finish_reason: str = ""):
        self.missing = missing
        self.partial = partial
        self.finish_reason = finish_reason
        reason = (
            tr("error.finish_reason", reason=finish_reason)
            if finish_reason
            else ""
        )
        super().__init__(
            tr(
                "error.missing_segments",
                segments=sorted(missing),
                reason=reason,
            )
        )


class DeepSeekTranslator:
    # Engines may aggregate independent document units into one call so this
    # translator can schedule its internal batches concurrently.
    supports_parallel_batches = True

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
        provider_id: str = "deepseek",
        api_style: str = "openai",
        supports_json_mode: bool = True,
        supports_thinking_control: bool = True,
        requires_api_key: bool = True,
        azure_api_version: str = "2024-10-21",
    ):
        if requires_api_key and not api_key.strip():
            raise ValueError(tr("error.api_key_required"))
        self.api_key = api_key.strip()
        self.model = model.strip() or "deepseek-v4-flash"
        self.source_language = source_language
        self.target_language = target_language
        self.glossary = glossary or {}
        self.cache = cache or TranslationCache()
        self.timeout = timeout
        self.batch_size = max(1, min(batch_size, 100))
        self.base_url = base_url
        self.provider_id = provider_id
        self.api_style = api_style
        self.supports_json_mode = supports_json_mode
        self.supports_thinking_control = supports_thinking_control
        self.requires_api_key = requires_api_key
        self.azure_api_version = azure_api_version
        self.pure_target_language = pure_target_language
        self.quality_review = quality_review
        self.force_refresh = force_refresh
        self._usage_lock = threading.Lock()
        self._worker_limit = self._automatic_worker_limit()
        self._rate_limiter = AdaptiveRateLimiter(
            initial_qps=float(self._worker_limit),
            maximum_qps=float(self._worker_limit),
        )
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
            "rate_limit_events": 0,
            "parallel_workers": self._worker_limit,
            "finish_reasons": {},
            "thinking_mode": "disabled",
            "provider": self.provider_id,
        }
        policy = "|".join((
            CACHE_POLICY_VERSION,
            self.provider_id,
            self.api_style,
            normalize_url(self.base_url),
            self.model,
            f"pure={int(self.pure_target_language)}",
            f"review={int(self.quality_review)}",
            glossary_signature(self.glossary),
        ))
        self._cache_signature = hashlib.sha256(policy.encode("utf-8")).hexdigest()

    @classmethod
    def from_profile(cls, profile: ProviderProfile, api_key: str, **kwargs):
        preset = profile.preset
        return cls(
            api_key=api_key,
            model=profile.model,
            base_url=profile.base_url,
            provider_id=profile.provider,
            api_style=profile.api_style,
            supports_json_mode=preset.supports_json_mode,
            supports_thinking_control=preset.supports_thinking_control,
            requires_api_key=preset.requires_api_key,
            azure_api_version=profile.azure_api_version,
            **kwargs,
        )

    def _automatic_worker_limit(self) -> int:
        """Choose safe network concurrency automatically; no quality tier."""
        model = self.model.casefold()
        if "reasoner" in model:
            default = 2
        elif "pro" in model:
            default = 3
        else:
            default = 4
        override = os.environ.get("UDT_TRANSLATION_CONCURRENCY", "").strip()
        if override:
            try:
                return max(1, min(6, int(override)))
            except ValueError:
                pass
        return default

    def _bump_usage(self, key: str, amount: int = 1) -> None:
        with self._usage_lock:
            self.usage[key] = int(self.usage.get(key, 0)) + amount

    def _record_response_usage(self, payload: dict, finish_reason: str) -> None:
        raw_usage = payload.get("usage", {})
        if self.api_style == "anthropic":
            raw_usage = {
                "prompt_tokens": raw_usage.get("input_tokens", 0),
                "completion_tokens": raw_usage.get("output_tokens", 0),
                "total_tokens": raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0),
            }
        with self._usage_lock:
            for key, value in raw_usage.items():
                if key in self.usage and isinstance(value, int):
                    self.usage[key] += value
            reasons = self.usage["finish_reasons"]
            reasons[finish_reason] = reasons.get(finish_reason, 0) + 1

    def _redact_error(self, value: object) -> str:
        text = str(value)
        if self.api_key:
            text = text.replace(self.api_key, "***")
        return re.sub(
            r"((?:api[-_ ]?key|authorization)(?:=|:|\s)+)(?:bearer\s+)?\S+",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )

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
            "每段开头的 [[UDT_SEGMENT_0000]] 是段落身份标记，必须原样保留在该段译文开头，"
            "不得删除、改写、交换或复制到其他 id。"
            "返回严格 JSON：{\"translations\":[{\"id\":0,\"text\":\"...\"}]}，id 必须与输入一致。"
            + (f"\n必须采用以下术语表：\n{glossary}" if glossary else "")
        )

    def _placeholder_counts_are_valid(self, source: str, translated: str) -> bool:
        """Keep codes exact while permitting a genuine bilingual merge.

        Target-only mode merges equivalent language halves. A code repeated
        in both halves should then occur as many times as it did in either one
        half, rather than as many times as it did in both halves combined.
        """
        expected = Counter(placeholder_indexes(source))
        actual = Counter(placeholder_indexes(translated))
        if actual == expected:
            return True
        if not self.pure_target_language or set(actual) != set(expected):
            return False

        branch_split = None

        # Packing lists commonly repeat the same material number before the
        # English and German descriptions. The second occurrence is a strong,
        # format-derived bilingual boundary even when no slash is present.
        leading_id = re.match(r"^\s*(\d{5,}(?:\.\d+)?)\s*[,;:]?", source)
        if leading_id:
            remainder_start = leading_id.end()
            repeated_id = re.search(
                rf"(?<!\w){re.escape(leading_id.group(1))}(?=\s*[,;:])",
                source[remainder_start:],
            )
            if repeated_id:
                candidate = remainder_start + repeated_id.start()
                if candidate >= 12 and len(source) - candidate >= 12:
                    branch_split = candidate

        # Long legal notes often use a central slash between complete language
        # versions. Internal slashes near either edge are not treated as the
        # language boundary.
        separators = [
            match
            for match in re.finditer(r"\s+/\s+", source)
            if match.start() >= 120 and len(source) - match.end() >= 120
        ]
        if branch_split is None and separators:
            separator = min(
                separators,
                key=lambda match: abs(match.start() - len(source) / 2),
            )
            branch_split = separator.start()

        # A small number of rows omit both the repeated material number and a
        # slash. Only accept an inferred boundary when the text itself contains
        # clear English/German parallel markers and a repeated protected value.
        english_marker = re.search(
            r"\b(?:the|and|with|without|for|from|to|of|or|according|length)\b",
            source,
            re.IGNORECASE,
        )
        german_marker = re.search(
            r"\b(?:der|die|das|und|mit|ohne|nach|von|für|auf|aus|oder|nicht|zum|zur|länge)\b",
            source,
            re.IGNORECASE,
        )
        if branch_split is None and english_marker and german_marker:
            positions_by_index: dict[int, list[re.Match]] = {}
            for match in PLACEHOLDER_RE.finditer(source):
                positions_by_index.setdefault(
                    int(match.group(0)[6:10]),
                    [],
                ).append(match)
            candidates = []
            for positions in positions_by_index.values():
                if len(positions) >= 2 and len(positions) % 2 == 0:
                    half = len(positions) // 2
                    candidates.append(
                        (positions[half - 1].end() + positions[half].start()) // 2
                    )
            if candidates:
                candidate = min(
                    candidates,
                    key=lambda value: abs(value - len(source) / 2),
                )
                if candidate >= 12 and len(source) - candidate >= 12:
                    branch_split = candidate

        if branch_split is None:
            return False
        left = Counter(placeholder_indexes(source[:branch_split]))
        right = Counter(placeholder_indexes(source[branch_split:]))
        merged = left | right
        return bool(set(left) & set(right)) and actual == merged

    def _request(self, items: list[dict], review: bool = False) -> dict[int, str]:
        system_prompt = self._system_prompt()
        if review:
            system_prompt += (
                "\n这是质量复核：上次结果可能残留了源语言。重新翻译每一段，确保普通词、物料名称和双语字段完全转换为目标语言，"
                "同时仍须保留代码、单位、型号、公司名和地址。"
            )
        wire_items = [
            {
                **item,
                "text": (
                    f"[[UDT_SEGMENT_{int(item['id']):04d}]] "
                    f"{item.get('text', '')}"
                ),
            }
            for item in items
        ]
        messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"segments": wire_items},
                        ensure_ascii=False,
                    ),
                },
            ]
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.1,
            # Give JSON enough room while keeping accidental runaway output
            # bounded. DeepSeek may otherwise return a truncated JSON object.
            "max_tokens": max(
                2048,
                min(
                    16384,
                    sum(
                        len(str(item.get("text", "")))
                        for item in wire_items
                    )
                    * 2
                    + 1024,
                ),
            ),
            "stream": False,
        }
        if self.supports_json_mode:
            body["response_format"] = {"type": "json_object"}
        if self.supports_thinking_control:
            # DeepSeek V4 enables thinking by default; deterministic document
            # translation does not benefit from the extra latency and tokens.
            body["thinking"] = {"type": "disabled"}
        headers = {"Content-Type": "application/json"}
        endpoint = self.base_url
        if self.api_style == "anthropic":
            body = {
                "model": self.model,
                "system": system_prompt,
                "messages": messages[1:],
                "temperature": 0.1,
                "max_tokens": body["max_tokens"],
            }
            headers.update({
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            })
        elif self.api_style == "azure":
            headers["api-key"] = self.api_key
            if "api-version=" not in endpoint:
                separator = "&" if "?" in endpoint else "?"
                endpoint = f"{endpoint}{separator}api-version={self.azure_api_version}"
            # Azure deployments identify the model in the URL. Some compatible
            # gateways reject a second model identifier in the request body.
            body.pop("model", None)
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                self._rate_limiter.acquire()
                self._bump_usage("api_attempts")
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                self._bump_usage("requests")
                if self.api_style == "anthropic":
                    finish_reason = str(payload.get("stop_reason") or "unknown")
                    content = "".join(
                        str(block.get("text", ""))
                        for block in payload.get("content", [])
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                else:
                    choice = payload["choices"][0]
                    finish_reason = str(choice.get("finish_reason") or "unknown")
                    content = choice["message"]["content"]
                self._record_response_usage(payload, finish_reason)
                requested_ids = {int(item["id"]) for item in items}
                try:
                    parsed = _decode_json_content(content)
                    translations = (
                        parsed.get("translations", [])
                        if isinstance(parsed, dict)
                        else parsed
                        if isinstance(parsed, list)
                        else []
                    )
                    if not isinstance(translations, list):
                        raise TypeError("translations must be a list")
                    result: dict[int, str] = {}
                    duplicate_ids: set[int] = set()
                    for item in translations:
                        item_id = int(item["id"])
                        if item_id in result:
                            duplicate_ids.add(item_id)
                        result[item_id] = str(item["text"])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                    self._bump_usage("schema_failures")
                    # Truncated JSON (commonly finish_reason=length) is a
                    # batch-size problem, not a reason to repeat the identical
                    # large request four times. Reuse the existing resilient
                    # path so it halves the batch and preserves all successes.
                    raise IncompleteResponseError(
                        requested_ids,
                        {},
                        finish_reason or "invalid JSON",
                    ) from exc
                unexpected = set(result) - requested_ids
                if duplicate_ids or unexpected:
                    self._bump_usage("schema_failures")
                    raise IncompleteResponseError(
                        requested_ids,
                        {},
                        "duplicate or unexpected segment ids",
                    )
                missing = requested_ids - set(result)
                if missing:
                    self._bump_usage("schema_failures")
                    # Do not repeat the same large request four times. The
                    # caller will preserve valid items and repair only missing
                    # IDs, splitting the batch when necessary.
                    raise IncompleteResponseError(missing, result, finish_reason)
                marker_invalid: set[int] = set()
                for item_id in requested_ids:
                    markers = [
                        int(match.group(1))
                        for match in SEGMENT_MARKER_RE.finditer(
                            result.get(item_id, "")
                        )
                    ]
                    if markers != [item_id]:
                        marker_invalid.add(item_id)
                    else:
                        result[item_id] = SEGMENT_MARKER_RE.sub(
                            "",
                            result[item_id],
                            count=1,
                        ).lstrip()
                if marker_invalid:
                    self._bump_usage("schema_failures")
                    valid = {
                        item_id: value
                        for item_id, value in result.items()
                        if item_id not in marker_invalid
                    }
                    raise IncompleteResponseError(
                        marker_invalid,
                        valid,
                        "invalid segment identity marker",
                    )
                invalid = {
                    int(item["id"])
                    for item in items
                    if not self._placeholder_counts_are_valid(
                        str(item.get("text", "")),
                        result.get(int(item["id"]), ""),
                    )
                }
                if invalid:
                    self._bump_usage("schema_failures")
                    valid = {item_id: value for item_id, value in result.items() if item_id not in invalid}
                    raise IncompleteResponseError(invalid, valid, "invalid placeholders")
                self._rate_limiter.record_success()
                return result
            except IncompleteResponseError:
                raise
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:1000]
                last_error = DeepSeekError(f"{self.provider_id} HTTP {exc.code}: {self._redact_error(detail)}")
                if exc.code == 429:
                    retry_after = None
                    try:
                        retry_after = float(exc.headers.get("Retry-After", ""))
                    except (AttributeError, TypeError, ValueError):
                        pass
                    self._rate_limiter.throttle(retry_after)
                    self._bump_usage("rate_limit_events")
                if exc.code not in RETRYABLE_HTTP_CODES:
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
                self._bump_usage("transport_retries")
                time.sleep((2**attempt) + random.random())
        raise DeepSeekError(
            tr(
                "error.deepseek_request",
                reason=self._redact_error(last_error),
            )
        )

    def list_models(self) -> list[str]:
        endpoint = models_url(
            ProviderProfile(
                id="runtime",
                name=self.provider_id,
                provider=self.provider_id,
                api_style=self.api_style,
                base_url=self.base_url,
                model=self.model,
                azure_api_version=self.azure_api_version,
            )
        )
        if not endpoint:
            return []
        headers = {"Accept": "application/json"}
        if self.api_style == "azure":
            headers["api-key"] = self.api_key
        elif self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(endpoint, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=min(self.timeout, 30)) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return sorted(
            str(item["id"])
            for item in payload.get("data", [])
            if isinstance(item, dict) and item.get("id")
        )

    def test_connection(self) -> tuple[bool, str]:
        try:
            models = self.list_models()
            if models:
                return True, f"{len(models)} models"
            # Providers without a model-list endpoint are verified with one
            # tiny structured translation request.
            self._request([{"id": 0, "text": "OK"}])
            return True, "OK"
        except Exception as exc:
            return False, self._redact_error(exc)

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
            self._bump_usage("recovered_segments", len(result))
            if result and missing_items:
                self._bump_usage("repair_requests")
                result.update(self._request_resilient(missing_items, review, depth + 1))
                return result
            if len(items) > 1:
                midpoint = len(items) // 2
                self._bump_usage("split_retries")
                left = self._request_resilient(items[:midpoint], review, depth + 1)
                right = self._request_resilient(items[midpoint:], review, depth + 1)
                left.update(right)
                return left
            # A single segment can still be a transient model-format failure.
            # Retry it twice before surfacing a precise terminal error.
            if single_retry < 2:
                self._bump_usage("repair_requests")
                return self._request_resilient(items, review, depth + 1, single_retry + 1)
            raise DeepSeekError(
                tr(
                    "error.single_segment_missing",
                    segment_id=items[0]["id"],
                )
            ) from exc

    def _translate_batch(self, batch: Sequence[str], review: bool = False) -> list[tuple[str, str]]:
        protected = [protect_text(text) for text in batch]
        items = [
            {
                "id": index,
                "text": value.text,
            }
            for index, value in enumerate(protected)
        ]
        translated = self._request_resilient(items, review=review)
        return [
            (source, protected_text.restore(translated[local_index]).strip())
            for local_index, (source, protected_text) in enumerate(zip(batch, protected))
        ]

    def _run_batches(
        self,
        texts: Sequence[str],
        *,
        review: bool = False,
        progress: Callable[[int, int], None] | None = None,
        on_completed: Callable[[list[tuple[str, str]]], None] | None = None,
    ) -> list[tuple[str, str]]:
        """Translate independent batches concurrently and checkpoint each success."""
        batches: list[list[str]] = []
        current: list[str] = []
        for text in texts:
            # A long legal note should not make dozens of short, already valid
            # segments wait for its repair path. Isolating it preserves context
            # inside the paragraph and lets every other batch checkpoint.
            if len(text) > LONG_SEGMENT_BATCH_THRESHOLD:
                if current:
                    batches.append(current)
                    current = []
                batches.append([text])
                continue
            current.append(text)
            if len(current) >= self.batch_size:
                batches.append(current)
                current = []
        if current:
            batches.append(current)
        if not batches:
            return []

        total = len(texts)
        done = 0
        completed_pairs: list[tuple[str, str]] = []

        def accept(pairs: list[tuple[str, str]]) -> None:
            nonlocal done
            # Persist before reporting progress. If another batch later fails,
            # a retry reuses every already completed segment.
            self.cache.put_many(
                self.source_language,
                self.target_language,
                pairs,
                self._cache_signature,
            )
            if on_completed:
                on_completed(pairs)
            completed_pairs.extend(pairs)
            done += len(pairs)
            if review:
                self._bump_usage("quality_retries", len(pairs))
            if progress:
                progress(min(done, total), total)

        worker_count = min(self._worker_limit, len(batches))
        if worker_count <= 1:
            for batch in batches:
                accept(self._translate_batch(batch, review=review))
            return completed_pairs

        failures: list[Exception] = []
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="udt-translate",
        ) as executor:
            batch_iterator = iter(batches)
            future_to_batch: dict[Future, list[str]] = {}

            def submit_next() -> bool:
                try:
                    batch = next(batch_iterator)
                except StopIteration:
                    return False
                future_to_batch[
                    executor.submit(self._translate_batch, batch, review)
                ] = batch
                return True

            for _ in range(worker_count):
                submit_next()
            while future_to_batch:
                # Keep only a bounded number of requests in flight. If one
                # batch fails permanently, no new batches are launched, while
                # already-running successes are still checkpointed.
                future = next(as_completed(tuple(future_to_batch)))
                future_to_batch.pop(future)
                try:
                    accept(future.result())
                except Exception as exc:
                    failures.append(exc)
                if not failures:
                    submit_next()
        if failures:
            raise failures[0]
        return completed_pairs

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
        repaired_cache_pairs: list[tuple[str, str]] = []
        stale_cache_texts: list[str] = []
        for source, cached in list(cached_values.items()):
            repaired = protect_text(source).restore(cached)
            if (
                has_internal_placeholder(repaired)
                or SEGMENT_MARKER_FLEX_RE.search(repaired)
            ):
                # Old versions could cache an un-restored or hallucinated UDT
                # placeholder or a segment-identity marker. Do not copy it
                # into another document: evict only the affected entry and
                # translate that segment again.
                stale_cache_texts.append(source)
                cached_values.pop(source, None)
            elif repaired != cached:
                cached_values[source] = repaired
                repaired_cache_pairs.append((source, repaired))
        if stale_cache_texts:
            self.cache.delete_many(
                self.source_language, self.target_language, stale_cache_texts, self._cache_signature
            )
        if repaired_cache_pairs:
            self.cache.put_many(
                self.source_language, self.target_language, repaired_cache_pairs, self._cache_signature
            )
        pending: list[str] = []
        for text, indexes in indexes_by_text.items():
            if text in cached_values:
                for index in indexes:
                    output[index] = cached_values[text]
                self._bump_usage("cache_hits", len(indexes))
            else:
                pending.append(text)

        def apply_pairs(pairs: list[tuple[str, str]]) -> None:
            for source, value in pairs:
                for output_index in indexes_by_text[source]:
                    output[output_index] = value

        self._run_batches(pending, progress=progress, on_completed=apply_pairs)
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

        def apply_pairs(pairs: list[tuple[str, str]]) -> None:
            for source, value in pairs:
                for output_index in indexes_by_text[source]:
                    output[output_index] = value

        self._run_batches(suspects, review=True, on_completed=apply_pairs)


def normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


class IdentityTranslator:
    """Offline translator used by layout tests; deliberately makes no network calls."""

    usage: dict = {}

    def translate_many(self, texts: Sequence[str], progress=None) -> list[str]:
        if progress:
            progress(len(texts), len(texts))
        return list(texts)


class FallbackTranslator:
    """Use the fallback after the primary provider has a terminal API failure."""

    supports_parallel_batches = True

    def __init__(self, primary: DeepSeekTranslator, fallback: DeepSeekTranslator | None = None):
        self.primary = primary
        self.fallback = fallback
        self._active = primary
        self.fallback_used = False

    def __getattr__(self, name):
        return getattr(self._active, name)

    @property
    def usage(self) -> dict:
        values = dict(self.primary.usage)
        if self.fallback:
            for key in ("prompt_tokens", "completion_tokens", "total_tokens", "requests", "api_attempts"):
                values[key] = int(values.get(key, 0)) + int(self.fallback.usage.get(key, 0))
        values["fallback_used"] = self.fallback_used
        return values

    def translate_many(self, texts: Sequence[str], progress=None) -> list[str]:
        try:
            return self._active.translate_many(texts, progress)
        except DeepSeekError:
            if self._active is not self.primary or self.fallback is None:
                raise
            self._active = self.fallback
            self.fallback_used = True
            return self.fallback.translate_many(texts, progress)

    def babeldoc_translator(self) -> DeepSeekTranslator | None:
        for candidate in (self._active, self.fallback):
            if candidate and candidate.api_style in {"openai", "azure"}:
                return candidate
        return None
