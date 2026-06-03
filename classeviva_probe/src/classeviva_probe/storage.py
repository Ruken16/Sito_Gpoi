from __future__ import annotations

import json
import mysql.connector
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator, Optional
import os


DEFAULT_PROFILE = {
    "study_goal": "Migliorare costanza e rendimento senza accumulare stress",
    "learning_mode": "standard",
    "daily_study_minutes": 120,
    "session_minutes": 40,
}


@dataclass
class Database:
    host: str
    user: str
    password: str
    database: str

    @contextmanager
    def connect(self) -> Iterator[mysql.connector.connection.MySQLConnection]:
        conn = mysql.connector.connect(
            host=self.host,
            user=self.user,
            password=self.password,
            database=self.database,
            charset='utf8mb4',
            collation='utf8mb4_unicode_ci',
            autocommit=True
        )
        try:
            yield conn
        finally:
            conn.close()


def get_db_config() -> dict[str, str]:
    return {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "cv_tutor"),
    }


def init_db(db: Database) -> None:
    # Lo schema è fornito separatamente in schema.sql, 
    # ma possiamo assicurarci che le tabelle esistano qui se necessario.
    pass


# --- Gestione Utenti ---

def create_user(db: Database, email: str, full_name: str, school_level: str) -> dict[str, Any]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO users (email, full_name, school_level) VALUES (%s, %s, %s)",
            (email, full_name, school_level)
        )
        user_id = cursor.lastrowid
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        # Inizializza anche il profilo
        ensure_profile(db, user_id=user_id, display_name=full_name)
        
        return user


def get_user_by_email(db: Database, email: str) -> Optional[dict[str, Any]]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cursor.fetchone()


def update_user_cv_credentials(db: Database, user_id: int, cv_username: str, cv_password: str) -> None:
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET cv_username = %s, cv_password = %s WHERE id = %s",
            (cv_username, cv_password, user_id)
        )


# --- Gestione Profili ---

def ensure_profile(db: Database, *, user_id: int, display_name: str) -> dict[str, Any]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row is None:
            cursor.execute(
                """
                INSERT INTO profiles (
                    user_id, display_name, study_goal, learning_mode,
                    daily_study_minutes, session_minutes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    display_name,
                    DEFAULT_PROFILE["study_goal"],
                    DEFAULT_PROFILE["learning_mode"],
                    DEFAULT_PROFILE["daily_study_minutes"],
                    DEFAULT_PROFILE["session_minutes"],
                ),
            )
            cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
        elif row["display_name"] != display_name and display_name:
            cursor.execute(
                "UPDATE profiles SET display_name = %s WHERE user_id = %s",
                (display_name, user_id),
            )
            cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
        return row


def update_profile(
    db: Database,
    *,
    user_id: int,
    display_name: str | None = None,
    study_goal: str | None = None,
    learning_mode: str | None = None,
    daily_study_minutes: int | None = None,
    session_minutes: int | None = None,
) -> dict[str, Any]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Profilo per utente {user_id} non trovato")
        
        current = row
        updated = {
            "display_name": display_name or current["display_name"],
            "study_goal": study_goal or current["study_goal"],
            "learning_mode": learning_mode or current["learning_mode"],
            "daily_study_minutes": int(daily_study_minutes or current["daily_study_minutes"]),
            "session_minutes": int(session_minutes or current["session_minutes"]),
        }
        cursor.execute(
            """
            UPDATE profiles
            SET display_name = %s, study_goal = %s, learning_mode = %s,
                daily_study_minutes = %s, session_minutes = %s
            WHERE user_id = %s
            """,
            (
                updated["display_name"],
                updated["study_goal"],
                updated["learning_mode"],
                updated["daily_study_minutes"],
                updated["session_minutes"],
                user_id,
            ),
        )
        cursor.execute("SELECT * FROM profiles WHERE user_id = %s", (user_id,))
        return cursor.fetchone()


# --- Gestione Task ---

def list_tasks(db: Database, *, user_id: int) -> list[dict[str, Any]]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = %s
            ORDER BY
                CASE status WHEN 'doing' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END,
                due_date ASC,
                priority DESC,
                id DESC
            """,
            (user_id,),
        )
        return cursor.fetchall()


def create_task(
    db: Database,
    *,
    user_id: int,
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
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO tasks (
                user_id, title, subject, due_date, category,
                estimated_minutes, difficulty, priority, status,
                notes, source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
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
            ),
        )
        task_id = cursor.lastrowid
        cursor.execute("SELECT * FROM tasks WHERE id = %s", (task_id,))
        return cursor.fetchone()


def update_task(db: Database, *, user_id: int, task_id: int, fields: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "title", "subject", "due_date", "category",
        "estimated_minutes", "difficulty", "priority", "status", "notes",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        raise ValueError("Nessun campo aggiornabile specificato")

    assignments = ", ".join(f"{key} = %s" for key in updates)
    values = list(updates.values()) + [user_id, task_id]

    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            f"UPDATE tasks SET {assignments} WHERE user_id = %s AND id = %s",
            values,
        )
        cursor.execute("SELECT * FROM tasks WHERE user_id = %s AND id = %s", (user_id, task_id))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Task {task_id} non trovata")
        return row


def delete_task(db: Database, *, user_id: int, task_id: int) -> None:
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE user_id = %s AND id = %s", (user_id, task_id))


# --- Gestione Chat ---

def create_chat_thread(db: Database, *, user_id: int, title: str = "Nuova chat") -> dict[str, Any]:
    clean_title = title.strip()[:80] or "Nuova chat"
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "INSERT INTO chat_threads (user_id, title) VALUES (%s, %s)",
            (user_id, clean_title),
        )
        thread_id = cursor.lastrowid
        cursor.execute("SELECT * FROM chat_threads WHERE id = %s", (thread_id,))
        return cursor.fetchone()


def list_chat_threads(db: Database, *, user_id: int) -> list[dict[str, Any]]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
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
            WHERE t.user_id = %s
            ORDER BY t.updated_at DESC, t.id DESC
            """,
            (user_id,),
        )
        return cursor.fetchall()


def ensure_chat_thread(db: Database, *, user_id: int, thread_id: int | None = None) -> dict[str, Any]:
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        row = None
        if thread_id is not None:
            cursor.execute(
                "SELECT * FROM chat_threads WHERE user_id = %s AND id = %s",
                (user_id, int(thread_id)),
            )
            row = cursor.fetchone()
        
        if row is None:
            cursor.execute(
                "SELECT * FROM chat_threads WHERE user_id = %s ORDER BY updated_at DESC, id DESC LIMIT 1",
                (user_id,),
            )
            row = cursor.fetchone()
            
        if row is None:
            cursor.execute(
                "INSERT INTO chat_threads (user_id, title) VALUES (%s, %s)",
                (user_id, "Chat principale"),
            )
            thread_id = cursor.lastrowid
            cursor.execute("SELECT * FROM chat_threads WHERE id = %s", (thread_id,))
            row = cursor.fetchone()
            
        return row


def _row_to_chat_message(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    if "context_json" in item:
        try:
            item["context"] = json.loads(item.pop("context_json", "{}") or "{}")
        except (json.JSONDecodeError, TypeError):
            item["context"] = {}
    return item


def list_chat_messages(db: Database, *, user_id: int, thread_id: int | None = None, limit: int = 40) -> list[dict[str, Any]]:
    thread = ensure_chat_thread(db, user_id=user_id, thread_id=thread_id)
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM chat_messages
            WHERE user_id = %s AND thread_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, thread["id"], limit),
        )
        rows = cursor.fetchall()

    return [_row_to_chat_message(row) for row in reversed(rows)]


def append_chat_message(
    db: Database,
    *,
    user_id: int,
    thread_id: int | None = None,
    role: str,
    content: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thread = ensure_chat_thread(db, user_id=user_id, thread_id=thread_id)
    with db.connect() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            INSERT INTO chat_messages (thread_id, user_id, role, content, context_json)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                thread["id"],
                user_id,
                role,
                content,
                json.dumps(context or {}, ensure_ascii=False),
            ),
        )
        message_id = cursor.lastrowid
        
        title = content.strip().replace("\n", " ")[:48] if role == "user" else thread["title"]
        if role == "user" and thread["title"] in {"Nuova chat", "Chat principale"} and title:
            cursor.execute(
                "UPDATE chat_threads SET title = %s WHERE id = %s AND user_id = %s",
                (title, thread["id"], user_id),
            )
        else:
            cursor.execute(
                "UPDATE chat_threads SET updated_at = CURRENT_TIMESTAMP WHERE id = %s AND user_id = %s",
                (thread["id"], user_id),
            )
            
        cursor.execute("SELECT * FROM chat_messages WHERE id = %s", (message_id,))
        return _row_to_chat_message(cursor.fetchone())
