"""Simple SQLite database for MVP storage."""

import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from .config import BASE_DIR

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "medrecord.db"


def get_connection():
    """Get a database connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize database tables."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            audio_filename TEXT,
            audio_size_bytes INTEGER DEFAULT 0,
            transcription TEXT,
            structured_text TEXT,
            specialty TEXT DEFAULT 'general',
            patient_info TEXT DEFAULT '',
            status TEXT DEFAULT 'processing',
            processing_time_sec REAL DEFAULT 0,
            metadata TEXT DEFAULT '{}'
        );
        
        CREATE INDEX IF NOT EXISTS idx_records_created 
            ON records(created_at DESC);
        
        CREATE INDEX IF NOT EXISTS idx_records_status 
            ON records(status);
    """)
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {DB_PATH}")


def create_record(audio_filename: str, audio_size: int, specialty: str = "general", patient_info: str = "") -> int:
    """Create a new record entry. Returns the record ID."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO records (audio_filename, audio_size_bytes, specialty, patient_info, status)
           VALUES (?, ?, ?, ?, 'processing')""",
        (audio_filename, audio_size, specialty, patient_info),
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def update_record(record_id: int, **kwargs):
    """Update a record with provided fields."""
    conn = get_connection()
    set_clauses = []
    values = []
    for key, value in kwargs.items():
        set_clauses.append(f"{key} = ?")
        values.append(value)
    
    values.append(record_id)
    query = f"UPDATE records SET {', '.join(set_clauses)} WHERE id = ?"
    conn.execute(query, values)
    conn.commit()
    conn.close()


def get_record(record_id: int) -> dict | None:
    """Get a single record by ID."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM records WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def get_recent_records(limit: int = 20) -> list[dict]:
    """Get recent records."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, created_at, audio_filename, specialty, patient_info, status, processing_time_sec "
        "FROM records ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
