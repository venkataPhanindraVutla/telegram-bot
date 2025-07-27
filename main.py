# main.py

import logging
import os
import asyncio
from collections import deque
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Please set the TELEGRAM_TOKEN environment variable.")

# Support multiple admins
ADMIN_IDS = set(map(int, os.environ.get("ADMIN_ID", "").split(",")))

# Enable logging
logging.basicConfig(
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# State definitions
GET_NAME, CHATTING = range(2)

# --- Data Structures ---
def get_bot_data(context: ContextTypes.DEFAULT_TYPE):
    if "waiting_queue" not in context.bot_data:
        context.bot_data["waiting_queue"] = deque()
    if "chat_partners" not in context.bot_data:
        context.bot_data["chat_partners"] = {}
    return context.bot_data["waiting_queue"], context.bot_data["chat_partners"]

# --- Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    user_id = user.id
    _, chat_partners = get_bot_data(context)
    if user_id in chat_partners:
        await end_command(update, context)
    await update.message.reply_html(rf"👋 Welcome, {user.mention_html()}!")
    await update.message.reply_text(
        "To get started, please tell me what name or nickname you'd like to use.\n\n"
        "🔒 Privacy Notice: Your real Telegram account details are never shared."
    )
    return GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_name = update.message.text
    context.user_data["name"] = user_name
    await update.message.reply_text(
        f"Great! I'll call you '{user_name}'.\n\n"
        "➡️ Use /search to find a random chat partner.\n"
        "➡️ Use /end to stop the current chat.\n"
        "➡️ Use /help to see all commands.\n\n"
        "Happy chatting!"
    )
    return CHATTING

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    waiting_queue, chat_partners = get_bot_data(context)
    if 'name' not in context.user_data:
        await update.message.reply_text("Please use /start to set up your name first.")
        return CHATTING
    if user_id in chat_partners:
        await update.message.reply_text("You are already in a chat. Use /end to leave.")
        return CHATTING
    if user_id in waiting_queue:
        await update.message.reply_text("You are already searching. Please be patient.")
        return CHATTING
    if waiting_queue:
        partner_id = waiting_queue.popleft()
        chat_partners[user_id] = partner_id
        chat_partners[partner_id] = user_id
        user_name = context.user_data.get('name', 'Stranger')
        partner_name = context.bot_data.get(partner_id, {}).get('name', 'Stranger')
        logger.info(f"Matched {user_id} ({user_name}) with {partner_id} ({partner_name})")
        await context.bot.send_message(chat_id=user_id, text="✅ You are now connected!")
        await context.bot.send_message(chat_id=partner_id, text="✅ You are now connected!")
        if partner_id in context.bot_data:
            del context.bot_data[partner_id]
    else:
        waiting_queue.append(user_id)
        context.bot_data[user_id] = context.user_data
        logger.info(f"{user_id} ({context.user_data.get('name')}) added to the queue.")
        await update.message.reply_text("⏳ Searching for a partner...")
    return CHATTING

async def end_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    waiting_queue, chat_partners = get_bot_data(context)
    if user_id in chat_partners:
        partner_id = chat_partners.pop(user_id)
        if partner_id in chat_partners:
            del chat_partners[partner_id]
        logger.info(f"Chat ended between {user_id} and {partner_id}")
        await update.message.reply_text("You have disconnected.")
        try:
            await context.bot.send_message(chat_id=partner_id, text="The other person has disconnected.")
        except Exception as e:
            logger.error(f"Could not send end message to {partner_id}: {e}")
    elif user_id in waiting_queue:
        waiting_queue.remove(user_id)
        if user_id in context.bot_data:
            del context.bot_data[user_id]
        await update.message.reply_text("You are no longer searching.")
    else:
        await update.message.reply_text("You are not in an active chat.")
    return CHATTING

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    help_text = (
        "Here are the available commands:\n\n"
        "/start - Restart the bot and set a new name.\n"
        "/search - Find a random chat partner.\n"
        "/end - Disconnect from your current chat.\n"
        "/help - Show this help message."
    )
    if update.effective_user.id in ADMIN_IDS:
        help_text += (
            "\n\n*Admin Commands:*\n"
            "/announcement <msg> - Send message to all active users.\n"
            "/waitinglist - See users in queue.\n"
            "/status - Get bot stats."
        )
    await update.message.reply_text(help_text, parse_mode='Markdown')
    return CHATTING

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    message = update.message
    waiting_queue, chat_partners = get_bot_data(context)
    user_name = context.user_data.get("name", "Stranger")
    if user_id in chat_partners:
        partner_id = chat_partners[user_id]
        logger.info(f"Message from {user_id} ({user_name}) to {partner_id}")
        try:
            await context.bot.copy_message(
                chat_id=partner_id, from_chat_id=user_id, message_id=message.message_id
            )
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            await update.message.reply_text("Could not send your message. The chat may be disconnected.")
            chat_partners.pop(user_id, None)
            chat_partners.pop(partner_id, None)
    elif user_id in waiting_queue:
        await update.message.reply_text("Please wait, we are still searching for a partner.")
    else:
        await update.message.reply_text("Please use /search or /start to begin.")
    return CHATTING

async def announcement_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized.")
        return CHATTING
    _, chat_partners = get_bot_data(context)
    announcement_text = " ".join(context.args)
    if not announcement_text:
        await update.message.reply_text("Usage: /announcement <message>")
        return CHATTING
    all_active_users = set(chat_partners.keys())
    if not all_active_users:
        await update.message.reply_text("No one is chatting.")
        return CHATTING
    full_message = f"📢 Announcement 📢\n\n{announcement_text}"
    success_count, fail_count = 0, 0
    for chat_id in all_active_users:
        try:
            await context.bot.send_message(chat_id=chat_id, text=full_message)
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {chat_id}: {e}")
            fail_count += 1
    await update.message.reply_text(f"✅ Sent\nSuccess: {success_count} | Failed: {fail_count}")
    return CHATTING

async def waitinglist_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("You are not authorized.")
        return CHATTING
    waiting_queue, _ = get_bot_data(context)
    await update.message.reply_text(f"There are {len(waiting_queue)} user(s) waiting.")
    return CHATTING

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized.")
        return CHATTING
    waiting_queue, chat_partners = get_bot_data(context)
    users_online = len(chat_partners)
    await update.message.reply_text(
        f"📊 Active Chats: {users_online // 2}\n⏳ Waiting Users: {len(waiting_queue)}"
    )
    return CHATTING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

# --- Main ---
async def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            CHATTING: [
                CommandHandler("search", search_command),
                CommandHandler("end", end_command),
                CommandHandler("help", help_command),
                CommandHandler("announcement", announcement_command),
                CommandHandler("waitinglist", waitinglist_command),
                CommandHandler("status", status_command),
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_message),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    logger.info("💖 Bot started. Running in polling mode.")
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
