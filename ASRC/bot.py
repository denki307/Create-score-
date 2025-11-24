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

import os
import random
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

# -------------------------
# 🔰 ⚚ 𝐌𝐁𝐓 ꭙ 𝐃𝐄𝐍𝐊𝐈 🜲
# -------------------------
OWNER_ID = 7252249791   # change to your Telegram ID

# -------------------------
# 🔰 LOAD TOKEN (Heroku ENV)
# -------------------------
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    print("❌ ERROR: BOT_TOKEN is missing in Heroku Config Vars")
    exit()

# -------------------------
# 🎮 CRICKET GAME SYSTEM
# -------------------------
user_scores = {}
game_active = {}

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

def handle_bat(update, context):
    user_id = update.effective_user.id

    # Game not started
    if user_id not in game_active or not game_active[user_id]:
        update.message.reply_text("Start game using /start")
        return

    # Validate
    if not update.message.text.isdigit():
        update.message.reply_text("Enter only numbers 1–6.")
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
            f"Start new game → /start",
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
# 👑 OWNER COMMAND
# -------------------------
def owner(update, context):
    if update.effective_user.id == OWNER_ID:
        update.message.reply_text("👑 You are the owner!")
    else:
        update.message.reply_text("❌ You are NOT the owner!")

# -------------------------
# 🚀 MAIN FUNCTION
# -------------------------
def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("owner", owner))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_bat))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
