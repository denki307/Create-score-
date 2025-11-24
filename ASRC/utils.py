# utils.py — Helper functions for Cricket Game Bot

import random

def get_random_run():
    """Returns a random run between 0 and 6."""
    return random.randint(0, 6)

def format_score(user_score, wickets):
    return f"🏏 Score: {user_score} / {wickets}"

def get_start_message():
    return (
        "🏏 *Cricket Game Started!*\n"
        "Choose a run from *0 to 6*.\n"
        "If your number matches the bot's number → *OUT!*"
    )

def get_out_message(final_score):
    return (
        f"😢 *OUT!*\n\n"
        f"Your final score: *{final_score}*\n"
        "Send /start to play again!"
    )

def get_ball_result(user_run, bot_run, total_score):
    return (
        f"👉 You played: *{user_run}*\n"
        f"🤖 Bot bowled: *{bot_run}*\n"
        f"📌 Total Score: *{total_score}*"
    )
