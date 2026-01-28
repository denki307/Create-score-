import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import

# 1. Setup Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 2. Game Storage (In-memory for this example)
# In a real bot, use a Database (SQLite/MongoDB)
games = {} 

# 3. Keyboards
def get_numbers_keyboard(side):
    # 'side' identifies if this is a batting or bowling click
    keyboard = [[InlineKeyboardButton(str(i), callback_data=f"{side}_{i}") for i in range(1, 7)]]
    return InlineKeyboardMarkup(keyboard)

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle Deep-linking: When bowler comes from Group to DM
    if context.args and "bowl_" in context.args[0]:
        game_id = context.args[0].replace("bowl_", "")
        await update.message.reply_text(
            f"🎳 **Bowling Mode!**\nGame ID: {game_id}\nPick your number to bowl:",
            reply_markup=get_numbers_keyboard("bowl")
        )
        return

    await update.message.reply_text("Welcome! Use /play in a group to start Hand Cricket.")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Initialize game state
    games[chat_id] = {
        'batsman_id': user.id,
        'batsman_name': user.first_name,
        'bowler_id': None,
        'bat_choice': None,
        'bowl_choice': None,
        'score': 0
    }

    # Deep link to invite a bowler to DM
    bot_username = (await context.bot.get_me()).username
    bowl_url = f"https://t.me/{bot_username}?start=bowl_{chat_id}"
    
    keyboard = [
        [InlineKeyboardButton("🏏 Bat (Group)", callback_data="bat_info")],
        [InlineKeyboardButton("🎳 Bowl (Go to DM)", url=bowl_url)]
    ]
    
    await update.message.reply_text(
        f"🏏 **Match Started!**\n**Batsman:** {user.first_name}\n\nWaiting for a Bowler to join via the button below...",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- Handling Choices ---
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # Handle Batting in Group
    if data.startswith("bat_"):
        # We find the game associated with this chat
        chat_id = str(query.message.chat_id)
        if chat_id not in games: return
        
        game = games[chat_id]
        if user_id != game['batsman_id']:
            await query.answer("You are not the Batsman!", show_alert=True)
            return
            
        # Instead of picking here, we show the numbers
        await query.edit_message_reply_markup(reply_markup=get_numbers_keyboard(f"run_{chat_id}"))

    # Handle Actual Number Picked (Batsman)
    elif data.startswith("run_"):
        parts = data.split("_")
        chat_id, num = parts[1], int(parts[2])
        games[chat_id]['bat_choice'] = num
        await query.answer(f"You chose {num}. Waiting for bowler...")
        await check_result(chat_id, context, query.message)

    # Handle Actual Number Picked (Bowler in DM)
    elif data.startswith("bowl_"):
        num = int(data.split("_")[1])
        # Find which game this bowler belongs to (Logic simplified for 1 active game per user)
        # In production, store user_id -> chat_id mapping in DB
        for gid, gdata in games.items():
            if gdata['bowl_choice'] is None: # Logic to assign bowler
                games[gid]['bowl_choice'] = num
                games[gid]['bowler_id'] = user_id
                await query.edit_message_text(f"✅ You bowled {num}! Check the group.")
                await check_result(gid, context)
                break

async def check_result(chat_id, context, message=None):
    game = games[chat_id]
    if game['bat_choice'] and game['bowl_choice']:
        bat = game['bat_choice']
        bowl = game['bowl_choice']
        
        if bat == bowl:
            text = f"❌ **OUT!**\nBoth chose {bat}.\nFinal Score: {game['score']}"
            del games[chat_id]
        else:
            game['score'] += bat
            text = f"✅ {bat} Runs!\nTotal Score: {game['score']}\n\nNext ball: Batsman pick a number!"
            game['bat_choice'] = None
            game['bowl_choice'] = None
            # Refresh group keyboard
            
        if message:
            await message.edit_text(text, reply_markup=get_numbers_keyboard(f"run_{chat_id}"), parse_mode="Markdown")
        else:
            await context.bot.send_message(chat_id, text, reply_markup=get_numbers_keyboard(f"run_{chat_id}"), parse_mode="Markdown")

# --- Main ---
if __name__ == "__main__":
    TOKEN = "YOUR_BOT_TOKEN_HERE"
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CallbackQueryHandler(handle_choice))
    
    print("Bot is live...")
    app.run_polling()
