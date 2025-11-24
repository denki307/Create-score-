from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def run_keyboard():
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(str(i), callback_data=str(i))] for i in range(1,7)]
    )
