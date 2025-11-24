import random

class CricketGame:
    def __init__(self):
        self.user_score = 0
        self.bot_score = 0
        self.is_out = False

    def user_play(self, user_run: int):
        bot_run = random.randint(1, 6)
        if user_run == bot_run:
            self.is_out = True
            return f"OUT! You chose {user_run} and bot chose {bot_run}.\nFinal Score: {self.user_score}"
        self.user_score += user_run
        return f"You: {user_run} | Bot: {bot_run}\nScore: {self.user_score}"

    def bot_play(self):
        self.bot_score = random.randint(10, 36)
        return f"Bot scored {self.bot_score} runs!"
