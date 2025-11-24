import os
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from game import CricketGame
from utils import get_score_text

TOKEN = os.getenv("BOT_TOKEN")  # Heroku reads token from config vars

game_sessions = {}


def start(update, context):
    user_id = update.effective_user.id
    game_sessions[user_id] = CricketGame()

    update.message.reply_text(
        "🏏 Welcome to Cricket Game Bot!\n"
        "Type a number between 1–6 to bat.\n"
        "If bot picks the same number → OUT!"
    )


def handle_input(update, context):
    user_id = update.effective_user.id

    if user_id not in game_sessions:
        update.message.reply_text("Type /start to begin a new game.")
        return

    game = game_sessions[user_id]

    if not update.message.text.isdigit():
        update.message.reply_text("Please enter a number between 1–6.")
        return

    user_run = int(update.message.text)
    if user_run < 1 or user_run > 6:
        update.message.reply_text("Invalid number! Enter 1–6 only.")
        return

    bot_run, out, total = game.play(user_run)

    if out:
        update.message.reply_text(
            f"😵 You're OUT!\n"
            f"Bot chose: {bot_run}\n"
            f"Your final score: {total}\n\n"
            f"Type /start to play again."
        )
        del game_sessions[user_id]
        return

    update.message.reply_text(
        f"🏏 You chose: {user_run}\n"
        f"🤖 Bot chose: {bot_run}\n\n"
        f"Current Score: {total}\n"
        f"Keep playing!"
    )


def main():
    print("🚀 Bot Starting...")

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text, handle_input))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
