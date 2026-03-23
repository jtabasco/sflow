import sqlite3
import threading
from datetime import datetime


PAGE_SIZE = 50


class Database:
    def __init__(self, path: str = "sflow.db"):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    text      TEXT NOT NULL,
                    duration  REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            self._conn.commit()

    def save_transcription(self, text: str, duration: float):
        created_at = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self._conn.execute(
                "INSERT INTO transcriptions (text, duration, created_at) VALUES (?, ?, ?)",
                (text, duration, created_at),
            )
            self._conn.commit()

    def get_transcriptions(self, page: int, search: str) -> tuple[list[dict], int]:
        offset = (page - 1) * PAGE_SIZE
        with self._lock:
            if search:
                pattern = f"%{search}%"
                total = self._conn.execute(
                    "SELECT COUNT(*) FROM transcriptions WHERE text LIKE ?", (pattern,)
                ).fetchone()[0]
                rows = self._conn.execute(
                    "SELECT * FROM transcriptions WHERE text LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?",
                    (pattern, PAGE_SIZE, offset),
                ).fetchall()
            else:
                total = self._conn.execute(
                    "SELECT COUNT(*) FROM transcriptions"
                ).fetchone()[0]
                rows = self._conn.execute(
                    "SELECT * FROM transcriptions ORDER BY id DESC LIMIT ? OFFSET ?",
                    (PAGE_SIZE, offset),
                ).fetchall()
        return [dict(r) for r in rows], total

    def get_setting(self, key: str, default: str = "") -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            self._conn.commit()

    def close(self):
        self._conn.close()
