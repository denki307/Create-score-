import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from game import play_cricket
from utils import load_score, save_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------
# START COMMAND
# ------------------------------
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🏏 Welcome to Cricket Game Bot!\n"
        "Type /play to start a match!"
    )

# ------------------------------
# PLAY COMMAND
# ------------------------------
def play(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    result, runs = play_cricket()

    # save score
    save_score(user_id, runs)

    update.message.reply_text(result)

# ------------------------------
# MY SCORE
# ------------------------------
def myscore(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    score = load_score(user_id)
    update.message.reply_text(f"🏏 Your total score: {score} runs")

# ------------------------------
# MAIN FUNCTION
# ------------------------------
def main():
    import os
    TOKEN = os.getenv("BOT_TOKEN")

    if TOKEN is None:
        logger.error("BOT_TOKEN is missing!")
        return

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("play", play))
    dp.add_handler(CommandHandler("myscore", myscore))

    logger.info("Bot Running...")
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
