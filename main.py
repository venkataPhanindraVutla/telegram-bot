import logging
import os
from collections import deque
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# --- Configuration ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# States
GET_NAME, CHATTING = range(2)

# In-memory data
waiting_queue = deque()
chat_partners = {}
user_names = {}


# --- Handler Functions (Synchronous) ---
def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if user.id in chat_partners:
        end(update, context)
    update.message.reply_text(
        f"👋 Welcome, {user.first_name}! What's your nickname?\n\n"
        "🔒 Your real account details are never shared."
    )
    return GET_NAME


def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user_names[user_id] = update.message.text
    update.message.reply_text(
        f"Great! I'll call you '{user_names[user_id]}'.\n\n"
        "➡️ Use /search to find a random chat partner.\n"
        "➡️ Use /end to stop the current chat.\n"
        "➡️ Use /help to see all commands."
    )
    return CHATTING


def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if user_id in chat_partners:
        update.message.reply_text("You're already chatting! Use /end to leave.")
        return CHATTING

    if user_id in waiting_queue:
        update.message.reply_text("Already searching! Please wait.")
        return CHATTING

    if waiting_queue:
        partner_id = waiting_queue.popleft()
        chat_partners[user_id] = partner_id
        chat_partners[partner_id] = user_id
        context.bot.send_message(chat_id=user_id, text="✅ You’re now connected!")
        context.bot.send_message(chat_id=partner_id, text="✅ You’re now connected!")
    else:
        waiting_queue.append(user_id)
        update.message.reply_text("⏳ Searching for a partner...")

    return CHATTING


def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if user_id in chat_partners:
        partner_id = chat_partners.pop(user_id)
        chat_partners.pop(partner_id, None)
        update.message.reply_text("❌ Disconnected.")
        context.bot.send_message(chat_id=partner_id, text="❌ Your partner disconnected.")
    elif user_id in waiting_queue:
        waiting_queue.remove(user_id)
        update.message.reply_text("You’ve been removed from the waiting list.")
    else:
        update.message.reply_text("You’re not in any chat right now.")

    return CHATTING


def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    msg = (
        "/start - Restart and set name\n"
        "/search - Find a chat partner\n"
        "/end - Leave chat\n"
        "/help - Show commands"
    )
    if user_id == ADMIN_ID:
        msg += "\n\n👑 Admin:\n/announcement <msg>\n/waitinglist"
    update.message.reply_text(msg)
    return CHATTING


def message_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id in chat_partners:
        partner_id = chat_partners[user_id]
        context.bot.copy_message(
            chat_id=partner_id,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )
    elif user_id in waiting_queue:
        update.message.reply_text("Still searching... please wait.")
    else:
        update.message.reply_text("Use /search to begin chatting.")
    return CHATTING


def announcement(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("Unauthorized.")
        return CHATTING

    msg = " ".join(context.args)
    if not msg:
        update.message.reply_text("Usage: /announcement <message>")
        return CHATTING

    all_ids = list(chat_partners.keys())
    for uid in all_ids:
        try:
            context.bot.send_message(chat_id=uid, text=f"📢 Announcement:\n\n{msg}")
        except:
            pass
    update.message.reply_text("Announcement sent!")
    return CHATTING


def waitinglist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != ADMIN_ID:
        update.message.reply_text("Unauthorized.")
        return CHATTING

    count = len(waiting_queue)
    update.message.reply_text(f"👥 Waiting users: {count}")
    return CHATTING


def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    update.message.reply_text("Action cancelled.")
    return ConversationHandler.END


# --- Main Entry Point (Synchronous) ---
def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            CHATTING: [
                CommandHandler("search", search),
                CommandHandler("end", end),
                CommandHandler("help", help_command),
                CommandHandler("announcement", announcement),
                CommandHandler("waitinglist", waitinglist),
                MessageHandler(filters.ALL & ~filters.COMMAND, message_forward),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)

    print("💖 Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
