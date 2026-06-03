from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


DEFAULT_PROFILE = {
    "study_goal": "Migliorare costanza e rendimento senza accumulare stress",
    "learning_mode": "standard",
    "daily_study_minutes": 120,
    "session_minutes": 40,
}


@dataclass
class Database:
    path: Path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def database_path(project_root: Path) -> Path:
    return project_root / ".cvprobe.sqlite3"


def init_db(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_key TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                study_goal TEXT NOT NULL,
                learning_mode TEXT NOT NULL,
                daily_study_minutes INTEGER NOT NULL,
                session_minutes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                due_date TEXT NOT NULL,
                category TEXT NOT NULL,
                estimated_minutes INTEGER NOT NULL,
                difficulty INTEGER NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id INTEGER,
                user_key TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_key TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(chat_messages)").fetchall()}
        if "thread_id" not in columns:
            conn.execute("ALTER TABLE chat_messages ADD COLUMN thread_id INTEGER")


def ensure_profile(db: Database, *, user_key: str, display_name: str) -> dict[str, Any]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE user_key = ?", (user_key,)).fetchone()
        if row is None:
            conn.execute(
                """
                INSERT INTO profiles (
                    user_key, display_name, study_goal, learning_mode,
                    daily_study_minutes, session_minutes, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_key,
                    display_name,
                    DEFAULT_PROFILE["study_goal"],
                    DEFAULT_PROFILE["learning_mode"],
                    DEFAULT_PROFILE["daily_study_minutes"],
                    DEFAULT_PROFILE["session_minutes"],
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM profiles WHERE user_key = ?", (user_key,)).fetchone()
        elif row["display_name"] != display_name and display_name:
            conn.execute(
                "UPDATE profiles SET display_name = ?, updated_at = ? WHERE user_key = ?",
                (display_name, now, user_key),
            )
            row = conn.execute("SELECT * FROM profiles WHERE user_key = ?", (user_key,)).fetchone()
        return dict(row)


def update_profile(
    db: Database,
    *,
    user_key: str,
    display_name: str | None = None,
    study_goal: str | None = None,
    learning_mode: str | None = None,
    daily_study_minutes: int | None = None,
    session_minutes: int | None = None,
) -> dict[str, Any]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE user_key = ?", (user_key,)).fetchone()
        if row is None:
            raise KeyError(f"Profilo {user_key} non trovato")
        current = dict(row)
        updated = {
            "display_name": display_name or current["display_name"],
            "study_goal": study_goal or current["study_goal"],
            "learning_mode": learning_mode or current["learning_mode"],
            "daily_study_minutes": int(daily_study_minutes or current["daily_study_minutes"]),
            "session_minutes": int(session_minutes or current["session_minutes"]),
        }
        conn.execute(
            """
            UPDATE profiles
            SET display_name = ?, study_goal = ?, learning_mode = ?,
                daily_study_minutes = ?, session_minutes = ?, updated_at = ?
            WHERE user_key = ?
            """,
            (
                updated["display_name"],
                updated["study_goal"],
                updated["learning_mode"],
                updated["daily_study_minutes"],
                updated["session_minutes"],
                now,
                user_key,
            ),
        )
        row = conn.execute("SELECT * FROM profiles WHERE user_key = ?", (user_key,)).fetchone()
        return dict(row)


def list_tasks(db: Database, *, user_key: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM tasks
            WHERE user_key = ?
            ORDER BY
                CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END,
                due_date ASC,
                priority DESC,
                id DESC
            """,
            (user_key,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_task(
    db: Database,
    *,
    user_key: str,
    title: str,
    subject: str,
    due_date: str,
    category: str,
    estimated_minutes: int,
    difficulty: int,
    priority: int,
    notes: str = "",
    source: str = "manual",
    status: str = "todo",
) -> dict[str, Any]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                user_key, title, subject, due_date, category,
                estimated_minutes, difficulty, priority, status,
                notes, source, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_key,
                title,
                subject,
                due_date,
                category,
                estimated_minutes,
                difficulty,
                priority,
                status,
                notes,
                source,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


def update_task(db: Database, *, user_key: str, task_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "title",
        "subject",
        "due_date",
        "category",
        "estimated_minutes",
        "difficulty",
        "priority",
        "status",
        "notes",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        raise ValueError("Nessun campo aggiornabile specificato")

    now = datetime.utcnow().isoformat(timespec="seconds")
    updates["updated_at"] = now
    assignments = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [user_key, task_id]

    with db.connect() as conn:
        conn.execute(
            f"UPDATE tasks SET {assignments} WHERE user_key = ? AND id = ?",
            values,
        )
        row = conn.execute("SELECT * FROM tasks WHERE user_key = ? AND id = ?", (user_key, task_id)).fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} non trovata")
        return dict(row)


def delete_task(db: Database, *, user_key: str, task_id: int) -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM tasks WHERE user_key = ? AND id = ?", (user_key, task_id))


def create_chat_thread(db: Database, *, user_key: str, title: str = "Nuova chat") -> dict[str, Any]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    clean_title = title.strip()[:80] or "Nuova chat"
    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO chat_threads (user_key, title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (user_key, clean_title, now, now),
        )
        row = conn.execute("SELECT * FROM chat_threads WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return dict(row)


def list_chat_threads(db: Database, *, user_key: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT
                t.*,
                (
                    SELECT content
                    FROM chat_messages m
                    WHERE m.thread_id = t.id
                    ORDER BY m.id DESC
                    LIMIT 1
                ) AS preview,
                (
                    SELECT COUNT(*)
                    FROM chat_messages m
                    WHERE m.thread_id = t.id
                ) AS message_count
            FROM chat_threads t
            WHERE t.user_key = ?
            ORDER BY t.updated_at DESC, t.id DESC
            """,
            (user_key,),
        ).fetchall()
    return [dict(row) for row in rows]


def ensure_chat_thread(db: Database, *, user_key: str, thread_id: int | None = None) -> dict[str, Any]:
    with db.connect() as conn:
        row = None
        if thread_id is not None:
            row = conn.execute(
                "SELECT * FROM chat_threads WHERE user_key = ? AND id = ?",
                (user_key, int(thread_id)),
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT * FROM chat_threads WHERE user_key = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_key,),
            ).fetchone()
        if row is None:
            now = datetime.utcnow().isoformat(timespec="seconds")
            cursor = conn.execute(
                """
                INSERT INTO chat_threads (user_key, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_key, "Chat principale", now, now),
            )
            row = conn.execute("SELECT * FROM chat_threads WHERE id = ?", (cursor.lastrowid,)).fetchone()
        conn.execute(
            "UPDATE chat_messages SET thread_id = ? WHERE user_key = ? AND thread_id IS NULL",
            (row["id"], user_key),
        )
    return dict(row)


def _row_to_chat_message(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["context"] = json.loads(item.pop("context_json", "{}") or "{}")
    except json.JSONDecodeError:
        item["context"] = {}
    return item


def list_chat_messages(db: Database, *, user_key: str, thread_id: int | None = None, limit: int = 40) -> list[dict[str, Any]]:
    thread = ensure_chat_thread(db, user_key=user_key, thread_id=thread_id)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM chat_messages
            WHERE user_key = ? AND thread_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_key, thread["id"], limit),
        ).fetchall()

    return [_row_to_chat_message(row) for row in reversed(rows)]


def append_chat_message(
    db: Database,
    *,
    user_key: str,
    thread_id: int | None = None,
    role: str,
    content: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    thread = ensure_chat_thread(db, user_key=user_key, thread_id=thread_id)
    with db.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO chat_messages (thread_id, user_key, role, content, context_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                thread["id"],
                user_key,
                role,
                content,
                json.dumps(context or {}, ensure_ascii=False),
                now,
            ),
        )
        title = content.strip().replace("\n", " ")[:48] if role == "user" else thread["title"]
        if role == "user" and thread["title"] in {"Nuova chat", "Chat principale"} and title:
            conn.execute(
                "UPDATE chat_threads SET title = ?, updated_at = ? WHERE id = ? AND user_key = ?",
                (title, now, thread["id"], user_key),
            )
        else:
            conn.execute(
                "UPDATE chat_threads SET updated_at = ? WHERE id = ? AND user_key = ?",
                (now, thread["id"], user_key),
            )
        row = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (cursor.lastrowid,)).fetchone()

    return _row_to_chat_message(row)


def seed_demo_tasks(db: Database, *, user_key: str) -> None:
    if list_tasks(db, user_key=user_key):
        return

    demo = [
        {
            "title": "Ripasso capitolo di matematica",
            "subject": "Matematica",
            "due_date": datetime.utcnow().date().isoformat(),
            "category": "ripasso",
            "estimated_minutes": 90,
            "difficulty": 4,
            "priority": 5,
            "notes": "Concentrarsi su equazioni e problemi.",
        },
        {
            "title": "Preparare verifica di storia",
            "subject": "Storia",
            "due_date": datetime.utcnow().date().isoformat(),
            "category": "verifica",
            "estimated_minutes": 120,
            "difficulty": 3,
            "priority": 4,
            "notes": "Rivedere timeline e date principali.",
        },
        {
            "title": "Compito di inglese",
            "subject": "Inglese",
            "due_date": datetime.utcnow().date().isoformat(),
            "category": "compito",
            "estimated_minutes": 45,
            "difficulty": 2,
            "priority": 3,
            "notes": "Scrivere draft e controllare la grammatica.",
        },
    ]
    for task in demo:
        create_task(db, user_key=user_key, source="demo", **task)
