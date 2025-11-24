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
