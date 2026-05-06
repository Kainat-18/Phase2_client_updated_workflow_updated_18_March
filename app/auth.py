from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sqlite3
from pathlib import Path
from typing import Any

from app.utils import ensure_dir


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db(db_path: str) -> None:
    db_file = Path(db_path)
    ensure_dir(str(db_file.parent))
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), actual_salt, 260000)
    salt_b64 = base64.b64encode(actual_salt).decode("utf-8")
    digest_b64 = base64.b64encode(digest).decode("utf-8")
    return f"{salt_b64}${digest_b64}"


def _verify_password(password: str, encoded_hash: str) -> bool:
    try:
        salt_b64, digest_b64 = encoded_hash.split("$", 1)
    except ValueError:
        return False
    salt = base64.b64decode(salt_b64.encode("utf-8"))
    expected = base64.b64decode(digest_b64.encode("utf-8"))
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260000)
    return hmac.compare_digest(actual, expected)


def ensure_default_admin(db_path: str, username: str, password: str) -> None:
    username = username.strip()
    if not username:
        return
    with _connect(db_path) as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return
        conn.execute(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (username, _hash_password(password)),
        )
        conn.commit()


def create_user(db_path: str, username: str, password: str, is_admin: bool = False) -> tuple[bool, str]:
    clean_username = username.strip()
    if len(clean_username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 8:
        return False, "Password must be at least 8 characters."
    try:
        with _connect(db_path) as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
                (clean_username, _hash_password(password), int(is_admin)),
            )
            conn.commit()
            return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."


def authenticate_user(db_path: str, username: str, password: str) -> dict[str, Any] | None:
    clean_username = username.strip()
    if not clean_username or not password:
        return None
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin FROM users WHERE username = ?",
            (clean_username,),
        ).fetchone()
    if not row:
        return None
    if not _verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "is_admin": bool(row["is_admin"])}


def get_user_by_id(db_path: str, user_id: int) -> dict[str, Any] | None:
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id, username, is_admin, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
    }


def list_users(db_path: str) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, username, is_admin, created_at FROM users ORDER BY created_at DESC, id DESC"
        ).fetchall()
    users: list[dict[str, Any]] = []
    for row in rows:
        users.append(
            {
                "id": row["id"],
                "username": row["username"],
                "is_admin": bool(row["is_admin"]),
                "created_at": row["created_at"],
            }
        )
    return users


def delete_user(db_path: str, target_user_id: int, actor_user_id: int) -> tuple[bool, str]:
    if target_user_id == actor_user_id:
        return False, "You cannot delete your own account."

    with _connect(db_path) as conn:
        target = conn.execute(
            "SELECT id, is_admin FROM users WHERE id = ?",
            (target_user_id,),
        ).fetchone()
        if not target:
            return False, "User not found."

        if bool(target["is_admin"]):
            admin_count_row = conn.execute("SELECT COUNT(*) AS count FROM users WHERE is_admin = 1").fetchone()
            admin_count = int(admin_count_row["count"]) if admin_count_row else 0
            if admin_count <= 1:
                return False, "Cannot delete the last admin account."

        conn.execute("DELETE FROM users WHERE id = ?", (target_user_id,))
        conn.commit()

    return True, "User deleted successfully."
