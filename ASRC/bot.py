import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- 1. CONFIGURATION ---
# Replace this with your actual token from @BotFather
TOKEN = "YOUR_BOT_TOKEN_HERE"

# Setup Logging to see errors in your terminal
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Game Storage: { chat_id: { data } }
games = {}

# --- 2. UTILITIES ---
def get_numbers_keyboard(side, chat_id):
    """Generates the 1-6 button grid."""
    # We use a short prefix to stay under Telegram's 64-character callback limit
    keyboard = [[
        InlineKeyboardButton(str(i), callback_data=f"{side}|{chat_id}|{i}") 
        for i in range(1, 7)
    ]]
    return InlineKeyboardMarkup(keyboard)

# --- 3. COMMAND HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start and the Bowler joining via DM."""
    user = update.effective_user
    
    # Check if this is a deep-link from a group (e.g., /start bowl_123)
    if context.args and context.args[0].startswith("bowl_"):
        chat_id = context.args[0].replace("bowl_", "")
        
        if chat_id not in games:
            await update.message.reply_text("❌ This game session has expired.")
            return

        game = games[chat_id]
        
        # Assign bowler if slot is empty
        if game['bowler_id'] is None:
            if user.id == game['batsman_id']:
                await update.message.reply_text("🚫 You are the batsman! You can't bowl to yourself.")
                return
            
            game['bowler_id'] = user.id
            game['bowler_name'] = user.first_name
            
            # Notify the group that a bowler has joined
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎳 **{user.first_name}** has joined as the Bowler!\n\nBatsman, pick your number!",
                reply_markup=get_numbers_keyboard("bat", chat_id),
                parse_mode="Markdown"
            )

        await update.message.reply_text(
            f"🎳 **Bowling Mode!**\nMatch against: {game['batsman_name']}\nPick your number:",
            reply_markup=get_numbers_keyboard("bowl", chat_id),
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("👋 Welcome! Add me to a group and type /play to start Hand Cricket!")

async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts a new game in a group."""
    if update.effective_chat.type == "private":
        await update.message.reply_text("❌ Please use /play inside a Group!")
        return

    chat_id = str(update.effective_chat.id)
    user = update.effective_user
    
    # Initialize game state
    games[chat_id] = {
        'batsman_id': user.id,
        'batsman_name': user.first_name,
        'bowler_id': None,
        'bowler_name': "Waiting...",
        'bat_choice': None,
        'bowl_choice': None,
        'score': 0
    }

    bot_info = await context.bot.get_me()
    bowl_url = f"https://t.me/{bot_info.username}?start=bowl_{chat_id}"
    
    keyboard = [[InlineKeyboardButton("🎳 Join as Bowler (DM)", url=bowl_url)]]
    
    await update.message.reply_text(
        f"🏏 **HAND CRICKET MATCH**\n\n"
        f"👤 **Batsman:** {user.first_name}\n"
        f"🤖 **Bowler:** (Waiting for opponent...)\n\n"
        f"The bowler must click the button below to play in private!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# --- 4. CALLBACK HANDLER (The Logic) ---
async def handle_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    # Format: action|chat_id|number
    try:
        data_parts = query.data.split("|")
        action, chat_id, num = data_parts[0], data_parts[1], int(data_parts[2])
    except:
        return

    if chat_id not in games:
        await query.answer("Game not found.")
        return

    game = games[chat_id]
    user_id = query.from_user.id

    # BATSMAN logic
    if action == "bat":
        if user_id != game['batsman_id']:
            await query.answer("Only the Batsman can pick!", show_alert=True)
            return
        if game['bat_choice'] is not None:
            await query.answer("You already picked! Waiting for bowler.")
            return
        
        game['bat_choice'] = num
        await query.answer(f"You picked {num}!")
        await process_turn(chat_id, context, query)

    # BOWLER logic
    elif action == "bowl":
        if user_id != game['bowler_id']:
            await query.answer("You are not the bowler!")
            return
        if game['bowl_choice'] is not None:
            await query.answer("Waiting for batsman.")
            return

        game['bowl_choice'] = num
        await query.edit_message_text(f"✅ You bowled {num}! Go check the group results.")
        await process_turn(chat_id, context)

async def process_turn(chat_id, context, query=None):
    game = games[chat_id]
    
    # If both have picked their numbers
    if game['bat_choice'] is not None and game['bowl_choice'] is not None:
        bat = game['bat_choice']
        bowl = game['bowl_choice']
        
        if bat == bowl:
            # OUT
            result_text = (
                f"❌ **OUT!**\n\n"
                f"🏏 Batsman chose: {bat}\n"
                f"🎳 Bowler chose: {bowl}\n\n"
                f"🔥 **FINAL SCORE: {game['score']}**"
            )
