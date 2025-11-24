import json
import os

SCORE_FILE = "score.json"


def load_score():
    """Load score from score.json file"""
    if not os.path.exists(SCORE_FILE):
        return {"runs": 0, "wickets": 0, "balls": 0}

    with open(SCORE_FILE, "r") as f:
        return json.load(f)


def save_score(score):
    """Save score to score.json file"""
    with open(SCORE_FILE, "w") as f:
        json.dump(score, f, indent=4)


def format_score(score):
    """Format score for sending to users"""
    return (
        f"🏏 *Current Score:*\n"
        f"Runs: *{score['runs']}*\n"
        f"Wickets: *{score['wickets']}*\n"
        f"Balls: *{score['balls']}*"
    )
