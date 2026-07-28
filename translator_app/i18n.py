"""Small, dependency-free internationalization layer for the desktop app.

The module deliberately has no Qt imports, so it can be loaded before the GUI
and used by the CLI, installer helpers and generated user guides as well.
"""

from __future__ import annotations

import locale
import os
import string
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .locales import CATALOGS, SUPPORTED_LANGUAGE_CODES


AUTO_LANGUAGE_CODES = frozenset({"", "auto", "default", "system"})
FALLBACK_LANGUAGE_CODES = ("en", "zh-CN")

_LANGUAGE_ALIASES = {
    "cn": "zh-CN",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh-hans-cn": "zh-CN",
    "zh-sg": "zh-CN",
    "chs": "zh-CN",
    "en": "en",
    "eng": "en",
    "ru": "ru",
    "rus": "ru",
    "es": "es",
    "spa": "es",
    "fr": "fr",
    "fra": "fr",
    "fre": "fr",
    "de": "de",
    "deu": "de",
    "ger": "de",
}


def _clean_language_code(code: object) -> str:
    """Return a comparison-friendly locale code without encoding/modifier."""

    if code is None:
        return ""
    value = str(code).strip().replace("_", "-")
    value = value.split(".", 1)[0].split("@", 1)[0]
    return value.strip("-").lower()


def _canonical_language(code: object) -> str | None:
    cleaned = _clean_language_code(code)
    if cleaned in AUTO_LANGUAGE_CODES:
        return "auto"
    direct = _LANGUAGE_ALIASES.get(cleaned)
    if direct:
        return direct
    # Regional variants such as en-US, ru-KZ and fr-CA use the supported base
    # language. Any Chinese locale currently uses the bundled simplified
    # Chinese catalog because it is the only Chinese UI shipped by the app.
    base = cleaned.split("-", 1)[0]
    if base == "zh":
        return "zh-CN"
    return _LANGUAGE_ALIASES.get(base)


def normalize_language_code(code: object, default: str = "en") -> str:
    """Normalize a saved/manual language code.

    ``auto``, ``system`` and an empty value normalize to ``"auto"``. Known
    regional variants normalize to one of ``zh-CN``, ``en``, ``ru``, ``es``,
    ``fr`` or ``de``. Unsupported values use ``default`` and finally English.
    Use :func:`resolve_language` when ``"auto"`` should be turned into the
    current system language.
    """

    normalized = _canonical_language(code)
    if normalized:
        return normalized
    fallback = _canonical_language(default)
    if fallback in SUPPORTED_LANGUAGE_CODES:
        return fallback
    return "en"


def _system_language_candidates() -> Iterator[str]:
    """Yield available OS locale hints without importing a GUI toolkit."""

    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name)
        if value:
            # LANGUAGE can contain a colon-separated preference list.
            yield from (part for part in value.split(":") if part)

    try:
        current = locale.getlocale()[0]
    except (AttributeError, TypeError, ValueError):
        current = None
    if current:
        yield current

    if os.name == "nt":
        # Python's process locale does not always reflect the Windows display
        # language, so ask the OS as a final, best-effort source.
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                yield buffer.value
        except (AttributeError, OSError):
            pass


def detect_system_language(candidates: Sequence[object] | None = None) -> str:
    """Return the closest bundled language for the current operating system."""

    values = candidates if candidates is not None else tuple(_system_language_candidates())
    for candidate in values:
        normalized = _canonical_language(candidate)
        if normalized in SUPPORTED_LANGUAGE_CODES:
            return normalized
    return "en"


def resolve_language(code: object = "auto") -> str:
    """Resolve a saved language selection to a concrete bundled catalog."""

    normalized = normalize_language_code(code)
    return detect_system_language() if normalized == "auto" else normalized


@dataclass(frozen=True)
class _MissingPlaceholder:
    name: str
    conversion: str | None = None

    def render(self, format_spec: str = "") -> str:
        conversion = f"!{self.conversion}" if self.conversion else ""
        spec = f":{format_spec}" if format_spec else ""
        return "{" + self.name + conversion + spec + "}"


class _SafeFormatter(string.Formatter):
    """Formatter that preserves unresolved fields instead of raising."""

    def get_value(self, key: object, args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
        try:
            return super().get_value(key, args, kwargs)
        except (IndexError, KeyError):
            return _MissingPlaceholder(str(key))

    def convert_field(self, value: Any, conversion: str | None) -> Any:
        if isinstance(value, _MissingPlaceholder):
            return _MissingPlaceholder(value.name, conversion)
        try:
            return super().convert_field(value, conversion)
        except (TypeError, ValueError):
            return value

    def format_field(self, value: Any, format_spec: str) -> str:
        if isinstance(value, _MissingPlaceholder):
            return value.render(format_spec)
        try:
            return super().format_field(value, format_spec)
        except (TypeError, ValueError):
            return str(value)


_FORMATTER = _SafeFormatter()


def format_message(template: object, /, **values: Any) -> str:
    """Safely interpolate a localized message.

    Missing values remain visible as ``{placeholder}``; malformed braces or an
    incompatible format specifier never crash the UI.
    """

    text = str(template)
    if not values and "{" not in text:
        return text
    try:
        return _FORMATTER.vformat(text, (), values)
    except (KeyError, IndexError, AttributeError, TypeError, ValueError):
        return text


def message_placeholders(template: object) -> frozenset[str]:
    """Return named placeholders used by a message, for resource validation."""

    names: set[str] = set()
    try:
        fields = _FORMATTER.parse(str(template))
        for _literal, field_name, _spec, _conversion in fields:
            if field_name:
                # ``item.name`` and ``item[index]`` both depend on ``item``.
                names.add(field_name.split(".", 1)[0].split("[", 1)[0])
    except ValueError:
        return frozenset()
    return frozenset(names)


class I18n:
    """Translation catalog bound to one resolved interface language."""

    def __init__(
        self,
        language: object = "auto",
        catalogs: Mapping[str, Mapping[str, str]] | None = None,
    ):
        self._catalogs = CATALOGS if catalogs is None else catalogs
        self._lock = threading.RLock()
        self._requested_language = "auto"
        self._language = "en"
        self.set_language(language)

    @property
    def requested_language(self) -> str:
        """Saved selection (possibly ``"auto"``)."""

        with self._lock:
            return self._requested_language

    @property
    def language(self) -> str:
        """Concrete catalog currently in use."""

        with self._lock:
            return self._language

    def set_language(self, code: object) -> str:
        """Select a language and return the concrete catalog code."""

        requested = normalize_language_code(code)
        resolved = detect_system_language() if requested == "auto" else requested
        with self._lock:
            self._requested_language = requested
            self._language = resolved
        return resolved

    def refresh_system_language(self) -> str:
        """Re-read the OS language when the saved selection is automatic."""

        with self._lock:
            requested = self._requested_language
        return self.set_language("auto") if requested == "auto" else self.language

    def has_key(self, key: str) -> bool:
        return any(key in catalog for catalog in self._catalogs.values())

    def _lookup(self, key: str, default: str | None) -> str:
        with self._lock:
            selected = self._language
        order = dict.fromkeys((selected, *FALLBACK_LANGUAGE_CODES))
        for code in order:
            catalog = self._catalogs.get(code, {})
            value = catalog.get(key)
            if value is not None:
                return value
        return default if default is not None else key

    def t(self, key: str, default: str | None = None, **values: Any) -> str:
        """Translate ``key`` and safely substitute named placeholders."""

        return format_message(self._lookup(key, default), **values)

    translate = t

    def language_choices(
        self,
        *,
        include_auto: bool = True,
        display_language: object | None = None,
    ) -> list[tuple[str, str]]:
        """Return ``(stored_code, label)`` pairs for a language combobox."""

        labels = self if display_language is None else I18n(display_language, self._catalogs)
        choices: list[tuple[str, str]] = []
        if include_auto:
            choices.append(("auto", labels.t("language.system")))
        choices.extend((code, labels.t(f"language.{code}")) for code in SUPPORTED_LANGUAGE_CODES)
        return choices


def validate_catalogs(
    catalogs: Mapping[str, Mapping[str, str]] | None = None,
) -> tuple[str, ...]:
    """Return structural/placeholder errors in locale resources."""

    resources = catalogs or CATALOGS
    english = resources.get("en", {})
    errors: list[str] = []
    base_keys = set(english)
    for code in SUPPORTED_LANGUAGE_CODES:
        catalog = resources.get(code)
        if catalog is None:
            errors.append(f"{code}: catalog missing")
            continue
        missing = sorted(base_keys - set(catalog))
        extra = sorted(set(catalog) - base_keys)
        if missing:
            errors.append(f"{code}: missing keys: {', '.join(missing)}")
        if extra:
            errors.append(f"{code}: extra keys: {', '.join(extra)}")
        for key in sorted(base_keys & set(catalog)):
            expected = message_placeholders(english[key])
            actual = message_placeholders(catalog[key])
            if actual != expected:
                errors.append(
                    f"{code}:{key}: placeholders {sorted(actual)} != {sorted(expected)}"
                )
    return tuple(errors)


_default_i18n = I18n()


def get_i18n() -> I18n:
    return _default_i18n


def set_language(code: object) -> str:
    """Set the process-wide interface language and return its concrete code."""

    return _default_i18n.set_language(code)


def get_language() -> str:
    return _default_i18n.language


def tr(key: str, default: str | None = None, **values: Any) -> str:
    """Translate using the process-wide catalog."""

    return _default_i18n.t(key, default, **values)


t = tr


@contextmanager
def use_language(code: object) -> Iterator[I18n]:
    """Temporarily change the process-wide language (primarily for tooling)."""

    previous = _default_i18n.requested_language
    _default_i18n.set_language(code)
    try:
        yield _default_i18n
    finally:
        _default_i18n.set_language(previous)


__all__ = [
    "AUTO_LANGUAGE_CODES",
    "FALLBACK_LANGUAGE_CODES",
    "I18n",
    "SUPPORTED_LANGUAGE_CODES",
    "detect_system_language",
    "format_message",
    "get_i18n",
    "get_language",
    "message_placeholders",
    "normalize_language_code",
    "resolve_language",
    "set_language",
    "t",
    "tr",
    "use_language",
    "validate_catalogs",
]
