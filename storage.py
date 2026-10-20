"""
storage.py — SQLite persistence for NextUp using parameterized queries.
"""

import json
import os
import sqlite3
import tempfile

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL,
    subject         TEXT    NOT NULL DEFAULT '',
    deadline        TEXT    NOT NULL,
    deadline_time   TEXT,
    difficulty      INTEGER NOT NULL,
    estimated_hours REAL    NOT NULL DEFAULT 1.0,
    task_type       TEXT    NOT NULL DEFAULT 'other',
    completed       INTEGER NOT NULL DEFAULT 0,
    completed_at    TEXT
);
"""


class TaskStore:
    """SQLite task repository with parameterized queries (SQL injection safe)."""

    def __init__(self, db_path=None):
        if db_path is None:
            app_dir = os.path.dirname(os.path.abspath(__file__))
            if os.environ.get("VERCEL") or not os.access(app_dir, os.W_OK):
                db_path = os.path.join(tempfile.gettempdir(), "nextup.db")
            else:
                db_path = os.path.join(app_dir, "nextup.db")
        self.db_path = db_path
        # check_same_thread=False allows Flask worker threads to share the connection.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._fresh = self._is_fresh_database()
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        if self._fresh:
            print(f"[NextUp] new database created at {os.path.basename(db_path)}")

    def _is_fresh_database(self):
        """True only if the tasks table does not exist yet. O(1)."""
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'tasks'")
        return cur.fetchone()[0] == 0

    def next_id(self) -> int:
        """Return 1 + max stored id (or 1 if empty). O(log n)."""
        cur = self._conn.execute("SELECT MAX(id) FROM tasks")
        top = cur.fetchone()[0]
        return (top or 0) + 1

    def load_tasks(self):
        """Load all task rows as dicts for Task.from_dict(). O(n)."""
        cur = self._conn.execute(
            "SELECT id, name, subject, deadline, deadline_time, difficulty, "
            "       estimated_hours, task_type, completed, completed_at "
            "FROM tasks ORDER BY id")
        return [{"id": r[0], "name": r[1], "subject": r[2],
                 "deadline": r[3], "deadline_time": r[4],
                 "difficulty": r[5], "estimated_hours": r[6],
                 "task_type": r[7], "completed": bool(r[8]),
                 "completed_at": r[9]} for r in cur.fetchall()]

    def upsert(self, task):
        """Insert or update one task row (parameterized). O(1)."""
        self._conn.execute(
            "INSERT INTO tasks (id, name, subject, deadline, deadline_time, "
            "                   difficulty, estimated_hours, task_type, "
            "                   completed, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET "
            "  name=excluded.name, subject=excluded.subject, "
            "  deadline=excluded.deadline, deadline_time=excluded.deadline_time, "
            "  difficulty=excluded.difficulty, "
            "  estimated_hours=excluded.estimated_hours, "
            "  task_type=excluded.task_type, completed=excluded.completed, "
            "  completed_at=excluded.completed_at",
            (task.id, task.name, task.subject, task.deadline_str(),
             task.deadline_time, task.difficulty, task.estimated_hours,
             task.task_type, 1 if task.completed else 0, task.completed_at))
        self._conn.commit()

    def delete(self, task_id):
        """Delete one task row by primary key (parameterized). O(1)."""
        self._conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._conn.commit()

    def close(self):
        """Close the SQLite connection."""
        self._conn.close()

    def migrate_from_json(self, json_path):
        """One-time import of legacy tasks.json on fresh SQLite startup. O(n)."""
        if not os.path.exists(json_path):
            return 0
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[NextUp] could not read tasks.json for migration: {exc}")
            return 0
        imported = 0
        for entry in data.get("tasks", []):
            cur = self._conn.execute(
                "SELECT 1 FROM tasks WHERE id = ?", (entry["id"],))
            if cur.fetchone() is not None:
                continue
            self._conn.execute(
                "INSERT INTO tasks (id, name, subject, deadline, "
                "                   deadline_time, difficulty, "
                "                   estimated_hours, task_type, "
                "                   completed, completed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (entry["id"], entry["name"], entry.get("subject", ""),
                 entry["deadline"], entry.get("deadline_time"),
                 entry["difficulty"], entry.get("estimated_hours", 1.0),
                 entry.get("task_type", "other"),
                 1 if entry.get("completed") else 0,
                 entry.get("completed_at")))
            imported += 1
        self._conn.commit()
        if imported:
            print(f"[NextUp] migrated {imported} task(s) from tasks.json "
                  "(the file is kept as a backup)")
        return imported


USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT    NOT NULL UNIQUE,
    name        TEXT    NOT NULL,
    program     TEXT    NOT NULL DEFAULT '',
    year_level  TEXT    NOT NULL DEFAULT '',
    pw_hash     TEXT    NOT NULL
);
"""


class UserStore:
    """SQLite persistence for student accounts (parameterized queries)."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(USER_SCHEMA)
        self._conn.commit()

    def create_user(self, name, program, year_level, pw_hash):
        """Insert a new student account; raises ValueError if username exists."""
        clean_name = name.strip()
        username = clean_name.lower()
        existing = self._conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing is not None:
            raise ValueError("An account with that name already exists.")
        cur = self._conn.execute(
            "INSERT INTO users (username, name, program, year_level, pw_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, clean_name, program.strip(), year_level.strip(), pw_hash),
        )
        self._conn.commit()
        return self.get_by_id(cur.lastrowid)

    def authenticate(self, name):
        """Return (user_dict, pw_hash) for case-insensitive name, or (None, None)."""
        username = name.strip().lower()
        row = self._conn.execute(
            "SELECT id, name, program, year_level, pw_hash FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None:
            return None, None
        return {
            "id": row[0],
            "name": row[1],
            "program": row[2],
            "yearLevel": row[3],
        }, row[4]

    def get_by_id(self, user_id):
        """Return user dict by id, or None."""
        row = self._conn.execute(
            "SELECT id, name, program, year_level FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": row[0],
            "name": row[1],
            "program": row[2],
            "yearLevel": row[3],
        }

    def close(self):
        self._conn.close()
