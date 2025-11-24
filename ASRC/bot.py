import os
import random
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# -------------------------
# 🔰 BOT CONFIG
# -------------------------
OWNER_ID = 7252249791   # Put your actual Telegram ID here
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing in Heroku Config Vars")
    exit()

# -------------------------
# 🎮 GAME DATA
# -------------------------
user_scores = {}
game_active = {}

# -------------------------
# /start COMMAND
# -------------------------
def start(update, context):
    user_id = update.effective_user.id
    user_scores[user_id] = 0
    game_active[user_id] = True

    update.message.reply_text(
        "🏏 *Welcome to Cricket Game!*\n\n"
        "Send a number *1 to 6* to bat.\n"
        "If bot picks the same number → YOU ARE OUT!",
        parse_mode="Markdown"
    )

# -------------------------
# HANDLE BATTING INPUT
# -------------------------
def handle_bat(update, context):
    user_id = update.effective_user.id

    if user_id not in game_active or not game_active[user_id]:
        update.message.reply_text("Start the game using /start")
        return

    if not update.message.text.isdigit():
        update.message.reply_text("Enter only numbers 1 to 6.")
        return

    user_run = int(update.message.text)
    if not 1 <= user_run <= 6:
        update.message.reply_text("Choose between 1–6.")
        return

    bot_run = random.randint(1, 6)

    if user_run == bot_run:
        final = user_scores[user_id]
        update.message.reply_text(
            f"❌ *OUT!*\nBot chose {bot_run}\n\n"
            f"🏏 Your Final Score: *{final}*\n"
            f"Start a new game → /start",
            parse_mode="Markdown"
        )
        game_active[user_id] = False
        return

    user_scores[user_id] += user_run

    update.message.reply_text(
        f"🏏 You: {user_run}\n🤖 Bot: {bot_run}\n"
        f"Total Score: {user_scores[user_id]}"
    )

# -------------------------
# OWNER COMMAND
# -------------------------
def owner(update, context):
    if update.effective_user.id == OWNER_ID:
        update.message.reply_text("👑 You are the owner!")
    else:
        update.message.reply_text("❌ You are NOT the owner!")

# -------------------------
# MAIN FUNCTION
# -------------------------
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("owner", owner))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_bat))

    updater.start_polling()
    updater.idle()

# -------------------------
# RUN BOT
# -------------------------
if __name__ == "__main__":
    main()
