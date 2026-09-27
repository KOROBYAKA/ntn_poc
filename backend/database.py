from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("old_data.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS udp_packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                src INTEGER,
                gw_timestamp TEXT,
                travel_time INTEGER,
                backend_timestamp TEXT,
                payload TEXT
            )
            """
        )


def insert_packet(
    src: int,
    gw_timestamp: str,
    travel_time: int,
    backend_timestamp: str,
    payload: str,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO udp_packets
                (src, gw_timestamp, travel_time, backend_timestamp, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (src, gw_timestamp, travel_time, backend_timestamp, payload),
        )


def get_packets() -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT
                id,
                src,
                gw_timestamp,
                travel_time,
                backend_timestamp,
                payload
            FROM udp_packets
            ORDER BY id DESC
            """
        ).fetchall()
