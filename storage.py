"""
Module 1: Data Storage Module
------------------------------
Handles all persistence for the Personal Deadline Negotiator Agent.
Uses SQLite (file-based, zero setup) with 4 tables:

    - deadlines    : tasks/assignments with due dates, estimated effort, priority, category
    - availability : how many free hours the user has on a given day
    - memory       : long-term learned facts about the user (pace, patterns)
    - history      : log of past agent recommendations and outcomes

This module exposes simple CRUD functions. Tools (Deadline Tool,
Availability Tool, Reprioritization Tool) and the Agent Orchestration
layer should ONLY talk to the database through these functions —
never write raw SQL elsewhere.
"""

import sqlite3
from datetime import date
from contextlib import contextmanager

DB_PATH = "deadline_agent.db"


# ---------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------
@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Schema setup
# ---------------------------------------------------------------------
def init_db():
    """Creates all tables if they don't already exist. Safe to call every run."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS deadlines (
                deadline_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                task_name         TEXT NOT NULL,
                due_date          TEXT NOT NULL,
                estimated_hours   REAL NOT NULL,
                priority          TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high')),
                status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'missed')),
                created_on        TEXT NOT NULL,
                category          TEXT NOT NULL DEFAULT 'other'
            );

            CREATE TABLE IF NOT EXISTS availability (
                availability_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                date              TEXT NOT NULL UNIQUE,
                available_hours   REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory (
                memory_id         INTEGER PRIMARY KEY AUTOINCREMENT,
                key               TEXT NOT NULL UNIQUE,
                value             TEXT NOT NULL,
                updated_on        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS history (
                history_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                deadline_id       INTEGER,
                recommendation    TEXT NOT NULL,
                outcome           TEXT DEFAULT 'unknown' CHECK (outcome IN ('met', 'missed', 'unknown')),
                recorded_on       TEXT NOT NULL,
                FOREIGN KEY (deadline_id) REFERENCES deadlines(deadline_id)
            );
            """
        )

        # Databases created before the category column existed get it added here
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(deadlines)")]
        if "category" not in columns:
            conn.execute("ALTER TABLE deadlines ADD COLUMN category TEXT NOT NULL DEFAULT 'other'")


# ---------------------------------------------------------------------
# Reset (useful before demos / repeated testing)
# ---------------------------------------------------------------------
def reset_db():
    """Wipes all data from all tables. Use this before a clean demo run."""
    with get_connection() as conn:
        conn.executescript(
            """
            DELETE FROM history;  -- first: its rows reference deadlines
            DELETE FROM deadlines;
            DELETE FROM availability;
            DELETE FROM memory;
            DELETE FROM sqlite_sequence;  -- restart AUTOINCREMENT ids from 1
            """
        )
    print("Database reset: all tables cleared.")


# ---------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------
def add_deadline(task_name: str, due_date: str, estimated_hours: float, priority: str,
                 category: str = "other"):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO deadlines (task_name, due_date, estimated_hours, priority, created_on, category)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task_name, due_date, estimated_hours, priority, date.today().isoformat(), category),
        )


def get_deadlines(status: str = None):
    """Fetch all deadlines, optionally filtered by status (pending/done/missed)."""
    with get_connection() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM deadlines WHERE status = ? ORDER BY due_date", (status,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deadlines ORDER BY due_date"
            ).fetchall()
        return [dict(r) for r in rows]


def update_deadline_status(deadline_id: int, status: str):
    with get_connection() as conn:
        conn.execute(
            "UPDATE deadlines SET status = ? WHERE deadline_id = ?",
            (status, deadline_id),
        )


# ---------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------
def set_availability(day: str, available_hours: float):
    """Insert or update available hours for a given date."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO availability (date, available_hours) VALUES (?, ?)
               ON CONFLICT(date) DO UPDATE SET available_hours = excluded.available_hours""",
            (day, available_hours),
        )


def get_availability(start_date: str = None, end_date: str = None):
    """Fetch availability rows, optionally within a date range (inclusive)."""
    with get_connection() as conn:
        if start_date and end_date:
            rows = conn.execute(
                "SELECT * FROM availability WHERE date BETWEEN ? AND ? ORDER BY date",
                (start_date, end_date),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM availability ORDER BY date"
            ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Memory (long-term learned facts about the user)
# ---------------------------------------------------------------------
def set_memory(key: str, value: str):
    """Store or update a learned fact, e.g. key='pace_multiplier', value='1.5'."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO memory (key, value, updated_on) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_on = excluded.updated_on""",
            (key, value, date.today().isoformat()),
        )


def get_memory(key: str = None):
    """Fetch one memory value by key, or all memory as a dict if key is None."""
    with get_connection() as conn:
        if key:
            row = conn.execute("SELECT value FROM memory WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
        else:
            rows = conn.execute("SELECT key, value FROM memory").fetchall()
            return {r["key"]: r["value"] for r in rows}


# ---------------------------------------------------------------------
# History (past agent recommendations + outcomes)
# ---------------------------------------------------------------------
def add_history_record(recommendation: str, deadline_id: int = None, outcome: str = "unknown"):
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO history (deadline_id, recommendation, outcome, recorded_on)
               VALUES (?, ?, ?, ?)""",
            (deadline_id, recommendation, outcome, date.today().isoformat()),
        )


def get_history():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM history ORDER BY recorded_on").fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------
# Quick self-test when run directly
# ---------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    print("Database initialized:", DB_PATH)
    reset_db()  # clean slate every time this file is run directly

    # sanity check with dummy data
    add_deadline("DBMS Assignment", "2026-09-08", estimated_hours=5, priority="high")
    add_deadline("Presentation Prep", "2026-09-07", estimated_hours=3, priority="medium")
    set_availability("2026-09-05", 2)
    set_availability("2026-09-06", 4)
    set_memory("pace_multiplier", "1.5")  # user usually takes 1.5x their estimate

    print("Deadlines:", get_deadlines())
    print("Availability:", get_availability())
    print("Memory:", get_memory())