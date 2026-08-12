from __future__ import annotations

import base64
import ctypes
import json
import os
from ctypes import wintypes
from pathlib import Path

from .config import app_data_dir
from .i18n import tr


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class SecretStore:
    """Store the API key using Windows DPAPI; never write plaintext to disk."""

    def __init__(self, path: Path | None = None, env_name: str | None = "DEEPSEEK_API_KEY"):
        self.path = path or app_data_dir() / "deepseek.key"
        self.env_name = env_name

    @staticmethod
    def _blob(data: bytes):
        buffer = ctypes.create_string_buffer(data)
        blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def save(self, secret: str) -> None:
        if not secret:
            self.clear()
            return
        if os.name != "nt":
            raise RuntimeError(tr("error.secure_store_windows"))
        in_blob, in_buffer = self._blob(secret.encode("utf-8"))
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        ok = crypt32.CryptProtectData(
            ctypes.byref(in_blob),
            "UniversalDocumentTranslator",
            None,
            None,
            None,
            0x01,
            ctypes.byref(out_blob),
        )
        if not ok:
            raise ctypes.WinError()
        try:
            encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            kernel32 = ctypes.windll.kernel32
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(out_blob.pbData)
            del in_buffer
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(base64.b64encode(encrypted))

    def load(self) -> str:
        env_key = os.environ.get(self.env_name, "") if self.env_name else ""
        if env_key:
            return env_key
        if not self.path.exists():
            return ""
        if os.name != "nt":
            return ""
        encrypted = base64.b64decode(self.path.read_bytes())
        in_blob, in_buffer = self._blob(encrypted)
        out_blob = DATA_BLOB()
        crypt32 = ctypes.windll.crypt32
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0x01, ctypes.byref(out_blob)
        )
        if not ok:
            raise ctypes.WinError()
        try:
            value = ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
        finally:
            kernel32 = ctypes.windll.kernel32
            kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            kernel32.LocalFree.restype = ctypes.c_void_p
            kernel32.LocalFree(out_blob.pbData)
            del in_buffer
        return value

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()


class ProviderSecretStore:
    """DPAPI-encrypted API keys indexed by provider profile id."""

    def __init__(self, path: Path | None = None, legacy: SecretStore | None = None):
        self.path = path or app_data_dir() / "provider-keys.dat"
        self._encrypted = SecretStore(self.path, env_name=None)
        self.legacy = legacy or SecretStore()

    def load_all(self) -> dict[str, str]:
        try:
            raw = self._encrypted.load()
            values = json.loads(raw) if raw else {}
            if raw and isinstance(values, dict):
                return {str(key): str(value) for key, value in values.items() if value}
        except (ValueError, TypeError, json.JSONDecodeError, OSError):
            pass
        try:
            legacy_key = self.legacy.load()
        except (ValueError, TypeError, OSError):
            legacy_key = ""
        return {"deepseek-default": legacy_key} if legacy_key else {}

    def save_all(self, values: dict[str, str]) -> None:
        clean = {str(key): str(value).strip() for key, value in values.items() if str(value).strip()}
        if clean:
            self._encrypted.save(json.dumps(clean, ensure_ascii=False, sort_keys=True))
            if self.legacy.path != self._encrypted.path:
                self.legacy.clear()
        else:
            self._encrypted.clear()
            if self.legacy.path != self._encrypted.path:
                self.legacy.clear()

    def load(self, profile_id: str) -> str:
        return self.load_all().get(profile_id, "")

    def save(self, profile_id: str, secret: str) -> None:
        values = self.load_all()
        if secret.strip():
            values[profile_id] = secret.strip()
        else:
            values.pop(profile_id, None)
        self.save_all(values)

    def clear(self, profile_id: str | None = None) -> None:
        if profile_id is None:
            self._encrypted.clear()
            if self.legacy.path != self._encrypted.path:
                self.legacy.clear()
            return
        values = self.load_all()
        values.pop(profile_id, None)
        self.save_all(values)
