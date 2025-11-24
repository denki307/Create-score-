import random

def play_cricket():
    runs = random.randint(1, 6)

    result = f"🏏 You hit *{runs}* runs!"
    return result, runs
