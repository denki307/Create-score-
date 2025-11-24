import random

class CricketGame:
    def __init__(self):
        self.score = 0

    def play(self, user_run):
        bot_run = random.randint(1, 6)
        if bot_run == user_run:
            return bot_run, True, self.score  # OUT
        else:
            self.score += user_run
            return bot_run, False, self.score
