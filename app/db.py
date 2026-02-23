from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("brainrot.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                gemini_api_key TEXT,
                veo_api_key TEXT,
                youtube_access_token TEXT,
                instagram_access_token TEXT,
                youtube_channel_id TEXT,
                instagram_account_id TEXT
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                niche TEXT NOT NULL,
                tone TEXT NOT NULL,
                prompt_extra TEXT,
                schedule_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'scheduled',
                output_log TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
