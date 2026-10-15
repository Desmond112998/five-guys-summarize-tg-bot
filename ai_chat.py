from telegram import Update
from telegram.ext import ContextTypes

from ai import get_ai_chat_response
from config import AI_CHAT_SYSTEM_PROMPT, GATE_REJECT_REPLY, logger
from database import (
    attach_thread_to_message,
    check_daily_usage_limit,
    get_thread_messages,
    increment_daily_usage,
    log_bot_reply,
    log_message,
    resolve_thread_id,
)
from jev_gate import allow_user_turn, previous_assistant_from_history


async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles AI chat when the bot is mentioned or replied to.
    Uses Jev gate + per-user thread memory.
    """
    await log_message(update, context)

    message = update.message
    if not message or not message.text:
        return

    bot = await context.bot.get_me()
    bot_username = bot.username
    bot_id = bot.id

    is_reply_to_bot = (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.id == bot_id
    )
    is_mentioning_bot = f"@{bot_username}" in message.text

    if not (is_reply_to_bot or is_mentioning_bot):
        return

    user_text = message.text.replace(f"@{bot_username}", "").strip()
    if not user_text:
        return

    logger.info(
        f"Bot is mentioned or replied to in chat {message.chat_id}. Triggering AI response."
    )

    reply_to_id = (
        message.reply_to_message.message_id if message.reply_to_message else None
    )
    thread_id = resolve_thread_id(message.chat_id, message.from_user.id, reply_to_id)
    if not thread_id:
        await message.reply_text("哎呀，讀取對話紀錄時出錯！🤯")
        return

    attach_thread_to_message(
        message.chat_id, message.message_id, thread_id, text=user_text
    )

    history = get_thread_messages(message.chat_id, thread_id)
    if history is None:
        await message.reply_text("哎呀，讀取對話紀錄時出錯！🤯")
        return

    previous_assistant = previous_assistant_from_history(history)
    if not allow_user_turn(user_text, previous_assistant):
        await message.reply_text(
            GATE_REJECT_REPLY,
            reply_to_message_id=message.message_id,
        )
        return

    can_use, current_usage = check_daily_usage_limit(message.chat_id, max_usage=20)
    if not can_use:
        await message.reply_text(
            f"今日已經用咗 {current_usage} 次喇 Ching！😅 聽日再搵我傾偈啦～",
            reply_to_message_id=message.message_id,
        )
        return

    if not history or history[-1]["role"] != "user":
        history.append({"role": "user", "content": user_text})

    waiting_message = await message.reply_text(
        "諗緊點答… ⏳", reply_to_message_id=message.message_id
    )

    ai_response = get_ai_chat_response(AI_CHAT_SYSTEM_PROMPT, history)

    if ai_response and "系統" not in ai_response:
        increment_daily_usage(message.chat_id)
        _, updated_usage = check_daily_usage_limit(message.chat_id, max_usage=20)
        remaining_usage = 20 - updated_usage
        response_with_usage = f"{ai_response}\n\n💬 今日剩餘用量：{remaining_usage}/20"

        sent_message = await waiting_message.edit_text(response_with_usage)

        await log_bot_reply(
            chat_id=sent_message.chat_id,
            chat_title=sent_message.chat.title
            if sent_message.chat.title
            else "Private Chat",
            text=ai_response,
            bot_id=bot.id,
            bot_name=bot.name,
            telegram_message_id=waiting_message.message_id,
            thread_id=thread_id,
            reply_to_message_id=message.message_id,
        )
    else:
        await waiting_message.edit_text("系統諗到hang咗機，一陣再試過啦！😵")
