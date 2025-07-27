import logging
import os
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

# --- ENV Setup ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", 8080))

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- States ---
GET_NAME, CHATTING = range(2)

# --- Main Memory Structures ---
waiting_queue = deque()
chat_partners = {}
user_data = {}

# --- Bot Logic ---

def get_name_by_id(user_id):
    return user_data.get(user_id, {}).get("name", "Stranger")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id in chat_partners:
        await end(update, context)
    await update.message.reply_text("👋 Welcome! Please enter your nickname:")
    return GET_NAME

async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    name = update.message.text
    user_data[user_id] = {"name": name}
    await update.message.reply_text(f"Hi {name}! Use /search to find a partner ✨")
    return CHATTING

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id in chat_partners:
        await update.message.reply_text("You're already chatting! Use /end to leave.")
        return CHATTING

    if user_id in waiting_queue:
        await update.message.reply_text("Already searching... please wait.")
        return CHATTING

    if waiting_queue:
        partner_id = waiting_queue.popleft()
        chat_partners[user_id] = partner_id
        chat_partners[partner_id] = user_id
        await context.bot.send_message(chat_id=user_id, text="✅ Partner found! Say hi!")
        await context.bot.send_message(chat_id=partner_id, text="✅ Partner found! Say hi!")
    else:
        waiting_queue.append(user_id)
        await update.message.reply_text("⏳ Searching for a partner...")

    return CHATTING

async def end(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id

    if user_id in chat_partners:
        partner_id = chat_partners.pop(user_id)
        chat_partners.pop(partner_id, None)
        await context.bot.send_message(chat_id=partner_id, text="❌ Your partner has left the chat.")
        await update.message.reply_text("❌ You have left the chat.")
    elif user_id in waiting_queue:
        waiting_queue.remove(user_id)
        await update.message.reply_text("🚫 Search cancelled.")
    else:
        await update.message.reply_text("You're not in a chat right now.")

    return CHATTING

async def forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if user_id in chat_partners:
        partner_id = chat_partners[user_id]
        await context.bot.copy_message(chat_id=partner_id, from_chat_id=user_id, message_id=update.message.message_id)
    else:
        await update.message.reply_text("Use /search to start chatting.")
    return CHATTING

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    help_text = (
        "/start - Restart the bot\n"
        "/search - Find a chat partner\n"
        "/end - Leave chat\n"
        "/help - Show help"
    )
    if update.effective_user.id == ADMIN_ID:
        help_text += "\n/announce <msg> - Broadcast"
    await update.message.reply_text(help_text)
    return CHATTING

async def announce(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Unauthorized.")
        return CHATTING
    msg = " ".join(context.args)
    for uid in set(chat_partners):
        await context.bot.send_message(chat_id=uid, text=f"📢 Announcement:\n{msg}")
    await update.message.reply_text("📨 Broadcast done!")
    return CHATTING

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Action cancelled.")
    return ConversationHandler.END

# --- Main Entry Point ---
async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_name)],
            CHATTING: [
                CommandHandler("search", search),
                CommandHandler("end", end),
                CommandHandler("help", help_command),
                CommandHandler("announce", announce),
                MessageHandler(filters.TEXT & ~filters.COMMAND, forward),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)

    k_service = os.environ.get("K_SERVICE", "")
    project_id = os.environ.get("GCLOUD_PROJECT", "")
    region = os.environ.get("K_CONFIGURATION", "us-central1").split("-")[1]
    webhook_url = f"https://{k_service}-{project_id}-{region}.a.run.app"

    logger.info("💖 Bot started with webhook at: %s", webhook_url)
    await app.run_webhook(listen="0.0.0.0", port=PORT, webhook_url=webhook_url)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
