from __future__ import annotations

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("data.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS udp_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                sink_id TEXT,
                sense_id TEXT,
                msg TEXT,
                timestamp TEXT,
                rssi INTEGER,
                first_8_bytes TEXT,
                data TEXT
            )
            """
        )
        ensure_column(conn, "timestamp", "TEXT")
        ensure_column(conn, "rssi", "INTEGER")
        ensure_column(conn, "first_8_bytes", "TEXT")
        ensure_column(conn, "data", "TEXT")


def ensure_column(conn: sqlite3.Connection, name: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(udp_messages)").fetchall()
    }
    if name not in columns:
        conn.execute(f"ALTER TABLE udp_messages ADD COLUMN {name} {definition}")


def insert_message(sink_id: str, sense_id: str, msg: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO udp_messages (received_at, sink_id, sense_id, msg)
            VALUES (?, ?, ?, ?)
            """,
            (local_received_at(), sink_id, sense_id, msg),
        )


def insert_packet(
    timestamp: str,
    rssi: int,
    first_8_bytes: str,
    data: list[str],
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO udp_messages
                (received_at, sink_id, sense_id, msg, timestamp, rssi, first_8_bytes, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_received_at(),
                "",
                "",
                "",
                timestamp,
                rssi,
                first_8_bytes,
                json.dumps(data),
            ),
        )


def local_received_at() -> str:
    """Return the receiving server's local timestamp with its UTC offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def get_messages() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                id,
                received_at,
                sink_id,
                sense_id,
                msg,
                timestamp,
                rssi,
                first_8_bytes,
                data
            FROM udp_messages
            ORDER BY id DESC
            """
        ).fetchall()
