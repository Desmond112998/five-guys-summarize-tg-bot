import uuid
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import pool

from config import DB_URL, HK_TIMEZONE, MAX_THREAD_TURNS, THREAD_IDLE_MINUTES, logger


class DatabasePool:
    _db_pool = None

    @staticmethod
    def init_pool():
        if DatabasePool._db_pool is not None:
            logger.info("Database pool already initialized")
            return
        try:
            DatabasePool._db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, dsn=DB_URL)
            if DatabasePool._db_pool:
                logger.info("Database pool initialized successfully")
            else:
                raise ValueError("Database pool initialization returned None")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise RuntimeError(f"Database pool initialization failed: {e}")

    @staticmethod
    def get_pool():
        if DatabasePool._db_pool is None:
            raise RuntimeError("Database pool not initialized. Call init_pool() first.")
        return DatabasePool._db_pool


def init_db():
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                user_name TEXT,
                user_id BIGINT,
                text TEXT,
                timestamp TIMESTAMP,
                chat_title TEXT
            )
        """)

        cursor.execute("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS telegram_message_id BIGINT,
            ADD COLUMN IF NOT EXISTS reply_to_message_id BIGINT,
            ADD COLUMN IF NOT EXISTS role TEXT,
            ADD COLUMN IF NOT EXISTS thread_id TEXT
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_telegram_message_id
            ON messages (chat_id, telegram_message_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_thread_timestamp
            ON messages (chat_id, thread_id, timestamp)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_ai_usage (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT,
                usage_date DATE,
                usage_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, usage_date)
            )
        """)
        conn.commit()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database schema: {e}")
        raise
    finally:
        if conn:
            db_pool.putconn(conn)


def _utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def log_message(update, context):
    if update.message and update.message.text:
        chat_id = update.message.chat_id
        user = update.message.from_user
        message = update.message.text
        timestamp = update.message.date
        if timestamp and timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        user_id = user.id
        chat_title = (
            update.message.chat.title if update.message.chat.title else "Private Chat"
        )
        telegram_message_id = update.message.message_id
        reply_to_message_id = (
            update.message.reply_to_message.message_id
            if update.message.reply_to_message
            else None
        )

        user_name = user.first_name if user.first_name else "唔知邊條粉蛋"
        if user.last_name:
            user_name += " " + user.last_name

        logger.info(
            f"Received message in chat {chat_id} ({chat_title}) from {user_name} (ID: {user_id}): {message}"
        )

        db_pool = DatabasePool.get_pool()
        conn = None
        try:
            conn = db_pool.getconn()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (
                    chat_id, user_name, user_id, text, timestamp, chat_title,
                    telegram_message_id, reply_to_message_id, role, thread_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    chat_id,
                    user_name,
                    user_id,
                    message,
                    timestamp,
                    chat_title,
                    telegram_message_id,
                    reply_to_message_id,
                    "user",
                    None,
                ),
            )
            conn.commit()
            logger.info(f"Message saved to database for chat {chat_id} ({chat_title})")
        except Exception as e:
            logger.error(f"Failed to log message to database: {e}")
        finally:
            if conn:
                db_pool.putconn(conn)


def resolve_thread_id(
    chat_id: int, user_id: int, reply_to_message_id: int | None
) -> str | None:
    """
    Resolve conversation thread for this chat/user.
    Reply to a bot message continues that thread; else continue idle window or open new.
    Returns None on DB error.
    """
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()

        if reply_to_message_id is not None:
            cursor.execute(
                """
                SELECT thread_id FROM messages
                WHERE chat_id = %s
                  AND telegram_message_id = %s
                  AND thread_id IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (chat_id, reply_to_message_id),
            )
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]

        idle_start = _utc_now() - timedelta(minutes=THREAD_IDLE_MINUTES)
        cursor.execute(
            """
            SELECT thread_id FROM messages
            WHERE chat_id = %s
              AND user_id = %s
              AND role = 'user'
              AND thread_id IS NOT NULL
              AND timestamp >= %s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (chat_id, user_id, idle_start),
        )
        row = cursor.fetchone()
        if row and row[0]:
            return row[0]

        return str(uuid.uuid4())
    except Exception as e:
        logger.error(f"Failed to resolve thread_id: {e}")
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


def attach_thread_to_message(
    chat_id: int,
    telegram_message_id: int,
    thread_id: str,
    text: str | None = None,
) -> bool:
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        if text is not None:
            cursor.execute(
                """
                UPDATE messages
                SET thread_id = %s, text = %s
                WHERE chat_id = %s AND telegram_message_id = %s
                """,
                (thread_id, text, chat_id, telegram_message_id),
            )
        else:
            cursor.execute(
                """
                UPDATE messages
                SET thread_id = %s
                WHERE chat_id = %s AND telegram_message_id = %s
                """,
                (thread_id, chat_id, telegram_message_id),
            )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Failed to attach thread_id: {e}")
        return False
    finally:
        if conn:
            db_pool.putconn(conn)


def get_thread_messages(
    chat_id: int, thread_id: str, limit: int = MAX_THREAD_TURNS
) -> list[dict] | None:
    """
    Load recent thread turns as OpenAI-style {role, content} dicts.
    Returns None on DB error; empty list if no rows.
    """
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, text FROM (
                SELECT role, text, timestamp, id
                FROM messages
                WHERE chat_id = %s
                  AND thread_id = %s
                  AND role IN ('user', 'assistant')
                ORDER BY timestamp DESC, id DESC
                LIMIT %s
            ) recent
            ORDER BY timestamp ASC, id ASC
            """,
            (chat_id, thread_id, limit),
        )
        rows = cursor.fetchall()
        messages = []
        for role, text in rows:
            if role in ("user", "assistant") and text:
                messages.append({"role": role, "content": text})
        return messages
    except Exception as e:
        logger.error(f"Failed to load thread messages: {e}")
        return None
    finally:
        if conn:
            db_pool.putconn(conn)


def log_thread_user_message(
    chat_id: int,
    chat_title: str,
    user_id: int,
    user_name: str,
    text: str,
    telegram_message_id: int,
    reply_to_message_id: int | None,
    thread_id: str,
) -> bool:
    """Insert a user turn already bound to a thread (e.g. /ask)."""
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO messages (
                chat_id, user_name, user_id, text, timestamp, chat_title,
                telegram_message_id, reply_to_message_id, role, thread_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                chat_id,
                user_name,
                user_id,
                text,
                _utc_now(),
                chat_title,
                telegram_message_id,
                reply_to_message_id,
                "user",
                thread_id,
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to log thread user message: {e}")
        return False
    finally:
        if conn:
            db_pool.putconn(conn)


async def log_bot_reply(
    chat_id: int,
    chat_title: str,
    text: str,
    bot_id: int,
    bot_name: str,
    telegram_message_id: int | None = None,
    thread_id: str | None = None,
    reply_to_message_id: int | None = None,
):
    """Logs the bot's own replies."""
    timestamp = _utc_now()
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()

        sql = """
            INSERT INTO messages (
                chat_id, user_name, user_id, text, timestamp, chat_title,
                telegram_message_id, reply_to_message_id, role, thread_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            chat_id,
            bot_name,
            bot_id,
            text,
            timestamp,
            chat_title,
            telegram_message_id,
            reply_to_message_id,
            "assistant",
            thread_id,
        )

        logger.info(
            f"Executing SQL (Bot Reply): {cursor.mogrify(sql, params).decode('utf-8')}"
        )

        cursor.execute(sql, params)
        conn.commit()
        logger.info(f"Bot reply saved to database for chat {chat_id} ({chat_title})")
    except Exception as e:
        logger.error(f"Failed to log bot reply to database: {e}")
    finally:
        if conn:
            db_pool.putconn(conn)


def check_daily_usage_limit(chat_id: int, max_usage: int = 20) -> tuple[bool, int]:
    """
    Check if the chat has exceeded daily usage limit.
    Returns (can_use, current_usage_count)
    """
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()

        today = datetime.now(HK_TIMEZONE).date()

        cursor.execute(
            """
            SELECT usage_count FROM daily_ai_usage
            WHERE chat_id = %s AND usage_date = %s
            """,
            (chat_id, today),
        )

        result = cursor.fetchone()
        current_usage = result[0] if result else 0

        can_use = current_usage < max_usage
        logger.info(
            f"Chat {chat_id} daily usage: {current_usage}/{max_usage}, can_use: {can_use}"
        )

        return can_use, current_usage

    except Exception as e:
        logger.error(f"Failed to check daily usage limit: {e}")
        return True, 0
    finally:
        if conn:
            db_pool.putconn(conn)


def increment_daily_usage(chat_id: int) -> bool:
    """
    Increment the daily usage count for a chat.
    Returns True if successful, False otherwise.
    """
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()

        today = datetime.now(HK_TIMEZONE).date()

        cursor.execute(
            """
            INSERT INTO daily_ai_usage (chat_id, usage_date, usage_count)
            VALUES (%s, %s, 1)
            ON CONFLICT (chat_id, usage_date)
            DO UPDATE SET
                usage_count = daily_ai_usage.usage_count + 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (chat_id, today),
        )

        conn.commit()
        logger.info(f"Incremented daily usage for chat {chat_id}")
        return True

    except Exception as e:
        logger.error(f"Failed to increment daily usage: {e}")
        return False
    finally:
        if conn:
            db_pool.putconn(conn)
