#!/usr/bin/env python3
"""Smoke-check that the local development environment can boot the bot stack."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    print("==> Loading config / dependencies")
    from config import TOKEN, MODEL, BASE_URL, DB_URL, SERPER_API_KEY  # noqa: F401
    from database import DatabasePool, init_db
    from telegram.ext import Application

    print(f"    MODEL={MODEL}")
    print(f"    BASE_URL={BASE_URL}")
    print(f"    DATABASE_URL host configured: {'@' in DB_URL}")
    print(f"    BOT_TOKEN present: {bool(TOKEN)}")
    print(f"    SERPER_API_KEY present: {bool(SERPER_API_KEY)}")

    print("==> Initializing database pool + schema")
    DatabasePool.init_pool()
    init_db()

    pool = DatabasePool.get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
            tables = [row[0] for row in cur.fetchall()]
            cur.execute(
                "INSERT INTO messages (chat_id, user_name, user_id, text, timestamp, chat_title) "
                "VALUES (%s, %s, %s, %s, NOW(), %s) RETURNING id",
                (1, "env-check", 1, "hello from verify_env", "Dev"),
            )
            inserted_id = cur.fetchone()[0]
            conn.commit()
            cur.execute("DELETE FROM messages WHERE id = %s", (inserted_id,))
            conn.commit()
    finally:
        pool.putconn(conn)

    print(f"    tables={tables}")
    print("    insert/delete round-trip: ok")

    print("==> Building Telegram Application object")
    app = Application.builder().token(TOKEN).build()
    print(f"    application built: {app is not None}")

    print("==> Environment verification PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - surface any boot failure clearly
        print(f"==> Environment verification FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
