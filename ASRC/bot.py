import asyncio
import inspect
import io
import os
import random
import urllib.parse
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from pyrogram import Client, enums, filters
from pyrogram.errors import FloodWait, MessageNotModified, RPCError
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# ================= CONFIGURATION (HEROKU + LOCAL READY) =================
API_ID = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))  # Bot Owner Telegram User ID

app = Client(
    "DynamicColorCricketBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Global Storage
matches = {}  # {chat_id: match_dict}
active_bowlers = {}  # {bowler_user_id: chat_id}
host_active_matches = {} # {host_user_id: group_chat_id}  <-- NEW: Maps Host to their active match
pending_gif_save = {}  # {owner_id: file_id}
BOT_USERNAME = None  # Auto-fetched on startup

# 10 Official IPL Teams Dictionary
IPL_TEAMS = {
    "CSK": "CSK 💛",
    "MI": "MI 💙",
    "RCB": "RCB ❤️",
    "KKR": "KKR 💜",
    "SRH": "SRH 🧡",
    "RR": "RR 🩷",
    "GT": "GT 🩵",
    "DC": "DC 💙",
    "PBKS": "PBKS ❤️",
    "LSG": "LSG 🩵",
}

# Custom Telegram GIF file_ids saved by OWNER in Bot DM
CUSTOM_GIFS = {
    "WICKET": [],
    6: [],
    4: [],
    "WIN": [],
}

# Exact Cricket Search Queries for Live Tenor Fetcher
TENOR_SEARCH_QUERIES = {
    "WICKET": [
        "cricket bowled stumps flying",
        "cricket umpire out finger",
        "virat kohli wicket celebration",
        "jasprit bumrah bowled wicket",
    ],
    6: [
        "virat kohli six shot cricket",
        "virat kohli lofted shot six",
        "ms dhoni six cricket",
        "rohit sharma six shot",
    ],
    4: [
        "virat kohli cover drive four",
        "cricket boundary four shot",
    ],
    "WIN": [
        "virat kohli winning celebration",
        "india cricket win celebration",
    ],
}

# Verified Direct Tenor Cricket GIF Fallbacks
FALLBACK_CRICKET_GIFS = {
    "WICKET": ["https://media.tenor.com/f3losXlErrQAAAAM/ms-dhoni-dhoni.gif"],
    6: ["https://media.tenor.com/f3losXlErrQAAAAM/ms-dhoni-dhoni.gif"],
    4: ["https://media.tenor.com/f3losXlErrQAAAAM/ms-dhoni-dhoni.gif"],
    "WIN": ["https://media.tenor.com/f3losXlErrQAAAAM/ms-dhoni-dhoni.gif"],
}

# Inspect InlineKeyboardButton parameters once at startup
_BTN_PARAMS = inspect.signature(InlineKeyboardButton.__init__).parameters
_COLOR_CYCLE = ["blue", "green", "red"]
_click_counter = 0


# ================= USER MENTION & TEXT HELPERS =================
def mention(user_id: int, name: str) -> str:
    """Creates a clickable Telegram user mention that notifies the player."""
    clean_name = (
        str(name).replace("[", "").replace("]", "").replace("*", "").strip()
        or "Player"
    )
    return f"[{clean_name}](tg://user?id={user_id})"


def clean_img_text(text: str) -> str:
    """Strips emojis/unsupported glyphs so Pillow renders crisp text."""
    cleaned = "".join(c for c in str(text) if ord(c) < 65535 and ord(c) != 65039)
    ascii_safe = "".join(c for c in cleaned if 32 <= ord(c) <= 126).strip()
    return ascii_safe or "Player"


# ================= DYNAMIC COLOR BUTTON ENGINE =================
def next_random_color() -> str:
    """Returns a dynamically shifting color on every call/click."""
    global _click_counter
    _click_counter += 1
    return random.choice(_COLOR_CYCLE)


def c_btn(
    text: str, callback_data: str = None, url: str = None, color: str = None
) -> InlineKeyboardButton:
    """100% Error-Free Kurigram Colored Button Builder."""
    if color is None:
        color = next_random_color()

    kwargs = {"text": text}
    if callback_data: kwargs["callback_data"] = callback_data
    if url: kwargs["url"] = url

    if "style" in _BTN_PARAMS:
        if hasattr(enums, "ButtonStyle"):
            bs = enums.ButtonStyle
            style_map = {
                "blue": getattr(bs, "PRIMARY", getattr(bs, "BLUE", None)),
                "green": getattr(bs, "SUCCESS", getattr(bs, "GREEN", None)),
                "red": getattr(bs, "DANGER", getattr(bs, "RED", None)),
            }
            if style_map.get(color) is not None:
                kwargs["style"] = style_map[color]
                return InlineKeyboardButton(**kwargs)
        try:
            return InlineKeyboardButton(**kwargs, style=color)
        except Exception:
            pass

    flag_map = {"blue": "primary", "green": "success", "red": "danger"}
    flag_name = flag_map.get(color)
    if flag_name and flag_name in _BTN_PARAMS:
        kwargs[flag_name] = True
        return InlineKeyboardButton(**kwargs)

    if "color" in _BTN_PARAMS:
        kwargs["color"] = color
        return InlineKeyboardButton(**kwargs)

    return InlineKeyboardButton(**kwargs)


# ================= AUTO-GENERATED WINNER SCORECARD IMAGE ENGINE =================
def load_font(size: int, bold: bool = True):
    font_paths = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "arialbd.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "arial.ttf",
        ]
    )
    for path in font_paths:
        if os.path.exists(path):
            try: return ImageFont.truetype(path, size)
            except Exception: pass
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()


def generate_winner_scorecard_image(
    match: dict, win_key: str, lose_key: str, banner_text: str
) -> io.BytesIO:
    win_team = match[win_key]
    lose_team = match[lose_key]
    is_tie = win_key == lose_key

    max_players = max(len(win_team["players"]), len(lose_team["players"]), 2)
    width = 1100
    height = max(680, 420 + (max_players * 44))

    img = Image.new("RGB", (width, height), color=(11, 15, 25))
    draw = ImageDraw.Draw(img)

    f_header = load_font(34, bold=True)
    f_banner = load_font(28, bold=True)
    f_team = load_font(30, bold=True)
    f_score = load_font(24, bold=True)
    f_sub = load_font(20, bold=True)
    f_player = load_font(20, bold=False)
    f_award = load_font(21, bold=True)

    draw.rounded_rectangle([(30, 20), (width - 30, 145)], radius=18, fill=(22, 30, 50), outline=(255, 215, 0), width=3)
    draw.text((width // 2, 55), f"IPL {match.get('overs_limit', 6)}-OVER CHAMPIONSHIP RESULT", fill=(255, 215, 0), font=f_header, anchor="mm")
    clean_banner = clean_img_text(banner_text).upper()
    draw.text((width // 2, 108), clean_banner, fill=(80, 255, 140), font=f_banner, anchor="mm")

    box_top = 170
    box_bottom = height - 135
    left_box = [(30, box_top), (535, box_bottom)]
    right_box = [(565, box_top), (width - 30, box_bottom)]

    draw.rounded_rectangle(left_box, radius=16, fill=(14, 38, 28), outline=(46, 213, 115), width=3)
    draw.rounded_rectangle(right_box, radius=16, fill=(40, 18, 26), outline=(255, 71, 87), width=3)

    def draw_team_panel(t_dict: dict, x_center: int, x_left: int, badge: str, badge_color: tuple):
        t_name = clean_img_text(t_dict["name"]).upper()
        overs_s = f"{t_dict['balls']//6}.{t_dict['balls']%6}"
        score_s = f"SCORE: {t_dict['score']}/{t_dict['wickets']} ({overs_s} / {match.get('overs_limit', 6)}.0 OVERS)"

        draw.text((x_center, box_top + 32), badge, fill=badge_color, font=f_sub, anchor="mm")
        draw.text((x_center, box_top + 70), t_name, fill=(255, 255, 255), font=f_team, anchor="mm")
        draw.text((x_center, box_top + 110), score_s, fill=(255, 215, 0), font=f_score, anchor="mm")
        draw.line([(x_left + 20, box_top + 138), (x_left + 485, box_top + 138)], fill=badge_color, width=2)

        draw.text((x_left + 25, box_top + 152), "PLAYER NAME", fill=(180, 200, 220), font=f_sub)
        draw.text((x_left + 310, box_top + 152), "BAT", fill=(180, 200, 220), font=f_sub)
        draw.text((x_left + 405, box_top + 152), "BOWL", fill=(180, 200, 220), font=f_sub)

        y_cursor = box_top + 190
        for idx, (uid, p_name) in enumerate(t_dict["players"].items()):
            st = match["stats"].get(uid, {})
            runs = st.get("runs", 0)
            balls = st.get("balls_faced", 0)
            wkts = st.get("wickets", 0)
            runs_c = st.get("runs_conceded", 0)
            balls_b = st.get("balls_bowled", 0)

            not_out_star = "*" if (uid not in match.get("all_out_history", set()) and balls > 0) else ""
            p_clean = clean_img_text(p_name)[:16]
            cap_tag = " (C)" if idx == 0 else ""
            bat_str = f"{runs}{not_out_star} ({balls})"
            bowl_str = f"{wkts}-{runs_c}" if balls_b > 0 else "-"

            draw.text((x_left + 25, y_cursor), f"{idx+1}. {p_clean}{cap_tag}", fill=(240, 245, 255), font=f_player)
            draw.text((x_left + 310, y_cursor), bat_str, fill=(120, 255, 170), font=f_player)
            draw.text((x_left + 405, y_cursor), bowl_str, fill=(130, 210, 255), font=f_player)
            y_cursor += 40

    if is_tie:
        draw_team_panel(match["team_A"], 282, 30, "TEAM 1 (TIED)", (255, 215, 0))
        draw_team_panel(match["team_B"], 817, 565, "TEAM 2 (TIED)", (255, 215, 0))
    else:
        draw_team_panel(win_team, 282, 30, "★ CHAMPIONS / WINNER ★", (46, 213, 115))
        draw_team_panel(lose_team, 817, 565, "RUNNER-UP TEAM", (255, 107, 129))

    draw.rounded_rectangle([(30, height - 115), (width - 30, height - 20)], radius=14, fill=(22, 30, 50), outline=(100, 160, 255), width=2)
    stats_list = list(match["stats"].values())
    if stats_list:
        top_bat = max(stats_list, key=lambda x: (x["runs"], -x["balls_faced"]))
        top_bowl = max(stats_list, key=lambda x: (x["wickets"], -x["runs_conceded"]))
        bat_txt = f"BEST BATSMAN: {clean_img_text(top_bat['name'])} — {top_bat['runs']} Runs ({top_bat['balls_faced']} Balls)"
        bowl_txt = f"BEST BOWLER: {clean_img_text(top_bowl['name'])} — {top_bowl['wickets']} Wickets ({top_bowl['runs_conceded']} Runs)"
    else:
        bat_txt = "BEST BATSMAN: N/A"
        bowl_txt = "BEST BOWLER: N/A"

    draw.text((width // 2, height - 85), bat_txt, fill=(255, 215, 0), font=f_award, anchor="mm")
    draw.text((width // 2, height - 48), bowl_txt, fill=(120, 220, 255), font=f_award, anchor="mm")

    bio = io.BytesIO()
    bio.name = "ipl_match_winner.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


# ================= LIVE TENOR CRICKET GIF ENGINE =================
async def fetch_live_cricket_gif(event_key) -> list:
    queries = TENOR_SEARCH_QUERIES.get(event_key, ["cricket six"])
    query = urllib.parse.quote(random.choice(queries))
    url = f"https://g.tenor.com/v1/search?q={query}&key=LIVDSRZULELA&limit=8&media_filter=minimal"

    gifs = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=4) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data.get("results", []):
                        media = item.get("media", [{}])[0]
                        mp4_url = media.get("mp4", {}).get("url") or media.get("gif", {}).get("url")
                        if mp4_url: gifs.append(mp4_url)
    except Exception: pass
    return gifs


async def send_event_gif(client: Client, chat_id: int, event_key, caption: str, auto_delete: int = 12):
    kb = InlineKeyboardMarkup([[c_btn("🎬 Match Highlight", callback_data="noop", color=next_random_color())]])
    candidates = list(CUSTOM_GIFS.get(event_key, []))
    random.shuffle(candidates)

    if not candidates:
        live_gifs = await fetch_live_cricket_gif(event_key)
        if live_gifs:
            random.shuffle(live_gifs)
            candidates.extend(live_gifs)

    candidates.extend(FALLBACK_CRICKET_GIFS.get(event_key, []))

    for anim in candidates:
        try:
            gif_msg = await client.send_animation(chat_id=chat_id, animation=anim, caption=caption, reply_markup=kb)
            if auto_delete > 0:
                await asyncio.sleep(auto_delete)
                try: await gif_msg.delete()
                except Exception: pass
            return
        except Exception: continue


# ================= SAFE TELEGRAM API WRAPPERS =================
async def safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None):
    try:
        return await message.edit_text(text=text, reply_markup=reply_markup)
    except MessageNotModified:
        if reply_markup:
            try: return await message.edit_reply_markup(reply_markup=reply_markup)
            except Exception: pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await safe_edit(message, text, reply_markup)
    except Exception: pass


async def safe_answer(cq: CallbackQuery, text: str = "", show_alert: bool = False):
    try: await cq.answer(text, show_alert=show_alert)
    except Exception: pass


# ================= DYNAMIC KEYBOARD GENERATORS =================
def get_overs_kb() -> InlineKeyboardMarkup:
    """FEATURE 2: Host selects 1 to 10 Overs before lobby starts"""
    return InlineKeyboardMarkup([
        [
            c_btn("1 Over", callback_data="setovers_1", color=next_random_color()),
            c_btn("2 Overs", callback_data="setovers_2", color=next_random_color()),
            c_btn("3 Overs", callback_data="setovers_3", color=next_random_color()),
        ],
        [
            c_btn("4 Overs", callback_data="setovers_4", color=next_random_color()),
            c_btn("5 Overs", callback_data="setovers_5", color=next_random_color()),
            c_btn("6 Overs", callback_data="setovers_6", color=next_random_color()),
        ],
        [
            c_btn("7 Overs", callback_data="setovers_7", color=next_random_color()),
            c_btn("8 Overs", callback_data="setovers_8", color=next_random_color()),
            c_btn("9 Overs", callback_data="setovers_9", color=next_random_color()),
        ],
        [
            c_btn("10 OVERS MATCH", callback_data="setovers_10", color="blue"),
        ],
    ])


def get_lobby_kb(match: dict, bot_username: str) -> InlineKeyboardMarkup:
    colors = random.sample(_COLOR_CYCLE, 3)
    tA_name = match["team_A"]["name"]
    tB_name = match["team_B"]["name"]

    return InlineKeyboardMarkup([
        [
            c_btn(f"Join {tA_name}", callback_data="join_A", color=colors[0]),
            c_btn(f"Join {tB_name}", callback_data="join_B", color=colors[1]),
        ],
        [
            c_btn("✏️ Choose IPL Team Names", callback_data="open_ipl_menu", color=colors[2]),
        ],
        [
            c_btn("🔄 Refresh Colors", callback_data="refresh_lobby", color=next_random_color()),
            c_btn("🚪 Leave Lobby", callback_data="leave_lobby", color=next_random_color()),
        ],
        [
            c_btn("🤖 Activate Bot DM", url=f"https://t.me/{bot_username}?start=cricket", color=next_random_color()),
        ],
        [
            c_btn("🚀 Start Match (Host)", callback_data="start_game", color=next_random_color()),
            c_btn("✖ End Lobby (Host)", callback_data="cancel_game", color=next_random_color()),
        ],
    ])


def get_ipl_team_selection_kb(match: dict, standalone: bool = False) -> InlineKeyboardMarkup:
    tA_curr = match["team_A"]["name"]
    tB_curr = match["team_B"]["name"]

    rows = [
        [c_btn(f"⬇️ Select for {tA_curr} (Team 1) ⬇️", callback_data="noop", color="blue")],
        [c_btn("CSK 💛", "setipl_A_CSK", color=next_random_color()), c_btn("MI 💙", "setipl_A_MI", color=next_random_color()), c_btn("RCB ❤️", "setipl_A_RCB", color=next_random_color()), c_btn("KKR 💜", "setipl_A_KKR", color=next_random_color()), c_btn("SRH 🧡", "setipl_A_SRH", color=next_random_color())],
        [c_btn("RR 🩷", "setipl_A_RR", color=next_random_color()), c_btn("GT 🩵", "setipl_A_GT", color=next_random_color()), c_btn("DC 💙", "setipl_A_DC", color=next_random_color()), c_btn("PBKS ❤️", "setipl_A_PBKS", color=next_random_color()), c_btn("LSG 🩵", "setipl_A_LSG", color=next_random_color())],
        [c_btn(f"⬇️ Select for {tB_curr} (Team 2) ⬇️", callback_data="noop", color="red")],
        [c_btn("CSK 💛", "setipl_B_CSK", color=next_random_color()), c_btn("MI 💙", "setipl_B_MI", color=next_random_color()), c_btn("RCB ❤", "setipl_B_RCB", color=next_random_color()), c_btn("KKR 💜", "setipl_B_KKR", color=next_random_color()), c_btn("SRH 🧡", "setipl_B_SRH", color=next_random_color())],
        [c_btn("RR 🩷", "setipl_B_RR", color=next_random_color()), c_btn("GT 🩵", "setipl_B_GT", color=next_random_color()), c_btn("DC 💙", "setipl_B_DC", color=next_random_color()), c_btn("PBKS ❤️", "setipl_B_PBKS", color=next_random_color()), c_btn("LSG 🩵", "setipl_B_LSG", color=next_random_color())],
    ]

    if standalone: rows.append([c_btn("✅ Done / Close Menu", callback_data="close_setteam", color="green")])
    else: rows.append([c_btn("🔙 Back to Match Lobby", callback_data="back_to_lobby", color="green")])
    return InlineKeyboardMarkup(rows)


def get_numbers_kb(prefix: str) -> InlineKeyboardMarkup:
    """FEATURE 1: 0-6 Numbers with 0 for Dot Ball"""
    return InlineKeyboardMarkup([
        [c_btn("0️⃣ (Dot Ball / Defend)", callback_data=f"{prefix}_0", color="red")],
        [c_btn("1️⃣", callback_data=f"{prefix}_1", color=next_random_color()), c_btn("2️⃣", callback_data=f"{prefix}_2", color=next_random_color()), c_btn("3️⃣", callback_data=f"{prefix}_3", color=next_random_color())],
        [c_btn("4️⃣ FOUR", callback_data=f"{prefix}_4", color=next_random_color()), c_btn("5️⃣", callback_data=f"{prefix}_5", color=next_random_color()), c_btn("6️⃣ SIX", callback_data=f"{prefix}_6", color=next_random_color())],
    ])


def get_host_player_select_kb(match: dict, need_bat: bool, need_bowl: bool) -> InlineKeyboardMarkup:
    """FEATURE 3: Host Player Selection Keyboard (For DM)"""
    rows = []
    bat_team = match[match["bat_team"]]
    bowl_team = match[match["bowl_team"]]

    if need_bat:
        avail_bat = {uid: name for uid, name in bat_team["players"].items() if uid not in match["out_players"]}
        rows.append([c_btn(f"👇 Select Next Striker ({bat_team['name']}) 👇", callback_data="noop", color="blue")])
        for uid, name in avail_bat.items():
            rows.append([c_btn(f"🏏 {name}", callback_data=f"hostsel_bat_{uid}", color=next_random_color())])

    if need_bowl:
        rows.append([c_btn(f"👇 Select Next Bowler ({bowl_team['name']}) 👇", callback_data="noop", color="red")])
        for uid, name in bowl_team["players"].items():
            rows.append([c_btn(f"🎳 {name}", callback_data=f"hostsel_bowl_{uid}", color=next_random_color())])

    return InlineKeyboardMarkup(rows)


def get_toss_kb() -> InlineKeyboardMarkup:
    c1, c2 = random.sample(_COLOR_CYCLE, 2)
    return InlineKeyboardMarkup([[c_btn("🪙 Heads", callback_data="toss_Heads", color=c1), c_btn("🪙 Tails", callback_data="toss_Tails", color=c2)]])

def get_toss_decision_kb() -> InlineKeyboardMarkup:
    c1, c2 = random.sample(_COLOR_CYCLE, 2)
    return InlineKeyboardMarkup([[c_btn("🏏 Batting", callback_data="decide_bat", color=c1), c_btn("🎳 Bowling", callback_data="decide_bowl", color=c2)]])


# ================= HELPER FUNCTIONS =================
async def get_bot_username(client: Client) -> str:
    global BOT_USERNAME
    if not BOT_USERNAME:
        me = await client.get_me()
        BOT_USERNAME = me.username
    return BOT_USERNAME

def format_lobby_text(match: dict) -> str:
    team_a = match["team_A"]["players"]
    team_b = match["team_B"]["players"]
    a_list = "\n".join([f"  {i+1}. {mention(uid, name)}" for i, (uid, name) in enumerate(team_a.items())]) or "  *Empty*"
    b_list = "\n".join([f"  {i+1}. {mention(uid, name)}" for i, (uid, name) in enumerate(team_b.items())]) or "  *Empty*"

    return (
        f"🏏 **{match.get('overs_limit', 6)}-OVER IPL MULTIPLAYER CRICKET LOBBY**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Match Host:** {mention(match['host'], match['host_name'])}\n\n"
        f"🛡️ **{match['team_A']['name']} ({len(team_a)}):**\n{a_list}\n\n"
        f"⚔️ **{match['team_B']['name']} ({len(team_b)}):**\n{b_list}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "• **Min Players:** 2 vs 2 (Max Unlimited)\n"
        f"• **Format:** {match.get('overs_limit', 6)} Overs ({match.get('max_balls', 36)} Balls)\n"
        "• **Custom IPL Names:** Host can click *'Choose IPL Team Names'*!\n"
        "⚠ *Note: Every player must click 'Activate Bot DM' and press `/start`!*"
    )

def format_ipl_menu_text(match: dict) -> str:
    return (
        "✏️ **SELECT CUSTOM IPL TEAM NAMES**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ **Team 1:** `{match['team_A']['name']}`\n⚔️ **Team 2:** `{match['team_B']['name']}`\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "👇 *Match Host, click an IPL franchise below to rename your team!*"
    )

def init_player_stats(match: dict, uid: int, name: str):
    if uid not in match["stats"]:
        match["stats"][uid] = {"id": uid, "name": name, "runs": 0, "balls_faced": 0, "fours": 0, "sixes": 0, "wickets": 0, "runs_conceded": 0, "balls_bowled": 0}

def cleanup_match(chat_id: int):
    m = matches.get(chat_id)
    if m: host_active_matches.pop(m["host"], None)
    for b_id, c_id in list(active_bowlers.items()):
        if c_id == chat_id: active_bowlers.pop(b_id, None)
    matches.pop(chat_id, None)


# ================= BOT COMMANDS & OWNER-ONLY GIF MANAGER =================
@app.on_message(filters.command("start") & filters.private)
async def start_private(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[c_btn("🎨 Test Dynamic Color!", callback_data="dm_color_test", color=next_random_color())]])
    owner_note = "\n\n👑 **Owner Mode Active:** Send any GIF here in DM to set custom **SIX, FOUR, WICKET, or WIN** GIFs!" if message.from_user.id == OWNER_ID else ""
    await message.reply(
        f"👋 **Hello {mention(message.from_user.id, message.from_user.first_name)}!**\n\n"
        "✅ **Your Bot DM is now Activated!**\n• Join Multiplayer Cricket Matches in your group.\n"
        "• When it's your turn to bowl, you will receive the **0-6 Colored Delivery Buttons** right here."
        f"{owner_note}", reply_markup=kb
    )


@app.on_message(filters.animation & filters.private)
async def handle_custom_gif_upload(client: Client, message: Message):
    if message.from_user.id != OWNER_ID: return await message.reply("❌ **Access Denied!** Only the Bot Owner can set or modify custom match GIFs.")
    fid = message.animation.file_id
    pending_gif_save[message.from_user.id] = fid
    kb = InlineKeyboardMarkup([
        [c_btn("🟢 Save as SIX (6) GIF", callback_data="savegif_6", color="green"), c_btn("💥 Save as WICKET GIF", callback_data="savegif_WICKET", color="red")],
        [c_btn("🔵 Save as FOUR (4) GIF", callback_data="savegif_4", color="blue"), c_btn("🏆 Save as WIN GIF", callback_data="savegif_WIN", color=next_random_color())],
        [c_btn("🗑️ Clear All Saved GIFs", callback_data="savegif_CLEAR", color="red")]
    ])
    await message.reply("🎬 **Owner GIF Manager:**\nWhere should this GIF be used during live matches?", reply_markup=kb)


@app.on_callback_query(filters.regex(r"^savegif_(6|4|WICKET|WIN|CLEAR)$"))
async def handle_save_gif_callback(client: Client, cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID: return await safe_answer(cq, "❌ Only the Bot Owner can do this!", show_alert=True)
    uid = cq.from_user.id
    choice = cq.data.split("_")[1]
    if choice == "CLEAR":
        for k in CUSTOM_GIFS: CUSTOM_GIFS[k].clear()
        await safe_answer(cq, "🗑️ Cleared all custom GIFs!", show_alert=True)
        return await safe_edit(cq.message, "🗑️ **All custom GIFs cleared! Bot will now use Live Tenor Cricket GIFs.**")
    fid = pending_gif_save.get(uid)
    if not fid: return await safe_answer(cq, "⚠️ Please send the GIF again!", show_alert=True)
    key = int(choice) if choice in ["4", "6"] else choice
    CUSTOM_GIFS[key].append(fid)
    done_kb = InlineKeyboardMarkup([[c_btn(f"✅ Saved for {choice} (Total: {len(CUSTOM_GIFS[key])})", callback_data="noop", color=next_random_color())]])
    await safe_answer(cq, f"✅ Saved as {choice} GIF!", show_alert=True)
    await safe_edit(cq.message, f"✅ **Success!** This GIF will now appear whenever a **{choice}** happens in the match!", reply_markup=done_kb)


@app.on_callback_query(filters.regex(r"^dm_color_test$"))
async def test_dm_color_change(client: Client, cq: CallbackQuery):
    new_color = next_random_color()
    kb = InlineKeyboardMarkup([[c_btn(f"🎨 Color Changed! ({new_color.upper()}) - Click Again", callback_data="dm_color_test", color=new_color)]])
    await safe_answer(cq, f"Button color shifted to {new_color.upper()}!")
    await safe_edit(cq.message, cq.message.text.markdown, reply_markup=kb)


@app.on_message(filters.command("help") & (filters.group | filters.private))
async def help_command(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[c_btn("🎨 Click to Shift Color", callback_data="noop", color=next_random_color())]])
    await message.reply(
        "🏏 **HOW TO PLAY IPL MULTIPLAYER CRICKET**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ **Start Match:** Send `/cricket` in a group to open the Lobby.\n"
        "2️⃣ **Join Teams:** Minimum **2 players per team** (Unlimited Max). All players must start the bot in DM first.\n"
        "3️⃣ **Custom IPL Team Names:** Host can use `/setteam` or click **'Choose IPL Team Names'**.\n"
        "4️⃣ **Host Controls:** Only the user who started the game (`/cricket`) can **Start/End** the match and **Select Players**.\n"
        "5️⃣ **Bowling (DM):** The Bowler secretly selects a number (`0-6`) inside the **Bot's Private DM**.\n"
        "6️⃣ **Batting (Group):** Once bowled, the Striker selects a shot (`0-6`) inside the **Group Chat**.\n"
        "   • **Same Number** = 💥 **OUT (Wicket + GIF!)**\n"
        "   • **Different Number** = 🏏 **Runs Scored (4 & 6 trigger GIFs!)**\n"
        "7️⃣ **Winner Scorecard Poster:** At the end of the match, an HD Winner Scorecard Image is auto-generated!\n"
        "8️⃣ **Commands:** `/cricket`, `/setteam`, `/score`, `/endcricket`, `/help`", reply_markup=kb
    )


@app.on_message(filters.command("cricket") & filters.group)
async def create_lobby(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in matches:
        m = matches[chat_id]
        return await message.reply(f"⚠️ **A match is already active in this group!**\n👑 Only the Match Host ({mention(m['host'], m['host_name'])}) can end it using `/endcricket`.")

    matches[chat_id] = {"host": message.from_user.id, "host_name": message.from_user.first_name, "status": "SELECT_OVERS"}
    await message.reply(f"👑 **Match Host: {message.from_user.first_name}**\n\n👉 **Host**, please select the number of overs for this match to open the lobby:", reply_markup=get_overs_kb())


@app.on_callback_query(filters.regex(r"^setovers_(\d+)$"))
async def setup_lobby_after_overs(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)
    if not match or match.get("status") != "SELECT_OVERS": return await safe_answer(cq, "⚠️ Session Expired!", show_alert=True)
    if cq.from_user.id != match["host"]: return await safe_answer(cq, "❌ Only the Match Host can select overs!", show_alert=True)

    overs = int(cq.data.split("_")[1])
    match.update({
        "status": "LOBBY", "overs_limit": overs, "max_balls": overs * 6, "innings": 1, "target": None, "max_wickets": 2,
        "team_A": {"name": "Team A 🔵", "players": {}, "score": 0, "wickets": 0, "balls": 0},
        "team_B": {"name": "Team B 🔴", "players": {}, "score": 0, "wickets": 0, "balls": 0},
        "bat_team": None, "bowl_team": None, "striker": None, "bowler": None,
        "out_players": [], "all_out_history": set(), "current_ball": None, "state": None, "stats": {}, "lobby_msg_id": None,
    })

    host_active_matches[cq.from_user.id] = chat_id  # Save reference for Host DM selection
    b_uname = await get_bot_username(client)
    await safe_answer(cq, f"✅ Selected {overs} Overs!")
    sent = await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
    if isinstance(sent, Message): match["lobby_msg_id"] = sent.id


@app.on_message(filters.command("setteam") & filters.group)
async def setteam_command(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match: return await message.reply("❌ **No active match lobby found!** Send `/cricket` first.")
    if match["status"] != "LOBBY": return await message.reply("⚠️ **Team names can only be changed while in the Match Lobby!**")
    if message.from_user.id != match["host"]: return await message.reply("❌ **Only the Match Host can change IPL team names!**")
    await message.reply(format_ipl_menu_text(match), reply_markup=get_ipl_team_selection_kb(match, standalone=True))


@app.on_message(filters.command("endcricket") & filters.group)
async def force_end_match(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match: return await message.reply("❌ **There is no active match in this group!**")
    if message.from_user.id != match["host"]: return await message.reply(f"❌ **Access Denied!**\nOnly the Match Host ({mention(match['host'], match['host_name'])}) can end this match!")
    cleanup_match(chat_id)
    await message.reply(f"🛑 **Match has been ended by the Host ({mention(message.from_user.id, message.from_user.first_name)})!**")


@app.on_message(filters.command("score") & filters.group)
async def show_scorecard(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE": return await message.reply("❌ **No live match is currently in progress!**")

    bat = match[match["bat_team"]]
    bowl = match[match["bowl_team"]]
    overs = f"{bat['balls']//6}.{bat['balls']%6}"
    striker_id = match.get("striker")
    bowler_id = match.get("bowler")
    
    striker_mention = mention(striker_id, bat["players"].get(striker_id, "Striker")) if striker_id else "N/A"
    bowler_mention = mention(bowler_id, bowl["players"].get(bowler_id, "Bowler")) if bowler_id else "N/A"

    s_stat = match["stats"].get(striker_id, {"runs": 0, "balls_faced": 0})
    b_stat = match["stats"].get(bowler_id, {"wickets": 0, "runs_conceded": 0, "balls_bowled": 0})

    text = (
        f"📊 **LIVE SCORECARD (Innings {match['innings']})**\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Host:** {mention(match['host'], match['host_name'])}\n"
        f"🏏 **{bat['name']}:** `{bat['score']}/{bat['wickets']}` ({overs} / {match.get('overs_limit', 6)}.0 Overs)\n"
        f"🎯 **Target:** `{match['target'] or '1st Innings'}` | **Max Wickets:** `{match['max_wickets']}`\n\n"
        f"👤 **Striker:** {striker_mention} — `{s_stat['runs']}* ({s_stat['balls_faced']})`\n"
        f"🎳 **Bowler:** {bowler_mention} — `{b_stat['wickets']}-{b_stat['runs_conceded']} ({b_stat['balls_bowled']//6}.{b_stat['balls_bowled']%6})`\n━━━━━━━━━━━━━━━━━━━━━━"
    )
    await message.reply(text, reply_markup=InlineKeyboardMarkup([[c_btn("📊 Live Scoreboard", callback_data="noop", color=next_random_color())]]))


# ================= IPL TEAM NAME SELECTION CALLBACKS =================
@app.on_callback_query(filters.regex(r"^(open_ipl_menu|back_to_lobby|close_setteam|setipl_(A|B)_([A-Z]+))$"))
async def handle_ipl_team_callbacks(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    user = cq.from_user
    match = matches.get(chat_id)

    if not match or match["status"] != "LOBBY": return await safe_answer(cq, "⚠ Lobby is closed or match already started!", show_alert=True)
    if cq.data != "back_to_lobby" and user.id != match["host"]: return await safe_answer(cq, "❌ Only the Match Host can change IPL Team names!", show_alert=True)

    data = cq.data
    b_uname = await get_bot_username(client)

    if data == "open_ipl_menu":
        await safe_answer(cq, "✏️ Select IPL Team Names!")
        return await safe_edit(cq.message, format_ipl_menu_text(match), reply_markup=get_ipl_team_selection_kb(match, standalone=False))

    elif data == "back_to_lobby":
        await safe_answer(cq, "🔙 Back to Lobby!")
        return await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))

    elif data == "close_setteam":
        await safe_answer(cq, "✅ Closed team selection menu!")
        try: await cq.message.delete()
        except Exception: pass
        return

    _, team_letter, ipl_code = data.split("_")
    target_key = "team_A" if team_letter == "A" else "team_B"
    other_key = "team_B" if team_letter == "A" else "team_A"

    new_ipl_name = IPL_TEAMS.get(ipl_code, f"{ipl_code} 🏏")

    if match[other_key]["name"] == new_ipl_name: return await safe_answer(cq, f"⚠️ {new_ipl_name} is already taken by the opponent team! Pick another franchise.", show_alert=True)

    match[target_key]["name"] = new_ipl_name
    await safe_answer(cq, f"✅ Team {team_letter} renamed to {new_ipl_name}!", show_alert=False)

    is_standalone = (cq.message.id != match.get("lobby_msg_id") and match.get("lobby_msg_id") is not None)
    await safe_edit(cq.message, format_ipl_menu_text(match), reply_markup=get_ipl_team_selection_kb(match, standalone=is_standalone))

    if is_standalone and match.get("lobby_msg_id"):
        try: await client.edit_message_text(chat_id=chat_id, message_id=match["lobby_msg_id"], text=format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
        except Exception: pass


# ================= LOBBY & TOSS HANDLERS =================
@app.on_callback_query(filters.regex(r"^(join_A|join_B|refresh_lobby|leave_lobby|start_game|cancel_game)$"))
async def handle_lobby_buttons(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    user = cq.from_user
    match = matches.get(chat_id)

    if not match or match["status"] != "LOBBY": return await safe_answer(cq, "⚠️ This Lobby is already closed!", show_alert=True)

    data = cq.data
    b_uname = await get_bot_username(client)

    if data == "refresh_lobby":
        await safe_answer(cq, "🎨 Button colors shifted!")
        return await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))

    elif data in ["join_A", "join_B"]:
        try: await client.send_chat_action(user.id, enums.ChatAction.TYPING)
        except Exception: return await safe_answer(cq, "❌ Please click 'Activate Bot DM' below and press /start first!", show_alert=True)

        match["team_A"]["players"].pop(user.id, None)
        match["team_B"]["players"].pop(user.id, None)

        t_key = "team_A" if data == "join_A" else "team_B"
        match[t_key]["players"][user.id] = user.first_name
        init_player_stats(match, user.id, user.first_name)

        await safe_answer(cq, f"✅ You joined {match[t_key]['name']}!")
        await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))

    elif data == "leave_lobby":
        rem_a = match["team_A"]["players"].pop(user.id, None)
        rem_b = match["team_B"]["players"].pop(user.id, None)
        if rem_a or rem_b:
            await safe_answer(cq, "👋 You left the lobby!")
            await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
        else: await safe_answer(cq, "⚠️ You have not joined any team yet!", show_alert=True)

    elif data == "cancel_game":
        if user.id != match["host"]: return await safe_answer(cq, f"❌ Only the Match Host ({match['host_name']}) can cancel the game!", show_alert=True)
        cleanup_match(chat_id)
        await safe_answer(cq, "🛑 Lobby Cancelled!")
        await safe_edit(cq.message, f"🛑 **Match Lobby was cancelled by the Host ({mention(user.id, user.first_name)}).**")

    elif data == "start_game":
        if user.id != match["host"]: return await safe_answer(cq, f"❌ Only the Match Host ({match['host_name']}) can start the match!", show_alert=True)
        if len(match["team_A"]["players"]) < 2 or len(match["team_B"]["players"]) < 2: return await safe_answer(cq, "❌ Minimum 2 players per team required! (At least 2 vs 2)", show_alert=True)

        match["status"] = "TOSS"
        match["max_wickets"] = min(len(match["team_A"]["players"]), len(match["team_B"]["players"]))
        cap_a_id = list(match["team_A"]["players"].keys())[0]
        cap_a_name = match["team_A"]["players"][cap_a_id]
        match["toss_caller"] = cap_a_id

        await safe_answer(cq, "🪙 Time for the Toss!")
        await safe_edit(cq.message, f"🪙 **TIME FOR THE TOSS!**\n⚔️ **{match['team_A']['name']}** vs **{match['team_B']['name']}**\n\n🧢 **{match['team_A']['name']} Player ({mention(cap_a_id, cap_a_name)})**, please call Heads or Tails:", reply_markup=get_toss_kb())


@app.on_callback_query(filters.regex(r"^toss_(Heads|Tails)$"))
async def handle_toss_call(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "TOSS": return await safe_answer(cq, "⚠️ The toss is already over!", show_alert=True)
    if cq.from_user.id != match["toss_caller"]: return await safe_answer(cq, f"❌ Only the designated player can call the toss!", show_alert=True)

    call = cq.data.split("_")[1]
    result = random.choice(["Heads", "Tails"])

    cap_a_id = list(match["team_A"]["players"].keys())[0]
    cap_b_id = list(match["team_B"]["players"].keys())[0]

    if call == result:
        match["toss_winner_team"] = "team_A"
        match["toss_winner_cap"] = cap_a_id
        winner_name = match["team_A"]["name"]
        cap_mention = mention(cap_a_id, match["team_A"]["players"][cap_a_id])
    else:
        match["toss_winner_team"] = "team_B"
        match["toss_winner_cap"] = cap_b_id
        winner_name = match["team_B"]["name"]
        cap_mention = mention(cap_b_id, match["team_B"]["players"][cap_b_id])

    await safe_answer(cq, f"Toss Result: {result}!")
    await safe_edit(cq.message, f"🪙 **Toss Coin Landed On:** `{result}`!\n🎉 **{winner_name}** won the toss!\n\n👑 {cap_mention}, choose whether to Bat or Bowl first:", reply_markup=get_toss_decision_kb())


@app.on_callback_query(filters.regex(r"^decide_(bat|bowl)$"))
async def handle_toss_decision(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "TOSS": return await safe_answer(cq, "⚠️ Decision has already been made!", show_alert=True)
    if cq.from_user.id != match["toss_winner_cap"]: return await safe_answer(cq, "❌ Only the Toss-Winning side can make this choice!", show_alert=True)

    choice = cq.data.split("_")[1]
    win_team = match["toss_winner_team"]
    lose_team = "team_B" if win_team == "team_A" else "team_A"

    if choice == "bat":
        match["bat_team"] = win_team
        match["bowl_team"] = lose_team
    else:
        match["bat_team"] = lose_team
        match["bowl_team"] = win_team

    match["status"] = "LIVE"
    bat_dict = match[match["bat_team"]]
    bowl_dict = match[match["bowl_team"]]
    
    match["striker"] = None
    match["bowler"] = None

    await safe_answer(cq, "🔥 Match Started!")
    await safe_edit(
        cq.message,
        f"🔥 **MATCH STARTED! ({match.get('overs_limit', 6)} Overs | Max Wickets: {match['max_wickets']})**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Match Host:** {mention(match['host'], match['host_name'])}\n"
        f"🏏 **Batting:** {bat_dict['name']}\n"
        f"🎳 **Bowling:** {bowl_dict['name']}\n"
    )

    await prompt_host_player_selection(client, chat_id, need_bat=True, need_bowl=True)


# ================= HOST SELECTS PLAYERS IN DM =================
async def prompt_host_player_selection(client: Client, chat_id: int, need_bat: bool, need_bowl: bool):
    """FEATURE 3: Triggers Host Selection UI IN HOST'S DM"""
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE": return
    match["state"] = "HOST_SELECTING"

    host_id = match["host"]
    kb = get_host_player_select_kb(match, need_bat, need_bowl)
    b_uname = await get_bot_username(client)

    # 1. Notify Group Chat
    dm_btn = InlineKeyboardMarkup([[c_btn("👑 Host: Go to DM to Select", url=f"https://t.me/{b_uname}")]])
    await client.send_message(
        chat_id, 
        f"⏳ **Match Host ({match['host_name']}) is assigning the active players in the Bot DM...**",
        reply_markup=dm_btn
    )

    # 2. Send Selection Keyboard to Host's Private DM
    try:
        await client.send_message(
            host_id,
            f"👑 **Match:** {match['team_A']['name']} vs {match['team_B']['name']}\n👉 Please assign the active players for this phase!",
            reply_markup=kb
        )
    except RPCError:
        await client.send_message(chat_id, f"⚠️ {mention(host_id, match['host_name'])} hasn't started the Bot DM! Please start the bot.")


@app.on_callback_query(filters.regex(r"^hostsel_(bat|bowl)_(\d+)$"))
async def handle_host_selection(client: Client, cq: CallbackQuery):
    host_id = cq.from_user.id
    chat_id = host_active_matches.get(host_id)
    
    match = matches.get(chat_id) if chat_id else None
    if not match or match.get("state") != "HOST_SELECTING":
        return await safe_answer(cq, "⚠️ No active selection needed!", show_alert=True)
    
    if host_id != match["host"]:
        return await safe_answer(cq, "❌ Only the Match Host can select active players!", show_alert=True)
        
    role = cq.data.split("_")[1]
    uid = int(cq.data.split("_")[2])
    
    if role == "bat":
        match["striker"] = uid
        await safe_answer(cq, "🏏 Striker Assigned!")
    else:
        match["bowler"] = uid
        await safe_answer(cq, "🎳 Bowler Assigned!")
        
    need_bat = match["striker"] is None
    need_bowl = match["bowler"] is None
    
    if need_bat or need_bowl:
        kb = get_host_player_select_kb(match, need_bat, need_bowl)
        await safe_edit(cq.message, cq.message.text.markdown, reply_markup=kb)
    else:
        # Finished selecting both
        await safe_edit(cq.message, "✅ **Players Assigned Successfully!**\n👉 Head back to the group.")
        
        # Notify Group and Start Delivery
        await client.send_message(chat_id, "✅ **Host has assigned the players!**")
        await prompt_bowler_dm(client, chat_id)


# ================= GAMEPLAY: DM BOWLING & GROUP BATTING =================
async def prompt_bowler_dm(client: Client, chat_id: int):
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE": return

    bowler_id = match["bowler"]
    striker_id = match["striker"]
    bat_dict = match[match["bat_team"]]
    bowl_dict = match[match["bowl_team"]]

    bowler_name = bowl_dict["players"][bowler_id]
    striker_name = bat_dict["players"][striker_id]

    bowler_m = mention(bowler_id, bowler_name)
    striker_m = mention(striker_id, striker_name)

    over_num = f"{bat_dict['balls']//6}.{bat_dict['balls']%6 + 1}"
    match["state"] = "WAIT_BOWLER"
    active_bowlers[bowler_id] = chat_id

    b_uname = await get_bot_username(client)
    dm_btn = InlineKeyboardMarkup([[
        c_btn(
            "🎳 Go to Bot DM (Bowler)",
            url=f"https://t.me/{b_uname}",
            color=next_random_color(),
        )
    ]])

    await client.send_message(
        chat_id,
        f"⏳ **Delivery {over_num}** ({bat_dict['name']} vs {bowl_dict['name']})\n"
        f"🏏 **Striker:** {striker_m}\n"
        f"🎳 **Bowler:** {bowler_m} is selecting a delivery in the Bot's DM...",
        reply_markup=dm_btn,
    )

    try:
        await client.send_message(
            bowler_id,
            f"🎳 **YOUR TURN TO BOWL! (Ball {over_num})**\n"
            f"🏟️ **Match:** {bat_dict['name']} vs {bowl_dict['name']}\n"
            f"👤 **Facing Striker:** {striker_m}\n"
            f"🎨 *Select your secret delivery number (0 to 6):*",
            reply_markup=get_numbers_kb("bowl"),
        )
    except RPCError:
        await client.send_message(
            chat_id,
            f"⚠️ {bowler_m} has blocked or not started the Bot DM! Please open @{b_uname} and send `/start`.",
        )


@app.on_callback_query(filters.regex(r"^bowl_([0-6])$"))
async def handle_bowler_dm(client: Client, cq: CallbackQuery):
    bowler_id = cq.from_user.id
    if bowler_id not in active_bowlers:
        return await safe_answer(cq, "⚠️ It is not your turn to bowl right now!", show_alert=True)

    chat_id = active_bowlers.pop(bowler_id)
    match = matches.get(chat_id)
    if not match or match["state"] != "WAIT_BOWLER":
        return await safe_answer(cq, "⚠️ This delivery has already expired!", show_alert=True)

    ball_val = int(cq.data.split("_")[1])
    match["current_ball"] = ball_val
    match["state"] = "WAIT_BATSMAN"

    done_kb = InlineKeyboardMarkup([[
        c_btn(
            f"✅ Delivered Ball: {ball_val}",
            callback_data="noop",
            color=next_random_color(),
        )
    ]])
    await safe_answer(cq, f"🎳 You bowled {ball_val}!")
    await safe_edit(
        cq.message,
        f"✅ **Ball Delivered!** You bowled `{ball_val}`.\n👉 Head back to the Group to see the Batsman's shot!",
        reply_markup=done_kb,
    )

    bat_dict = match[match["bat_team"]]
    bowl_dict = match[match["bowl_team"]]
    striker_id = match["striker"]
    striker_m = mention(striker_id, bat_dict["players"][striker_id])
    bowler_m = mention(bowler_id, bowl_dict["players"][bowler_id])
    over_num = f"{bat_dict['balls']//6}.{bat_dict['balls']%6 + 1}"

    await client.send_message(
        chat_id,
        f"🏏 **Delivery {over_num} is Ready!** (Bowled by {bowler_m})\n"
        f"🔥 {striker_m}, play your shot right here in the Group (0-6):",
        reply_markup=get_numbers_kb("bat"),
    )


@app.on_callback_query(filters.regex(r"^bat_([0-6])$"))
async def handle_batsman_group(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "WAIT_BATSMAN": return await safe_answer(cq, "⚠️ This ball has already been played!", show_alert=True)
    if cq.from_user.id != match["striker"]: return await safe_answer(cq, "❌ You are not the current Striker!", show_alert=True)

    match["state"] = "PROCESSING"

    bat_val = int(cq.data.split("_")[1])
    bowl_val = match["current_ball"]
    bat_dict = match[match["bat_team"]]
    bowl_dict = match[match["bowl_team"]]

    striker_id = match["striker"]
    bowler_id = match["bowler"]
    striker_name = bat_dict["players"][striker_id]
    bowler_name = bowl_dict["players"][bowler_id]

    striker_m = mention(striker_id, striker_name)
    bowler_m = mention(bowler_id, bowler_name)

    bat_dict["balls"] += 1
    match["stats"][striker_id]["balls_faced"] += 1
    match["stats"][bowler_id]["balls_bowled"] += 1

    overs_str = f"{bat_dict['balls']//6}.{bat_dict['balls']%6}"
    
    # 0 == 0 Wicket Logic Check
    is_wicket = bat_val == bowl_val

    if is_wicket:
        bat_dict["wickets"] += 1
        match["out_players"].append(striker_id)
        match["all_out_history"].add(striker_id)
        match["stats"][bowler_id]["wickets"] += 1
        s_runs = match["stats"][striker_id]["runs"]
        s_balls = match["stats"][striker_id]["balls_faced"]

        await safe_answer(cq, "💥 OUT! Wicket!", show_alert=True)
        action_header = (
            f"💥 **HOWZAT!! WICKET!** ☝️\n"
            f"🎳 **Bowler ({bowler_m}):** `{bowl_val}` | 🏏 **Batsman ({striker_m}):** `{bat_val}`\n"
            f"🚶 {striker_m} departs for `{s_runs} ({s_balls})`!"
        )
        badge_btn = c_btn(f"💥 WICKET! ({bowl_val} == {bat_val})", callback_data="noop", color="red")

        gif_caption = f"💥 **WICKET!! ({bat_dict['name']})** ☝️\n🎳 {bowler_m} dismisses 🏏 {striker_m} for `{s_runs} ({s_balls})`!"
        asyncio.create_task(send_event_gif(client, chat_id, "WICKET", gif_caption))
    else:
        bat_dict["score"] += bat_val
        match["stats"][striker_id]["runs"] += bat_val
        match["stats"][bowler_id]["runs_conceded"] += bat_val
        s_runs = match["stats"][striker_id]["runs"]
        s_balls = match["stats"][striker_id]["balls_faced"]

        if bat_val == 0:
            shot_tag = "🛡️ **DEFENDED! DOT BALL!**"
        elif bat_val == 4:
            match["stats"][striker_id]["fours"] += 1
            shot_tag = "🔵 **CRACKING FOUR!**"
            gif_caption = f"🔵 **CRACKING FOUR!! ({bat_dict['name']})**\n🏏 {striker_m} smashes `4` runs off 🎳 {bowler_m}! (`{s_runs}*`)"
            asyncio.create_task(send_event_gif(client, chat_id, 4, gif_caption))
        elif bat_val == 6:
            match["stats"][striker_id]["sixes"] += 1
            shot_tag = "🟢 **MASSIVE SIXER!!**"
            gif_caption = f"🟢 **KING KOHLI STYLE SIXER!! ({bat_dict['name']})** 🚀\n🏏 {striker_m} launches `6` runs off 🎳 {bowler_m}! (`{s_runs}*`)"
            asyncio.create_task(send_event_gif(client, chat_id, 6, gif_caption))
        else:
            shot_tag = f"🏃 **{bat_val} RUNS!**"

        await safe_answer(cq, f"🏏 {bat_val} Runs!")
        action_header = f"{shot_tag}\n🎳 **Bowler ({bowler_m}):** `{bowl_val}` | 🏏 **Batsman ({striker_m}):** `{bat_val}`"
        badge_btn = c_btn(f"🏏 +{bat_val} RUNS (Score: {bat_dict['score']}/{bat_dict['wickets']})", callback_data="noop", color=next_random_color())

    target_line = f" | 🎯 **Target:** `{match['target']}`" if match["target"] else ""
    board_footer = (
        f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{bat_dict['name']}:** `{bat_dict['score']}/{bat_dict['wickets']}` ({overs_str} / {match.get('overs_limit', 6)}.0 Overs){target_line}"
    )

    await safe_edit(cq.message, action_header + board_footer, reply_markup=InlineKeyboardMarkup([[badge_btn]]))

    # Check Innings or Match End Conditions
    target_chased = match["target"] is not None and bat_dict["score"] >= match["target"]
    all_out = bat_dict["wickets"] >= match["max_wickets"]
    overs_done = bat_dict["balls"] >= match["max_balls"]

    if target_chased or all_out or overs_done:
        if match["innings"] == 1:
            match["innings"] = 2
            match["target"] = bat_dict["score"] + 1
            match["bat_team"], match["bowl_team"] = match["bowl_team"], match["bat_team"]
            match["out_players"] = []
            match["striker"] = None
            match["bowler"] = None

            await client.send_message(
                chat_id,
                f"🔄 **INNINGS BREAK!**\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏏 **{bat_dict['name']}** finished at `{bat_dict['score']}/{bat_dict['wickets']}`.\n"
                f"🎯 **Target for {match[match['bat_team']]['name']}:** `{match['target']}` runs in {match['max_balls']} balls!\n\n"
            )
            await asyncio.sleep(2)
            return await prompt_host_player_selection(client, chat_id, need_bat=True, need_bowl=True)
        else:
            if target_chased:
                rem_w = match["max_wickets"] - bat_dict["wickets"]
                win_key, lose_key = match["bat_team"], match["bowl_team"]
                result_msg = f"🏆 **{bat_dict['name']} WON BY {rem_w} WICKETS!** 🎉"
                img_banner = f"{bat_dict['name']} WON BY {rem_w} WICKETS!"
            elif bat_dict["score"] == match["target"] - 1:
                win_key, lose_key = "team_A", "team_A"
                result_msg = "🤝 **MATCH TIED! What a thriller!** 🔥"
                img_banner = "MATCH TIED! THRILLING FINISH!"
            else:
                runs_margin = (match["target"] - 1) - bat_dict["score"]
                win_key, lose_key = match["bowl_team"], match["bat_team"]
                result_msg = f"🏆 **{bowl_dict['name']} WON BY {runs_margin} RUNS!** 🎉"
                img_banner = f"{bowl_dict['name']} WON BY {runs_margin} RUNS!"

            summary = build_match_summary(match, result_msg, win_key, lose_key)
            end_kb = InlineKeyboardMarkup([[c_btn("🏆 Match Completed", callback_data="noop", color=next_random_color())]])

            try:
                poster_bio = generate_winner_scorecard_image(match, win_key, lose_key, img_banner)
                cleanup_match(chat_id)
                await client.send_photo(chat_id=chat_id, photo=poster_bio, caption=summary, reply_markup=end_kb)
            except Exception:
                cleanup_match(chat_id)
                await client.send_message(chat_id, summary, reply_markup=end_kb)

            asyncio.create_task(send_event_gif(client, chat_id, "WIN", result_msg, auto_delete=15))
            return

    # Check if Host needs to select next player
    need_bat = is_wicket
    need_bowl = (bat_dict["balls"] % 6 == 0)

    if need_bat or need_bowl:
        if need_bat: 
            match["striker"] = None
        if need_bowl:
            match["bowler"] = None
            await client.send_message(chat_id, f"📣 **End of Over {bat_dict['balls']//6}!**\n")

        await asyncio.sleep(1)
        await prompt_host_player_selection(client, chat_id, need_bat, need_bowl)
    else:
        # Continue with current players
        await asyncio.sleep(1)
        await prompt_bowler_dm(client, chat_id)


def build_match_summary(
    match: dict, result_banner: str, win_key: str, lose_key: str
) -> str:
    tA = match["team_A"]
    tB = match["team_B"]

    if win_key == lose_key:
        win_squad_mentions = "Match Tied!"
    else:
        win_team = match[win_key]
        win_squad_mentions = ", ".join([mention(uid, name) for uid, name in win_team["players"].items()])

    stats_list = list(match["stats"].values())
    if stats_list:
        top_bat = max(stats_list, key=lambda x: (x["runs"], -x["balls_faced"]))
        top_bowl = max(stats_list, key=lambda x: (x["wickets"], -x["runs_conceded"]))
        bat_m = mention(top_bat["id"], top_bat["name"])
        bowl_m = mention(top_bowl["id"], top_bowl["name"])
        awards_text = (
            f"⭐ **Best Batsman:** {bat_m} — `{top_bat['runs']} ({top_bat['balls_faced']})`\n"
            f"🔥 **Best Bowler:** {bowl_m} — `{top_bowl['wickets']}-{top_bowl['runs_conceded']}`"
        )
    else:
        awards_text = ""

    return (
        f"🏁 **IPL MATCH COMPLETED!** 🏁\n━━━━━━━━━━━━━━━━━━━━━━\n{result_banner}\n🏅 **Winning Squad:** {win_squad_mentions}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛡️ **{tA['name']}:** `{tA['score']}/{tA['wickets']}` ({tA['balls']//6}.{tA['balls']%6} ov)\n"
        f"⚔️ **{tB['name']}:** `{tB['score']}/{tB['wickets']}` ({tB['balls']//6}.{tB['balls']%6} ov)\n\n{awards_text}"
    )


@app.on_callback_query(filters.regex(r"^noop$"))
async def handle_noop(client: Client, cq: CallbackQuery):
    kb = InlineKeyboardMarkup([[
        c_btn(
            cq.message.reply_markup.inline_keyboard[0][0].text,
            callback_data="noop",
            color=next_random_color(),
        )
    ]])
    await safe_answer(cq, "🎨 Button color changed!")
    await safe_edit(cq.message, cq.message.text.markdown, reply_markup=kb)


if __name__ == "__main__":
    print("🏏 Dynamic Color Kurigram IPL Cricket Bot Starting...")
    app.run()
