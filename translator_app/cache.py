from __future__ import annotations

import hashlib
import math
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from .config import app_data_dir


DEFAULT_MAX_CACHE_BYTES = 100 * 1024 * 1024
CACHE_TRIM_TARGET_RATIO = 0.90


class TranslationCache:
    def __init__(self, path: Path | None = None, max_cache_bytes: int = DEFAULT_MAX_CACHE_BYTES):
        self.path = path or app_data_dir() / "translations.sqlite3"
        self.max_cache_bytes = max(0, max_cache_bytes)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS translations (
                    cache_key TEXT PRIMARY KEY,
                    source_language TEXT NOT NULL,
                    target_language TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self):
        return sqlite3.connect(self.path, timeout=30)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def key(source_language: str, target_language: str, text: str, glossary_signature: str = "") -> str:
        raw = "\0".join((source_language, target_language, glossary_signature, text))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, source_language: str, target_language: str, text: str, glossary_signature: str = "") -> str | None:
        cache_key = self.key(source_language, target_language, text, glossary_signature)
        with self._lock, self._connection() as conn:
            row = conn.execute(
                "SELECT translated_text FROM translations WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return row[0] if row else None

    def put(self, source_language: str, target_language: str, text: str, translated: str, glossary_signature: str = "") -> None:
        cache_key = self.key(source_language, target_language, text, glossary_signature)
        with self._lock, self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO translations
                (cache_key, source_language, target_language, source_text, translated_text)
                VALUES (?, ?, ?, ?, ?)
                """,
                (cache_key, source_language, target_language, text, translated),
            )
        self._enforce_size_limit()

    def get_many(self, source_language: str, target_language: str, texts: list[str], glossary_signature: str = "") -> dict[str, str]:
        if not texts:
            return {}
        key_to_text = {self.key(source_language, target_language, text, glossary_signature): text for text in texts}
        found: dict[str, str] = {}
        with self._lock, self._connection() as conn:
            keys = list(key_to_text)
            for start in range(0, len(keys), 800):
                chunk = keys[start : start + 800]
                placeholders = ",".join("?" for _ in chunk)
                for cache_key, translated in conn.execute(
                    f"SELECT cache_key, translated_text FROM translations WHERE cache_key IN ({placeholders})", chunk
                ):
                    found[key_to_text[cache_key]] = translated
        return found

    def put_many(self, source_language: str, target_language: str, pairs: list[tuple[str, str]], glossary_signature: str = "") -> None:
        if not pairs:
            return
        rows = [
            (self.key(source_language, target_language, source, glossary_signature), source_language, target_language, source, translated)
            for source, translated in pairs
        ]
        with self._lock, self._connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO translations
                (cache_key, source_language, target_language, source_text, translated_text)
                VALUES (?, ?, ?, ?, ?)""",
                rows,
            )
        self._enforce_size_limit()

    def delete_many(self, source_language: str, target_language: str, texts: list[str], glossary_signature: str = "") -> None:
        """Remove selected entries without clearing unrelated translation history."""
        if not texts:
            return
        keys = [self.key(source_language, target_language, text, glossary_signature) for text in texts]
        with self._lock, self._connection() as conn:
            for start in range(0, len(keys), 800):
                chunk = keys[start : start + 800]
                placeholders = ",".join("?" for _ in chunk)
                conn.execute(f"DELETE FROM translations WHERE cache_key IN ({placeholders})", chunk)

    def _enforce_size_limit(self) -> int:
        """Trim oldest rows and compact the database when it exceeds 100 MB."""
        if not self.max_cache_bytes or not self.path.exists() or self.path.stat().st_size <= self.max_cache_bytes:
            return 0
        deleted = 0
        target_bytes = int(self.max_cache_bytes * CACHE_TRIM_TARGET_RATIO)
        with self._lock:
            for _attempt in range(3):
                file_size = self.path.stat().st_size
                if file_size <= target_bytes:
                    break
                conn = self._connect()
                try:
                    row_count = int(conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0])
                    if not row_count:
                        break
                    # Delete enough oldest rows to reach the target, plus a small
                    # margin so compaction is not triggered again immediately.
                    fraction = min(1.0, max(0.05, 1.0 - (target_bytes / file_size) + 0.03))
                    remove_count = min(row_count, max(1, math.ceil(row_count * fraction)))
                    conn.execute(
                        """DELETE FROM translations WHERE rowid IN (
                        SELECT rowid FROM translations
                        ORDER BY created_at ASC, rowid ASC LIMIT ?
                        )""",
                        (remove_count,),
                    )
                    conn.commit()
                    deleted += remove_count
                    # DELETE frees logical pages; VACUUM returns them to Windows.
                    conn.execute("VACUUM")
                    conn.commit()
                finally:
                    conn.close()
        return deleted
