import psycopg2
from psycopg2 import pool
from config import DB_URL, logger, HK_TIMEZONE
from datetime import datetime


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
        
        # Create table for tracking daily AI chat usage
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


async def log_message(update, context):
    if update.message and update.message.text:
        chat_id = update.message.chat_id
        user = update.message.from_user
        message = update.message.text
        timestamp = update.message.date
        user_id = user.id
        chat_title = update.message.chat.title if update.message.chat.title else "Private Chat"

        user_name = user.first_name if user.first_name else '唔知邊條粉蛋'
        if user.last_name:
            user_name += " " + user.last_name

        logger.info(f"Received message in chat {chat_id} ({chat_title}) from {user_name} (ID: {user_id}): {message}")

        db_pool = DatabasePool.get_pool()
        conn = None
        try:
            conn = db_pool.getconn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (chat_id, user_name, user_id, text, timestamp, chat_title) VALUES (%s, %s, %s, %s, %s, %s)",
                (chat_id, user_name, user_id, message, timestamp, chat_title)
            )
            conn.commit()
            logger.info(f"Message saved to database for chat {chat_id} ({chat_title})")
        except Exception as e:
            logger.error(f"Failed to log message to database: {e}")
            # Do not send an error reply to Telegram; only log the error for backend monitoring.
        finally:
            if conn:
                db_pool.putconn(conn)


async def log_bot_reply(chat_id: int, chat_title: str, text: str, bot_id: int, bot_name: str):
    """Logs the bot's own replies."""
    timestamp = datetime.now(HK_TIMEZONE)
    db_pool = DatabasePool.get_pool()
    conn = None
    try:
        conn = db_pool.getconn()
        cursor = conn.cursor()

        sql = "INSERT INTO messages (chat_id, user_name, user_id, text, timestamp, chat_title) VALUES (%s, %s, %s, %s, %s, %s)"
        params = (chat_id, bot_name, bot_id, text, timestamp, chat_title)

        # Log the SQL query to be executed (Bot Reply)
        logger.info(f"Executing SQL (Bot Reply): {cursor.mogrify(sql, params).decode('utf-8')}")

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
        
        # Get today's date in Hong Kong timezone
        today = datetime.now(HK_TIMEZONE).date()
        
        # Check current usage for today
        cursor.execute("""
            SELECT usage_count FROM daily_ai_usage 
            WHERE chat_id = %s AND usage_date = %s
        """, (chat_id, today))
        
        result = cursor.fetchone()
        current_usage = result[0] if result else 0
        
        can_use = current_usage < max_usage
        logger.info(f"Chat {chat_id} daily usage: {current_usage}/{max_usage}, can_use: {can_use}")
        
        return can_use, current_usage
        
    except Exception as e:
        logger.error(f"Failed to check daily usage limit: {e}")
        # If there's an error, allow usage to prevent blocking
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
        
        # Get today's date in Hong Kong timezone
        today = datetime.now(HK_TIMEZONE).date()
        
        # Use UPSERT to increment usage count
        cursor.execute("""
            INSERT INTO daily_ai_usage (chat_id, usage_date, usage_count) 
            VALUES (%s, %s, 1)
            ON CONFLICT (chat_id, usage_date) 
            DO UPDATE SET 
                usage_count = daily_ai_usage.usage_count + 1,
                updated_at = CURRENT_TIMESTAMP
        """, (chat_id, today))
        
        conn.commit()
        logger.info(f"Incremented daily usage for chat {chat_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to increment daily usage: {e}")
        return False
    finally:
        if conn:
            db_pool.putconn(conn)
