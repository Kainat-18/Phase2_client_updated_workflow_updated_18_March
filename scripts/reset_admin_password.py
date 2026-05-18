#!/usr/bin/env python3
"""Reset admin password from .env (ADMIN_USERNAME / ADMIN_PASSWORD)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.auth import _hash_password, _connect, ensure_default_admin, init_auth_db
from app.config import settings


def main() -> None:
    username = settings.admin_username.strip()
    password = settings.admin_password
    if not username:
        print("ERROR: ADMIN_USERNAME is empty")
        sys.exit(1)
    if len(password) < 8:
        print("ERROR: ADMIN_PASSWORD must be at least 8 characters")
        sys.exit(1)

    init_auth_db(settings.auth_db_path)
    with _connect(settings.auth_db_path) as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (_hash_password(password), row["id"]),
            )
            conn.commit()
            print(f"Password reset for: {username}")
        else:
            ensure_default_admin(settings.auth_db_path, username, password)
            print(f"Created admin user: {username}")

    print(f"Login with username={username!r} and the password from ADMIN_PASSWORD in .env")


if __name__ == "__main__":
    main()
