from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from config import BOT_TOKEN
from game_engine import CricketGame
import keyboards

game_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏏 Welcome to Cricket Bot! Use /play to start.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game_sessions[user_id] = CricketGame()
    await update.message.reply_text("Choose your run:", reply_markup=keyboards.run_keyboard())

async def run_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    game = game_sessions[user_id]
    choice = int(query.data)
    result = game.user_play(choice)
    await query.edit_message_text(result)
    if game.is_out:
        await query.message.reply_text(game.bot_play())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Choose 1–6. If bot matches, you're OUT!")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CallbackQueryHandler(run_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
