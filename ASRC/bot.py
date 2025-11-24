import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from game import CricketGame
from utils import get_score_text

TOKEN = os.getenv("BOT_TOKEN")

game_sessions = {}


def start(update, context):
    user_id = update.effective_user.id
    game_sessions[user_id] = CricketGame()

    update.message.reply_text(
        "🏏 *Welcome to Cricket Game Bot!*\n\n"
        "Send a number *1 to 6* to bat.\n"
        "If bot chooses the same number → you're OUT! 😵",
        parse_mode="Markdown"
    )


def handle_input(update, context):
    user_id = update.effective_user.id

    if user_id not in game_sessions:
        update.message.reply_text("Type /start to begin a new game.")
        return

    game = game_sessions[user_id]

    if not update.message.text.isdigit():
        update.message.reply_text("Enter numbers only (1–6).")
        return

    user_run = int(update.message.text)

    if not 1 <= user_run <= 6:
        update.message.reply_text("Choose only between 1–6.")
        return

    bot_run, out, total = game.play(user_run)

    if out:
        update.message.reply_text(
            f"😵 OUT!\nBot chose {bot_run}\n\n"
            f"🏏 Final score: {total}\n"
            f"Use /start to play again."
        )
        del game_sessions[user_id]
        return

    update.message.reply_text(
        f"🏏 You: {user_run}\n🤖 Bot: {bot_run}\n"
        f"Total Score: {total}"
    )


def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text, handle_input))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()

from telegram.ext import Updater, CommandHandler, CallbackContext
from telegram import Update
import random

# -------------------------
# 🔰 ⚚ 𝐌𝐁𝐓 ꭙ 𝐃𝐄𝐍𝐊𝐈 🜲
# -------------------------
OWNER_ID = 7252249791   # <-- Change to your Telegram User ID

# -------------------------
# 🎮 Cricket Game Logic
# -------------------------

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🏏 Welcome to the Cricket Game!\n\n"
        "Use /bat to play your turn.\n"
        "Whoever gets OUT loses!"
    )

def bat(update: Update, context: CallbackContext):
    user_run = random.randint(1, 6)
    bot_run = random.randint(1, 6)

    if user_run == bot_run:
        update.message.reply_text(f"❌ OUT! You chose {user_run} and bot chose {bot_run}.\nGame Over!")
    else:
        update.message.reply_text(f"🏏 You hit *{user_run}* runs!\nBot chose {bot_run}. Continue batting...")

def owner(update: Update, context: CallbackContext):
    if update.message.from_user.id == OWNER_ID:
        update.message.reply_text("👑 You are the Owner!")
    else:
        update.message.reply_text("❌ You are not the owner.")

# -------------------------
# 🔥 BOT STARTER
# -------------------------

def main():
    TOKEN = "7671358820:AAFmF1LzCS2RmGMVWnxIjzCCoVMyCzl7tVs"  # Put your bot token here

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("bat", bat))
    dp.add_handler(CommandHandler("owner", owner))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
