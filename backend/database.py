import sqlite3
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
                sink_id TEXT NOT NULL,
                sense_id TEXT NOT NULL,
                msg TEXT NOT NULL
            )
            """
        )


def insert_message(sink_id: str, sense_id: str, msg: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO udp_messages (sink_id, sense_id, msg) VALUES (?, ?, ?)",
            (sink_id, sense_id, msg),
        )


def get_messages() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, received_at, sink_id, sense_id, msg
            FROM udp_messages
            ORDER BY id DESC
            """
        ).fetchall()
