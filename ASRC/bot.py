import asyncio
import inspect
import io
import os
import random
import time
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
from motor.motor_asyncio import AsyncIOMotorClient

# ================= CONFIGURATION (HEROKU + LOCAL READY) =================
API_ID = int(os.getenv("API_ID", "12345678"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

LOG_GROUP_ID = int(os.getenv("LOG_GROUP_ID", "-1001234567890"))
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://...")

app = Client(
    "DynamicColorCricketBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# MongoDB Setup
mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client["CricketBot"]
groups_col = db["groups"]

# Global Storage
matches = {}  
active_bowlers = {}  
host_active_matches = {} 
pending_gif_save = {}  
BOT_USERNAME = None  
BOT_ID = None

# ================= PREMIUM EMOJI ENGINE =================
PREMIUM_IDS = [
    6084869030840114492,
    5416028144794617466,
    5465198403573012261,
    5938508592775696902,
    5393194986252542669,
    5469785308386041323,
    5461130232025078672,
    5346089086325130313,
]

def p_emo(idx: int, fallback: str = "⚡") -> str:
    """Returns formatted Premium Emoji tag for messages."""
    eid = PREMIUM_IDS[idx % len(PREMIUM_IDS)]
    return f"<emoji id='{eid}'>{fallback}</emoji>"

# Pre-mapped Premium Emojis for all pages
E1 = p_emo(0, "🏏") # Cricket / Bat / Main Header
E2 = p_emo(1, "👑") # Host / Crown / Winner
E3 = p_emo(2, "🔥") # Six / Action / Live
E4 = p_emo(3, "💥") # Wicket / Out / Alert
E5 = p_emo(4, "🎯") # Bowling / Target / Four
E6 = p_emo(5, "🪙") # Toss / Stats / Shield
E7 = p_emo(6, "⚡") # Timer / Fast / Star
E8 = p_emo(7, "🏆") # Trophy / Success / Done

IPL_TEAMS = {
    "CSK": "CSK 💛", "MI": "MI 💙", "RCB": "RCB ❤️", "KKR": "KKR 💜",
    "SRH": "SRH 🧡", "RR": "RR 🩷", "GT": "GT 🩵", "DC": "DC 💙",
    "PBKS": "PBKS ❤️", "LSG": "LSG 🩵",
}

CUSTOM_GIFS = {"WICKET": [], "HATTRICK": [], 6: [], 4: [], "WIN": []}

TENOR_SEARCH_QUERIES = {
    "WICKET": ["cricket bowled stumps flying", "cricket umpire out finger"],
    "HATTRICK": ["cricket hat trick celebration", "bowler hat trick cricket"],
    6: ["virat kohli six shot cricket", "ms dhoni six cricket"],
    4: ["virat kohli cover drive four", "cricket boundary four shot"],
    "WIN": ["virat kohli winning celebration", "india cricket win celebration"],
}

FALLBACK_CRICKET_GIFS = {
    "WICKET": ["https://files.catbox.moe/gvywua.mp4"],
    "HATTRICK": ["https://files.catbox.moe/gvywua.mp4"], 
    6: ["https://files.catbox.moe/qjb1q0.mp4"],
    4: ["https://files.catbox.moe/ekhicn.mp4"],
    "WIN": ["https://media.tenor.com/f3losXlErrQAAAAM/ms-dhoni-dhoni.gif"],
}

_BTN_PARAMS = inspect.signature(InlineKeyboardButton.__init__).parameters
_COLOR_CYCLE = ["blue", "green", "red"]
_click_counter = 0
_btn_emo_counter = 0


# ================= HELPERS & PREMIUM COLOR BUTTONS =================
async def get_bot_username(client: Client) -> str:
    global BOT_USERNAME, BOT_ID
    if not BOT_USERNAME:
        me = await client.get_me()
        BOT_USERNAME = me.username
        BOT_ID = me.id
    return BOT_USERNAME

def mention(user_id: int, name: str) -> str:
    clean_name = str(name).replace("[", "").replace("]", "").replace("*", "").strip() or "Player"
    return f"[{clean_name}](tg://user?id={user_id})"

def clean_img_text(text: str) -> str:
    cleaned = "".join(c for c in str(text) if ord(c) < 65535 and ord(c) != 65039)
    return "".join(c for c in cleaned if 32 <= ord(c) <= 126).strip() or "Player"

def next_random_color() -> str:
    global _click_counter
    _click_counter += 1
    return random.choice(_COLOR_CYCLE)

def c_btn(text: str, callback_data: str = None, url: str = None, color: str = None, emoji_id: int = None) -> InlineKeyboardButton:
    global _btn_emo_counter
    if color is None:
        color = next_random_color()
    if emoji_id is None:
        emoji_id = PREMIUM_IDS[_btn_emo_counter % len(PREMIUM_IDS)]
        _btn_emo_counter += 1

    kwargs = {"text": text}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url

    # Support Kurigram / Pyrogram Custom Emoji in Inline Button
    if "icon_custom_emoji_id" in _BTN_PARAMS:
        kwargs["icon_custom_emoji_id"] = emoji_id
    elif "custom_emoji_id" in _BTN_PARAMS:
        kwargs["custom_emoji_id"] = emoji_id

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


# ================= GROUP LOGGER & OWNER COMMANDS =================
@app.on_chat_member_updated()
async def log_group_add_remove(client: Client, update):
    await get_bot_username(client)
    if not update.new_chat_member or update.new_chat_member.user.id != BOT_ID:
        return

    chat_id = update.chat.id
    chat_title = update.chat.title or "Unknown Group"
    status = update.new_chat_member.status

    if status in [enums.ChatMemberStatus.MEMBER, enums.ChatMemberStatus.ADMINISTRATOR]:
        await groups_col.update_one({"chat_id": chat_id}, {"$set": {"chat_name": chat_title, "active": True}}, upsert=True)
        try:
            adder = update.from_user.mention if update.from_user else "Unknown User"
            msg = (
                f"{E8} **Bot Added to New Group!**\n━━━━━━━━━━━━━━━\n"
                f"{E1} **Group Name:** `{chat_title}`\n"
                f"{E6} **Group ID:** `{chat_id}`\n"
                f"{E2} **Added By:** {adder}\n"
                f"{E3} **Status:** Active in DB"
            )
            await client.send_message(LOG_GROUP_ID, msg)
        except Exception:
            pass

    elif status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
        await groups_col.update_one({"chat_id": chat_id}, {"$set": {"active": False}})
        try:
            msg = (
                f"{E4} **Bot Removed from Group!**\n━━━━━━━━━━━━━━━\n"
                f"{E1} **Group Name:** `{chat_title}`\n"
                f"{E6} **Group ID:** `{chat_id}`\n"
                f"{E7} **Status:** Marked Inactive in DB"
            )
            await client.send_message(LOG_GROUP_ID, msg)
        except Exception:
            pass

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def bot_stats(client: Client, message: Message):
    active_groups = await groups_col.count_documents({"active": True})
    live_matches = len(matches)
    text = (
        f"{E6} **BOT STATISTICS** {E8}\n━━━━━━━━━━━━━━━\n"
        f"{E2} **Total Active Groups:** `{active_groups}`\n"
        f"{E1} **Live Matches Running:** `{live_matches}`"
    )
    await message.reply(text)

@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast_msg(client: Client, message: Message):
    if len(message.command) < 2 and not message.reply_to_message:
        return await message.reply(f"{E4} Usage: `/broadcast Hello everyone!` or reply to a message with `/broadcast`")
    
    msg_to_send = await message.reply(f"{E7} **Starting Broadcast...**")
    success, failed = 0, 0
    active_groups = await groups_col.find({"active": True}).to_list(length=None)
    
    for grp in active_groups:
        try:
            if message.reply_to_message:
                await message.reply_to_message.copy(grp["chat_id"])
            else:
                text = message.text.split(None, 1)[1]
                await client.send_message(grp["chat_id"], text)
            success += 1
            await asyncio.sleep(0.3) 
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception:
            failed += 1
            await groups_col.update_one({"chat_id": grp["chat_id"]}, {"$set": {"active": False}})

    await msg_to_send.edit_text(
        f"{E8} **Broadcast Completed!**\n"
        f"{E5} **Success:** `{success}` Groups\n"
        f"{E4} **Failed/Removed:** `{failed}` Groups"
    )

@app.on_message(filters.command("sudoend") & filters.user(OWNER_ID))
async def force_end_match_owner(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply(f"{E4} Usage: `/sudoend <chat_id>`")
    try:
        target_chat = int(message.command[1])
        if target_chat in matches:
            cleanup_match(target_chat)
            await client.send_message(target_chat, f"{E4} **This match was Force Cancelled by the Bot Owner!**")
            await message.reply(f"{E8} Match successfully cancelled in `{target_chat}`!")
        else:
            await message.reply(f"{E4} No active match found in that group!")
    except Exception as e:
        await message.reply(f"{E4} Error: {str(e)}")

@app.on_message(filters.command("ping"))
async def ping_command(client: Client, message: Message):
    start_t = time.time()
    msg = await message.reply(f"{E7} Pinging...")
    end_t = time.time()
    await msg.edit_text(f"{E1} **Pong!**\n{E7} **Latency:** `{round((end_t - start_t) * 1000)}ms`")


# ================= HD WINNER SCORECARD ENGINE =================
def load_font(size: int, bold: bool = True):
    font_paths = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "arialbd.ttf"] if bold else ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "arial.ttf"]
    for path in font_paths:
        if os.path.exists(path):
            try: return ImageFont.truetype(path, size)
            except Exception: pass
    try: return ImageFont.load_default(size=size)
    except TypeError: return ImageFont.load_default()

def generate_winner_scorecard_image(match: dict, win_key: str, lose_key: str, banner_text: str) -> io.BytesIO:
    win_team, lose_team = match[win_key], match[lose_key]
    is_tie = win_key == lose_key
    max_players = max(len(win_team["players"]), len(lose_team["players"]), 2)
    width, height = 1100, max(680, 420 + (max_players * 44))

    img = Image.new("RGB", (width, height), color=(11, 15, 25))
    draw = ImageDraw.Draw(img)

    f_header, f_banner, f_team, f_score = load_font(34, True), load_font(28, True), load_font(30, True), load_font(24, True)
    f_sub, f_player, f_award = load_font(20, True), load_font(20, False), load_font(21, True)

    draw.rounded_rectangle([(30, 20), (width - 30, 145)], radius=18, fill=(22, 30, 50), outline=(255, 215, 0), width=3)
    draw.text((width // 2, 55), f"IPL {match.get('overs_limit', 6)}-OVER CHAMPIONSHIP RESULT", fill=(255, 215, 0), font=f_header, anchor="mm")
    draw.text((width // 2, 108), clean_img_text(banner_text).upper(), fill=(80, 255, 140), font=f_banner, anchor="mm")

    box_top, box_bottom = 170, height - 135
    draw.rounded_rectangle([(30, box_top), (535, box_bottom)], radius=16, fill=(14, 38, 28), outline=(46, 213, 115), width=3)
    draw.rounded_rectangle([(565, box_top), (width - 30, box_bottom)], radius=16, fill=(40, 18, 26), outline=(255, 71, 87), width=3)

    def draw_team_panel(t_dict: dict, x_center: int, x_left: int, badge: str, badge_color: tuple):
        overs_s = f"{t_dict['balls']//6}.{t_dict['balls']%6}"
        draw.text((x_center, box_top + 32), badge, fill=badge_color, font=f_sub, anchor="mm")
        draw.text((x_center, box_top + 70), clean_img_text(t_dict["name"]).upper(), fill=(255, 255, 255), font=f_team, anchor="mm")
        draw.text((x_center, box_top + 110), f"SCORE: {t_dict['score']}/{t_dict['wickets']} ({overs_s} / {match.get('overs_limit', 6)}.0 OVERS)", fill=(255, 215, 0), font=f_score, anchor="mm")
        draw.line([(x_left + 20, box_top + 138), (x_left + 485, box_top + 138)], fill=badge_color, width=2)
        draw.text((x_left + 25, box_top + 152), "PLAYER NAME", fill=(180, 200, 220), font=f_sub)
        draw.text((x_left + 310, box_top + 152), "BAT", fill=(180, 200, 220), font=f_sub)
        draw.text((x_left + 405, box_top + 152), "BOWL", fill=(180, 200, 220), font=f_sub)

        y_cursor = box_top + 190
        for idx, (uid, p_name) in enumerate(t_dict["players"].items()):
            st = match["stats"].get(uid, {})
            runs, balls, wkts, runs_c, balls_b = st.get("runs", 0), st.get("balls_faced", 0), st.get("wickets", 0), st.get("runs_conceded", 0), st.get("balls_bowled", 0)
            not_out_star = "*" if (uid not in match.get("all_out_history", set()) and balls > 0) else ""
            draw.text((x_left + 25, y_cursor), f"{idx+1}. {clean_img_text(p_name)[:16]}{' (C)' if idx == 0 else ''}", fill=(240, 245, 255), font=f_player)
            draw.text((x_left + 310, y_cursor), f"{runs}{not_out_star} ({balls})", fill=(120, 255, 170), font=f_player)
            draw.text((x_left + 405, y_cursor), f"{wkts}-{runs_c}" if balls_b > 0 else "-", fill=(130, 210, 255), font=f_player)
            y_cursor += 40

    if is_tie:
        draw_team_panel(match["team_A"], 282, 30, "TEAM 1 (TIED)", (255, 215, 0))
        draw_team_panel(match["team_B"], 817, 565, "TEAM 2 (TIED)", (255, 215, 0))
    else:
        draw_team_panel(win_team, 282, 30, "★ CHAMPIONS ★", (46, 213, 115))
        draw_team_panel(lose_team, 817, 565, "RUNNER-UP", (255, 107, 129))

    draw.rounded_rectangle([(30, height - 115), (width - 30, height - 20)], radius=14, fill=(22, 30, 50), outline=(100, 160, 255), width=2)
    stats_list = list(match["stats"].values())
    if stats_list:
        top_bat = max(stats_list, key=lambda x: (x["runs"], -x["balls_faced"]))
        top_bowl = max(stats_list, key=lambda x: (x["wickets"], -x["runs_conceded"]))
        bat_txt = f"BEST BATSMAN: {clean_img_text(top_bat['name'])} — {top_bat['runs']} Runs ({top_bat['balls_faced']} Balls)"
        bowl_txt = f"BEST BOWLER: {clean_img_text(top_bowl['name'])} — {top_bowl['wickets']} Wickets ({top_bowl['runs_conceded']} Runs)"
    else:
        bat_txt, bowl_txt = "BEST BATSMAN: N/A", "BEST BOWLER: N/A"

    draw.text((width // 2, height - 85), bat_txt, fill=(255, 215, 0), font=f_award, anchor="mm")
    draw.text((width // 2, height - 48), bowl_txt, fill=(120, 220, 255), font=f_award, anchor="mm")

    bio = io.BytesIO()
    bio.name = "ipl_match_winner.png"
    img.save(bio, "PNG")
    bio.seek(0)
    return bio


# ================= GIF ENGINE =================
async def send_event_gif(client: Client, chat_id: int, event_key, caption: str, auto_delete: int = 12):
    kb = InlineKeyboardMarkup([[c_btn("🎬 Match Highlight", callback_data="noop", color=next_random_color(), emoji_id=PREMIUM_IDS[2])]])
    candidates = list(CUSTOM_GIFS.get(event_key, []))
    random.shuffle(candidates)
    if not candidates: candidates.extend(FALLBACK_CRICKET_GIFS.get(event_key, []))

    for anim in candidates:
        try:
            gif_msg = await client.send_animation(chat_id=chat_id, animation=anim, caption=caption, reply_markup=kb)
            if auto_delete > 0:
                await asyncio.sleep(auto_delete)
                try: await gif_msg.delete()
                except Exception: pass
            return
        except Exception: continue


# ================= WRAPPERS & KEYBOARDS =================
async def safe_edit(message: Message, text: str, reply_markup: InlineKeyboardMarkup = None):
    try: return await message.edit_text(text=text, reply_markup=reply_markup)
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

def init_player_stats(match: dict, uid: int, name: str):
    if uid not in match["stats"]:
        match["stats"][uid] = {"id": uid, "name": name, "runs": 0, "balls_faced": 0, "fours": 0, "sixes": 0, "wickets": 0, "runs_conceded": 0, "balls_bowled": 0}

def cleanup_match(chat_id: int):
    m = matches.get(chat_id)
    if m: host_active_matches.pop(m["host"], None)
    for b_id, c_id in list(active_bowlers.items()):
        if c_id == chat_id: active_bowlers.pop(b_id, None)
    matches.pop(chat_id, None)

def get_overs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [c_btn("1 Over", "setovers_1", emoji_id=PREMIUM_IDS[0]), c_btn("2 Overs", "setovers_2", emoji_id=PREMIUM_IDS[1]), c_btn("3 Overs", "setovers_3", emoji_id=PREMIUM_IDS[2])],
        [c_btn("4 Overs", "setovers_4", emoji_id=PREMIUM_IDS[3]), c_btn("5 Overs", "setovers_5", emoji_id=PREMIUM_IDS[4]), c_btn("6 Overs", "setovers_6", emoji_id=PREMIUM_IDS[5])],
        [c_btn("7 Overs", "setovers_7", emoji_id=PREMIUM_IDS[6]), c_btn("8 Overs", "setovers_8", emoji_id=PREMIUM_IDS[7]), c_btn("9 Overs", "setovers_9", emoji_id=PREMIUM_IDS[0])],
        [c_btn("10 OVERS MATCH", "setovers_10", color="blue", emoji_id=PREMIUM_IDS[7])],
    ])

def format_lobby_text(match: dict) -> str:
    team_a = match["team_A"]["players"]
    team_b = match["team_B"]["players"]
    a_list = "\n".join([f"  {i+1}. {mention(uid, name)}" for i, (uid, name) in enumerate(team_a.items())]) or "  *Empty*"
    b_list = "\n".join([f"  {i+1}. {mention(uid, name)}" for i, (uid, name) in enumerate(team_b.items())]) or "  *Empty*"

    return (
        f"{E1} **{match.get('overs_limit', 6)}-OVER IPL MULTIPLAYER CRICKET LOBBY** {E8}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E2} **Match Host:** {mention(match['host'], match['host_name'])}\n\n"
        f"{E6} **{match['team_A']['name']} ({len(team_a)}):**\n{a_list}\n\n"
        f"{E5} **{match['team_B']['name']} ({len(team_b)}):**\n{b_list}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E7} **Min Players:** 1 vs 1 (Max Unlimited)\n"
        f"{E3} **Format:** {match.get('overs_limit', 6)} Overs ({match.get('max_balls', 36)} Balls)\n"
        f"{E2} **Custom IPL Names:** Host can click *'Choose IPL Team Names'* or send `/setteam`!\n"
        f"{E4} *Note: Every player must click 'Activate Bot DM' and press `/start`!*"
    )

def format_ipl_menu_text(match: dict) -> str:
    return (
        f"{E2} **SELECT CUSTOM IPL TEAM NAMES** {E8}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E6} **Team 1:** `{match['team_A']['name']}`\n{E5} **Team 2:** `{match['team_B']['name']}`\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E7} *Match Host, click an IPL franchise below to rename your team!*"
    )

def get_lobby_kb(match: dict, bot_username: str) -> InlineKeyboardMarkup:
    colors = random.sample(_COLOR_CYCLE, 3)
    return InlineKeyboardMarkup([
        [c_btn(f"Join {match['team_A']['name']}", "join_A", color=colors[0], emoji_id=PREMIUM_IDS[0]), c_btn(f"Join {match['team_B']['name']}", "join_B", color=colors[1], emoji_id=PREMIUM_IDS[1])],
        [c_btn("✏️ Choose IPL Team Names", "open_ipl_menu", color=colors[2], emoji_id=PREMIUM_IDS[2])],
        [c_btn("🔄 Refresh Colors", "refresh_lobby", emoji_id=PREMIUM_IDS[3]), c_btn("🚪 Leave Lobby", "leave_lobby", emoji_id=PREMIUM_IDS[4])],
        [c_btn("🤖 Activate Bot DM", url=f"https://t.me/{bot_username}?start=cricket", emoji_id=PREMIUM_IDS[5])],
        [c_btn("🚀 Start Match (Host)", "start_game", color="blue", emoji_id=PREMIUM_IDS[6]), c_btn("✖ End Lobby (Host)", "cancel_game", color="red", emoji_id=PREMIUM_IDS[7])],
    ])

def get_ipl_team_selection_kb(match: dict, standalone: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [c_btn(f"⬇️ Select for {match['team_A']['name']} (Team 1) ⬇️", "noop", color="blue", emoji_id=PREMIUM_IDS[0])],
        [c_btn("CSK 💛", "setipl_A_CSK", emoji_id=PREMIUM_IDS[1]), c_btn("MI 💙", "setipl_A_MI", emoji_id=PREMIUM_IDS[2]), c_btn("RCB ❤️", "setipl_A_RCB", emoji_id=PREMIUM_IDS[3]), c_btn("KKR 💜", "setipl_A_KKR", emoji_id=PREMIUM_IDS[4]), c_btn("SRH 🧡", "setipl_A_SRH", emoji_id=PREMIUM_IDS[5])],
        [c_btn("RR 🩷", "setipl_A_RR", emoji_id=PREMIUM_IDS[6]), c_btn("GT 🩵", "setipl_A_GT", emoji_id=PREMIUM_IDS[7]), c_btn("DC 💙", "setipl_A_DC", emoji_id=PREMIUM_IDS[0]), c_btn("PBKS ❤️", "setipl_A_PBKS", emoji_id=PREMIUM_IDS[1]), c_btn("LSG 🩵", "setipl_A_LSG", emoji_id=PREMIUM_IDS[2])],
        [c_btn(f"⬇️ Select for {match['team_B']['name']} (Team 2) ⬇️", "noop", color="red", emoji_id=PREMIUM_IDS[3])],
        [c_btn("CSK 💛", "setipl_B_CSK", emoji_id=PREMIUM_IDS[4]), c_btn("MI 💙", "setipl_B_MI", emoji_id=PREMIUM_IDS[5]), c_btn("RCB ❤", "setipl_B_RCB", emoji_id=PREMIUM_IDS[6]), c_btn("KKR 💜", "setipl_B_KKR", emoji_id=PREMIUM_IDS[7]), c_btn("SRH 🧡", "setipl_B_SRH", emoji_id=PREMIUM_IDS[0])],
        [c_btn("RR 🩷", "setipl_B_RR", emoji_id=PREMIUM_IDS[1]), c_btn("GT 🩵", "setipl_B_GT", emoji_id=PREMIUM_IDS[2]), c_btn("DC 💙", "setipl_B_DC", emoji_id=PREMIUM_IDS[3]), c_btn("PBKS ❤️", "setipl_B_PBKS", emoji_id=PREMIUM_IDS[4]), c_btn("LSG 🩵", "setipl_B_LSG", emoji_id=PREMIUM_IDS[5])],
    ]
    if standalone: rows.append([c_btn("✅ Done / Close Menu", "close_setteam", color="green", emoji_id=PREMIUM_IDS[7])])
    else: rows.append([c_btn("🔙 Back to Match Lobby", "back_to_lobby", color="green", emoji_id=PREMIUM_IDS[6])])
    return InlineKeyboardMarkup(rows)

def get_bowler_numbers_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [c_btn("1️⃣", f"{prefix}_1", emoji_id=PREMIUM_IDS[0]), c_btn("2️⃣", f"{prefix}_2", emoji_id=PREMIUM_IDS[1]), c_btn("3️⃣", f"{prefix}_3", emoji_id=PREMIUM_IDS[2])],
        [c_btn("4️⃣ FOUR", f"{prefix}_4", color="blue", emoji_id=PREMIUM_IDS[4]), c_btn("5️⃣", f"{prefix}_5", emoji_id=PREMIUM_IDS[5]), c_btn("6️⃣ SIX", f"{prefix}_6", color="green", emoji_id=PREMIUM_IDS[2])],
    ])

def get_batsman_numbers_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [c_btn("0️⃣ (Dot Ball / Defend)", f"{prefix}_0", color="red", emoji_id=PREMIUM_IDS[3])],
        [c_btn("1️⃣", f"{prefix}_1", emoji_id=PREMIUM_IDS[0]), c_btn("2️⃣", f"{prefix}_2", emoji_id=PREMIUM_IDS[1]), c_btn("3️⃣", f"{prefix}_3", emoji_id=PREMIUM_IDS[5])],
        [c_btn("4️⃣ FOUR", f"{prefix}_4", color="blue", emoji_id=PREMIUM_IDS[4]), c_btn("5️⃣", f"{prefix}_5", emoji_id=PREMIUM_IDS[6]), c_btn("6️⃣ SIX", f"{prefix}_6", color="green", emoji_id=PREMIUM_IDS[2])],
    ])

def get_host_player_select_kb(match: dict, need_bat: bool, need_bowl: bool) -> InlineKeyboardMarkup:
    rows, bat_team, bowl_team = [], match[match["bat_team"]], match[match["bowl_team"]]
    if need_bat:
        avail_bat = {uid: name for uid, name in bat_team["players"].items() if uid not in match["out_players"]}
        rows.append([c_btn(f"👇 Select Next Striker ({bat_team['name']}) 👇", "noop", color="blue", emoji_id=PREMIUM_IDS[0])])
        for idx, (uid, name) in enumerate(avail_bat.items()):
            rows.append([c_btn(f"🏏 {name}", f"hostsel_bat_{uid}", emoji_id=PREMIUM_IDS[idx % len(PREMIUM_IDS)])])
    if need_bowl:
        rows.append([c_btn(f"👇 Select Next Bowler ({bowl_team['name']}) 👇", "noop", color="red", emoji_id=PREMIUM_IDS[4])])
        for idx, (uid, name) in enumerate(bowl_team["players"].items()):
            rows.append([c_btn(f"🎳 {name}", f"hostsel_bowl_{uid}", emoji_id=PREMIUM_IDS[(idx + 3) % len(PREMIUM_IDS)])])
    return InlineKeyboardMarkup(rows)

def get_toss_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[c_btn("🪙 Heads", "toss_Heads", emoji_id=PREMIUM_IDS[5]), c_btn("🪙 Tails", "toss_Tails", emoji_id=PREMIUM_IDS[6])]])

def get_toss_decision_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[c_btn("🏏 Batting", "decide_bat", emoji_id=PREMIUM_IDS[0]), c_btn("🎳 Bowling", "decide_bowl", emoji_id=PREMIUM_IDS[4])]])


# ================= TIMERS & MATCH EVALUATION ENGINE =================
async def match_timer_task(client: Client, chat_id: int, state_type: str, turn_id: int):
    """60s Timer Task for Batting and Bowling ONLY. (Host timer removed)."""
    if state_type == "HOST_SELECTING":
        return

    await asyncio.sleep(30)
    match = matches.get(chat_id)
    if not match or match.get("state") != state_type or match.get("turn_id") != turn_id: return
    
    m_name = ""
    if state_type == "WAIT_BOWLER": m_name = mention(match["bowler"], match[match["bowl_team"]]["players"][match["bowler"]])
    elif state_type == "WAIT_BATSMAN": m_name = mention(match["striker"], match[match["bat_team"]]["players"][match["striker"]])
    
    await client.send_message(chat_id, f"{E7} **30 Seconds Remaining!** {m_name}, please make your move fast!")

    await asyncio.sleep(20)
    match = matches.get(chat_id)
    if not match or match.get("state") != state_type or match.get("turn_id") != turn_id: return
    await client.send_message(chat_id, f"{E4} **10 Seconds Left!!** {m_name}, hurry up!")

    await asyncio.sleep(10)
    match = matches.get(chat_id)
    if not match or match.get("state") != state_type or match.get("turn_id") != turn_id: return
    
    match["state"] = "PROCESSING"
    
    if state_type == "WAIT_BOWLER":
        await client.send_message(chat_id, f"{E4} **TIMEOUT!** {m_name} didn't bowl in 60s!\n{E3} **+6 Runs Penalty** given to {match[match['bat_team']]['name']}!")
        bat_dict = match[match["bat_team"]]
        bat_dict["score"] += 6
        bat_dict["balls"] += 1
        match["stats"][match["bowler"]]["runs_conceded"] += 6
        match["stats"][match["bowler"]]["balls_bowled"] += 1
        match["stats"][match["striker"]]["balls_faced"] += 1
        match["consecutive_wickets"] = 0
        await evaluate_and_continue(client, chat_id, match, is_wicket=False)

    elif state_type == "WAIT_BATSMAN":
        await client.send_message(chat_id, f"{E4} **TIMEOUT!** {m_name} took too long!\n{E4} **WICKET (Timed Out)!**")
        bat_dict, bowl_dict = match[match["bat_team"]], match[match["bowl_team"]]
        striker_id, bowler_id = match["striker"], match["bowler"]
        
        bat_dict["wickets"] += 1
        bat_dict["balls"] += 1
        match["out_players"].append(striker_id)
        match["all_out_history"].add(striker_id)
        match["stats"][bowler_id]["wickets"] += 1
        match["stats"][bowler_id]["balls_bowled"] += 1
        match["stats"][striker_id]["balls_faced"] += 1
        match["consecutive_wickets"] += 1
        await evaluate_and_continue(client, chat_id, match, is_wicket=True)


async def evaluate_and_continue(client: Client, chat_id: int, match: dict, is_wicket: bool):
    """Handles end of ball logic, checks for innings break/match over, and routes to next action."""
    bat_dict = match[match["bat_team"]]
    bowl_dict = match[match["bowl_team"]]
    
    target_chased = match["target"] is not None and bat_dict["score"] >= match["target"]
    all_out = bat_dict["wickets"] >= match["max_wickets"]
    overs_done = bat_dict["balls"] >= match["max_balls"]

    if target_chased or all_out or overs_done:
        if match["innings"] == 1:
            match["innings"], match["target"] = 2, bat_dict["score"] + 1
            match["bat_team"], match["bowl_team"] = match["bowl_team"], match["bat_team"]
            match["out_players"], match["striker"], match["bowler"] = [], None, None
            match["consecutive_wickets"] = 0

            await client.send_message(
                chat_id,
                f"{E7} **INNINGS BREAK!** {E7}\n━━━━━━━━━━━━━━━━━━━━━━\n"
                f"{E1} **{bat_dict['name']}** finished at `{bat_dict['score']}/{bat_dict['wickets']}`.\n"
                f"{E5} **Target for {match[match['bat_team']]['name']}:** `{match['target']}` runs in {match['max_balls']} balls!\n\n"
            )
            await asyncio.sleep(2)
            return await prompt_host_player_selection(client, chat_id, need_bat=True, need_bowl=True)
        else:
            if target_chased:
                rem_w = match["max_wickets"] - bat_dict["wickets"]
                win_key, lose_key, result_msg = match["bat_team"], match["bowl_team"], f"{E8} **{bat_dict['name']} WON BY {rem_w} WICKETS!** {E3}"
            elif bat_dict["score"] == match["target"] - 1:
                win_key, lose_key, result_msg = "team_A", "team_A", f"{E6} **MATCH TIED! What a thriller!** {E3}"
            else:
                runs_margin = (match["target"] - 1) - bat_dict["score"]
                win_key, lose_key, result_msg = match["bowl_team"], match["bat_team"], f"{E8} **{bowl_dict['name']} WON BY {runs_margin} RUNS!** {E3}"

            summary = build_match_summary(match, result_msg, win_key, lose_key)
            end_kb = InlineKeyboardMarkup([[c_btn("🏆 Match Completed", "noop", emoji_id=PREMIUM_IDS[7])]])
            try:
                poster_bio = generate_winner_scorecard_image(match, win_key, lose_key, result_msg.replace("*", ""))
                cleanup_match(chat_id)
                await client.send_photo(chat_id, poster_bio, caption=summary, reply_markup=end_kb)
            except Exception:
                cleanup_match(chat_id)
                await client.send_message(chat_id, summary, reply_markup=end_kb)

            asyncio.create_task(send_event_gif(client, chat_id, "WIN", result_msg, auto_delete=15))
            return

    need_bat = is_wicket
    need_bowl = (bat_dict["balls"] % 6 == 0)

    if need_bat or need_bowl:
        if need_bat: match["striker"] = None
        if need_bowl:
            match["bowler"] = None
            await client.send_message(chat_id, f"{E6} **End of Over {bat_dict['balls']//6}!**\n")
        
        await asyncio.sleep(1) 
        await prompt_host_player_selection(client, chat_id, need_bat, need_bowl)
    else:
        await asyncio.sleep(1)
        await prompt_bowler_dm(client, chat_id)


# ================= BOT COMMANDS =================
@app.on_message(filters.command("start") & filters.private)
async def start_private(client: Client, message: Message):
    b_uname = await get_bot_username(client)
    
    kb = InlineKeyboardMarkup([
        [c_btn("➕ Add me to your Group", url=f"https://t.me/{b_uname}?startgroup=true", color="blue", emoji_id=PREMIUM_IDS[0])]
    ])
    owner_note = f"\n\n{E2} **Owner Mode Active:** Send any GIF here in DM to set custom **SIX, FOUR, WICKET, HATTRICK, or WIN** GIFs!" if message.from_user.id == OWNER_ID else ""
    
    explanation = (
        f"{E1} **IPL MULTIPLAYER CRICKET BOT** {E8}\n\n"
        f"{E2} **How it works:**\n"
        f"{E3} First, add this bot to your Telegram group.\n"
        f"{E5} Send `/cricket` in the group. Once the Host selects the Overs, the Lobby opens.\n"
        f"{E6} Anyone in the group can Join. (Note: Everyone must start the bot in their DM first via `/start`).\n"
        f"{E7} Once the match starts, the **Match Host** will select the Batsman & Bowler.\n"
        f"{E5} **Bowling:** The Bowler will receive numbers (1-6) in their Private DM. Select a number secretly.\n"
        f"{E1} **Batting:** The Batsman will receive numbers (0-6) in the Group. The result appears immediately upon selection!\n"
        f"   {E4} *If both select the same number = WICKET!*\n"
        f"   {E3} *If numbers are different = RUNS/DOT BALL!*\n"
    )

    await message.reply(f"{E8} **Hello {mention(message.from_user.id, message.from_user.first_name)}!**\n\n{explanation}{owner_note}", reply_markup=kb)


@app.on_message(filters.command("help") & (filters.group | filters.private))
async def help_command(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[c_btn("🎨 Click to Shift Color", callback_data="noop", color=next_random_color(), emoji_id=PREMIUM_IDS[6])]])
    await message.reply(
        f"{E1} **HOW TO PLAY IPL MULTIPLAYER CRICKET** {E8}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E2} **Start Match:** Send `/cricket` in a group to open the Lobby.\n"
        f"{E6} **Join Teams:** Minimum **1 player per team** (Unlimited Max). All players must start the bot in DM first.\n"
        f"{E3} **Custom IPL Team Names:** Host can use `/setteam` or click **'Choose IPL Team Names'**.\n"
        f"{E2} **Host Controls:** Only the user who started the game (`/cricket`) can **Start/End** the match and **Select Players**.\n"
        f"{E5} **Bowling (DM):** The Bowler secretly selects a number (`1-6`) inside the **Bot's Private DM**.\n"
        f"{E1} **Batting (Group):** Once bowled, the Striker selects a shot (`0-6`) inside the **Group Chat**.\n"
        f"   • **Same Number** = {E4} **OUT (Wicket + GIF!)**\n"
        f"   • **Different Number** = {E3} **Runs Scored (4 & 6 trigger GIFs!)**\n"
        f"{E8} **Winner Scorecard Poster:** At the end of the match, an HD Winner Scorecard Image is auto-generated!\n"
        f"{E7} **Commands:** `/cricket`, `/setteam`, `/score`, `/endcricket`, `/help`", reply_markup=kb
    )


@app.on_message(filters.command("score") & filters.group)
async def show_scorecard(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE":
        return await message.reply(f"{E4} **No live match is currently in progress!**")

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
        f"{E6} **LIVE SCORECARD (Innings {match['innings']})** {E8}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E2} **Host:** {mention(match['host'], match['host_name'])}\n"
        f"{E1} **{bat['name']}:** `{bat['score']}/{bat['wickets']}` ({overs} / {match.get('overs_limit', 6)}.0 Overs)\n"
        f"{E5} **Target:** `{match['target'] or '1st Innings'}` | **Max Wickets:** `{match['max_wickets']}`\n\n"
        f"{E3} **Striker:** {striker_mention} — `{s_stat['runs']}* ({s_stat['balls_faced']})`\n"
        f"{E7} **Bowler:** {bowler_mention} — `{b_stat['wickets']}-{b_stat['runs_conceded']} ({b_stat['balls_bowled']//6}.{b_stat['balls_bowled']%6})`\n━━━━━━━━━━━━━━━━━━━━━━"
    )
    await message.reply(text, reply_markup=InlineKeyboardMarkup([[c_btn("📊 Live Scoreboard", callback_data="noop", color=next_random_color(), emoji_id=PREMIUM_IDS[5])]]))


@app.on_message(filters.animation & filters.private)
async def handle_custom_gif_upload(client: Client, message: Message):
    if message.from_user.id != OWNER_ID: 
        return await message.reply(f"{E4} **Access Denied!**")

    fid = message.animation.file_id
    pending_gif_save[message.from_user.id] = fid
    kb = InlineKeyboardMarkup([
        [c_btn("🟢 Save as SIX (6) GIF", "savegif_6", color="green", emoji_id=PREMIUM_IDS[2]), c_btn("💥 Save as WICKET GIF", "savegif_WICKET", color="red", emoji_id=PREMIUM_IDS[3])],
        [c_btn("🎩 Save as HAT-TRICK GIF", "savegif_HATTRICK", color="blue", emoji_id=PREMIUM_IDS[6]), c_btn("🔵 Save as FOUR (4) GIF", "savegif_4", color="blue", emoji_id=PREMIUM_IDS[4])],
        [c_btn("🏆 Save as WIN GIF", "savegif_WIN", emoji_id=PREMIUM_IDS[7]), c_btn("🗑️ Clear All Saved GIFs", "savegif_CLEAR", color="red", emoji_id=PREMIUM_IDS[5])]
    ])
    await message.reply(f"{E2} **Owner GIF Manager:**\nWhere should this GIF be used during live matches?", reply_markup=kb)


@app.on_callback_query(filters.regex(r"^savegif_(6|4|WICKET|WIN|HATTRICK|CLEAR)$"))
async def handle_save_gif_callback(client: Client, cq: CallbackQuery):
    if cq.from_user.id != OWNER_ID: return await safe_answer(cq, "❌ Only the Bot Owner can do this!", show_alert=True)
    uid, choice = cq.from_user.id, cq.data.split("_")[1]
    if choice == "CLEAR":
        for k in CUSTOM_GIFS: CUSTOM_GIFS[k].clear()
        return await safe_edit(cq.message, f"{E4} **All custom GIFs cleared! Bot will now use Live Tenor Cricket GIFs.**")
    
    fid = pending_gif_save.get(uid)
    if not fid: return await safe_answer(cq, "⚠️ Please send the GIF again!", show_alert=True)
    
    key = int(choice) if choice in ["4", "6"] else choice
    CUSTOM_GIFS[key].append(fid)
    await safe_answer(cq, f"✅ Saved as {choice} GIF!", show_alert=True)
    await safe_edit(cq.message, f"{E8} **Success!** This GIF will now appear whenever a **{choice}** happens in the match!", reply_markup=InlineKeyboardMarkup([[c_btn(f"✅ Saved for {choice}", "noop", emoji_id=PREMIUM_IDS[7])]]))


@app.on_message(filters.command("cricket") & filters.group)
async def create_lobby(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in matches:
        m = matches[chat_id]
        return await message.reply(f"{E4} **A match is already active in this group!**\n{E2} Only Match Host ({mention(m['host'], m['host_name'])}) can end it.")

    matches[chat_id] = {"host": message.from_user.id, "host_name": message.from_user.first_name, "status": "SELECT_OVERS"}
    await message.reply(
        f"{E2} **Match Host: {message.from_user.first_name}** {E1}\n\n"
        f"{E7} **Host**, please select the number of overs for this match to open the lobby:",
        reply_markup=get_overs_kb()
    )


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
        "consecutive_wickets": 0, "turn_id": 0
    })

    host_active_matches[cq.from_user.id] = chat_id
    b_uname = await get_bot_username(client)
    await safe_answer(cq, f"✅ Selected {overs} Overs!")
    sent = await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
    if isinstance(sent, Message): match["lobby_msg_id"] = sent.id


@app.on_message(filters.command("setteam") & filters.group)
async def setteam_command(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match: return await message.reply(f"{E4} **No active match lobby found!** Send `/cricket` first.")
    if match["status"] != "LOBBY": return await message.reply(f"{E4} **Team names can only be changed while in the Match Lobby!**")
    if message.from_user.id != match["host"]: return await message.reply(f"{E4} **Only the Match Host can change IPL team names!**")
    await message.reply(format_ipl_menu_text(match), reply_markup=get_ipl_team_selection_kb(match, standalone=True))


@app.on_message(filters.command("endcricket") & filters.group)
async def force_end_match(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match: return await message.reply(f"{E4} **There is no active match in this group!**")
    if message.from_user.id != match["host"]: return await message.reply(f"{E4} **Access Denied!**")
    cleanup_match(chat_id)
    await message.reply(f"{E4} **Match has been ended by the Host ({mention(message.from_user.id, message.from_user.first_name)})!**")


@app.on_callback_query(filters.regex(r"^(open_ipl_menu|back_to_lobby|close_setteam|setipl_(A|B)_([A-Z]+))$"))
async def handle_ipl_team_callbacks(client: Client, cq: CallbackQuery):
    chat_id, user, match = cq.message.chat.id, cq.from_user, matches.get(cq.message.chat.id)
    if not match or match["status"] != "LOBBY": return await safe_answer(cq, "⚠ Lobby is closed!", show_alert=True)
    if cq.data != "back_to_lobby" and user.id != match["host"]: return await safe_answer(cq, "❌ Only the Match Host can change names!", show_alert=True)

    b_uname, data = await get_bot_username(client), cq.data
    if data == "open_ipl_menu": return await safe_edit(cq.message, format_ipl_menu_text(match), reply_markup=get_ipl_team_selection_kb(match, False))
    elif data == "back_to_lobby": return await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
    elif data == "close_setteam":
        try: await cq.message.delete()
        except: pass
        return

    _, team_letter, ipl_code = data.split("_")
    target_key, other_key = f"team_{team_letter}", "team_B" if team_letter == "A" else "team_A"
    new_ipl_name = IPL_TEAMS.get(ipl_code, f"{ipl_code} 🏏")

    if match[other_key]["name"] == new_ipl_name: return await safe_answer(cq, f"⚠️ {new_ipl_name} is already taken!", show_alert=True)

    match[target_key]["name"] = new_ipl_name
    await safe_answer(cq, f"✅ Team renamed to {new_ipl_name}!")
    
    is_standalone = (cq.message.id != match.get("lobby_msg_id") and match.get("lobby_msg_id") is not None)
    await safe_edit(cq.message, format_ipl_menu_text(match), reply_markup=get_ipl_team_selection_kb(match, is_standalone))

    if is_standalone and match.get("lobby_msg_id"):
        try: await client.edit_message_text(chat_id, match["lobby_msg_id"], text=format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
        except: pass


@app.on_callback_query(filters.regex(r"^(join_A|join_B|refresh_lobby|leave_lobby|start_game|cancel_game)$"))
async def handle_lobby_buttons(client: Client, cq: CallbackQuery):
    chat_id, user, match = cq.message.chat.id, cq.from_user, matches.get(cq.message.chat.id)
    if not match or match["status"] != "LOBBY": return await safe_answer(cq, "⚠️ Lobby is closed!", show_alert=True)

    b_uname, data = await get_bot_username(client), cq.data

    if data == "refresh_lobby": return await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
    elif data in ["join_A", "join_B"]:
        match["team_A"]["players"].pop(user.id, None)
        match["team_B"]["players"].pop(user.id, None)
        t_key = "team_A" if data == "join_A" else "team_B"
        match[t_key]["players"][user.id] = user.first_name
        init_player_stats(match, user.id, user.first_name)
        await safe_answer(cq, f"✅ You joined {match[t_key]['name']}!")
        await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))

    elif data == "leave_lobby":
        rem = match["team_A"]["players"].pop(user.id, None) or match["team_B"]["players"].pop(user.id, None)
        if rem: await safe_edit(cq.message, format_lobby_text(match), reply_markup=get_lobby_kb(match, b_uname))
        else: await safe_answer(cq, "⚠️ You have not joined any team yet!", show_alert=True)

    elif data == "cancel_game":
        if user.id != match["host"]: return await safe_answer(cq, "❌ Only Match Host can cancel!", show_alert=True)
        cleanup_match(chat_id)
        await safe_edit(cq.message, f"{E4} **Match Lobby cancelled by Host ({mention(user.id, user.first_name)}).**")

    elif data == "start_game":
        if user.id != match["host"]: return await safe_answer(cq, "❌ Only Match Host can start!", show_alert=True)
        if len(match["team_A"]["players"]) < 1 or len(match["team_B"]["players"]) < 1: return await safe_answer(cq, "❌ Minimum 1 player per team required!", show_alert=True)

        match["status"] = "TOSS"
        match["max_wickets"] = min(len(match["team_A"]["players"]), len(match["team_B"]["players"]))
        cap_a_id = list(match["team_A"]["players"].keys())[0]
        match["toss_caller"] = cap_a_id

        await safe_answer(cq, "🪙 Time for Toss!")
        await safe_edit(
            cq.message,
            f"{E6} **TIME FOR THE TOSS!** {E8}\n"
            f"{E1} **{match['team_A']['name']}** vs **{match['team_B']['name']}**\n\n"
            f"{E2} **Team 1 Player ({mention(cap_a_id, match['team_A']['players'][cap_a_id])})**, please call Heads or Tails:",
            reply_markup=get_toss_kb()
        )


@app.on_callback_query(filters.regex(r"^toss_(Heads|Tails)$"))
async def handle_toss_call(client: Client, cq: CallbackQuery):
    chat_id, match = cq.message.chat.id, matches.get(cq.message.chat.id)
    if not match or match["status"] != "TOSS": return
    if cq.from_user.id != match["toss_caller"]: return await safe_answer(cq, "❌ Only designated player can call toss!", show_alert=True)

    call, result = cq.data.split("_")[1], random.choice(["Heads", "Tails"])
    win_t_key = "team_A" if call == result else "team_B"
    match["toss_winner_team"] = win_t_key
    match["toss_winner_cap"] = list(match[win_t_key]["players"].keys())[0]

    win_name, cap_m = match[win_t_key]["name"], mention(match["toss_winner_cap"], match[win_t_key]["players"][match["toss_winner_cap"]])
    await safe_answer(cq, f"Toss Result: {result}!")
    await safe_edit(
        cq.message,
        f"{E6} **Toss Coin Landed On:** `{result}`!\n"
        f"{E8} **{win_name}** won the toss!\n\n"
        f"{E2} {cap_m}, choose Bat or Bowl:",
        reply_markup=get_toss_decision_kb()
    )


@app.on_callback_query(filters.regex(r"^decide_(bat|bowl)$"))
async def handle_toss_decision(client: Client, cq: CallbackQuery):
    chat_id, match = cq.message.chat.id, matches.get(cq.message.chat.id)
    if not match or match["status"] != "TOSS": return
    if cq.from_user.id != match["toss_winner_cap"]: return await safe_answer(cq, "❌ Only Toss-Winning side can choose!", show_alert=True)

    choice = cq.data.split("_")[1]
    win_team, lose_team = match["toss_winner_team"], "team_B" if match["toss_winner_team"] == "team_A" else "team_A"

    match["bat_team"] = win_team if choice == "bat" else lose_team
    match["bowl_team"] = lose_team if choice == "bat" else win_team
    match["status"], match["striker"], match["bowler"] = "LIVE", None, None

    await safe_answer(cq, "🔥 Match Started!")
    await safe_edit(
        cq.message,
        f"{E3} **MATCH STARTED! ({match.get('overs_limit', 6)} Overs | Max Wickets: {match['max_wickets']})** {E8}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E2} **Match Host:** {mention(match['host'], match['host_name'])}\n"
        f"{E1} **Batting:** {match[match['bat_team']]['name']}\n"
        f"{E5} **Bowling:** {match[match['bowl_team']]['name']}\n"
    )
    
    await prompt_host_player_selection(client, chat_id, need_bat=True, need_bowl=True)


# ================= HOST SELECTS PLAYERS IN DM =================
async def prompt_host_player_selection(client: Client, chat_id: int, need_bat: bool, need_bowl: bool):
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE": return
    match["state"] = "HOST_SELECTING"
    match["turn_id"] += 1

    host_id, b_uname = match["host"], await get_bot_username(client)
    kb = get_host_player_select_kb(match, need_bat, need_bowl)

    await client.send_message(
        chat_id,
        f"{E7} **Match Host ({match['host_name']}) is assigning the active players in the Bot DM...**",
        reply_markup=InlineKeyboardMarkup([[c_btn("👑 Host: Go to DM to Select", url=f"https://t.me/{b_uname}", emoji_id=PREMIUM_IDS[1])]])
    )

    try:
        await client.send_message(
            host_id,
            f"{E2} **Match:** {match['team_A']['name']} vs {match['team_B']['name']}\n"
            f"{E7} Please assign the active players for this phase!",
            reply_markup=kb
        )
    except RPCError:
        await client.send_message(chat_id, f"{E4} {mention(host_id, match['host_name'])} hasn't started the Bot DM! Please start the bot.")
    

@app.on_callback_query(filters.regex(r"^hostsel_(bat|bowl)_(\d+)$"))
async def handle_host_selection(client: Client, cq: CallbackQuery):
    host_id, chat_id = cq.from_user.id, host_active_matches.get(cq.from_user.id)
    match = matches.get(chat_id) if chat_id else None
    if not match or match.get("state") != "HOST_SELECTING" or host_id != match["host"]: 
        return await safe_answer(cq, "❌ Cannot select right now!", show_alert=True)
        
    role, uid = cq.data.split("_")[1], int(cq.data.split("_")[2])
    match["striker" if role == "bat" else "bowler"] = uid
    await safe_answer(cq, f"{'🏏 Striker' if role=='bat' else '🎳 Bowler'} Assigned!")
        
    need_bat, need_bowl = match["striker"] is None, match["bowler"] is None
    if need_bat or need_bowl:
        await safe_edit(cq.message, cq.message.text.markdown, reply_markup=get_host_player_select_kb(match, need_bat, need_bowl))
    else:
        await safe_edit(cq.message, f"{E8} **Players Assigned Successfully!**\n{E7} Head back to the group.")
        await prompt_bowler_dm(client, chat_id)


# ================= GAMEPLAY: DM BOWLING & GROUP BATTING =================
async def prompt_bowler_dm(client: Client, chat_id: int):
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE": return

    bowler_id, striker_id = match["bowler"], match["striker"]
    bat_dict, bowl_dict = match[match["bat_team"]], match[match["bowl_team"]]
    bowler_m, striker_m = mention(bowler_id, bowl_dict["players"][bowler_id]), mention(striker_id, bat_dict["players"][striker_id])
    over_num = f"{bat_dict['balls']//6}.{bat_dict['balls']%6 + 1}"
    
    match["state"] = "WAIT_BOWLER"
    match["turn_id"] += 1
    active_bowlers[bowler_id] = chat_id

    b_uname = await get_bot_username(client)
    await client.send_message(
        chat_id,
        f"{E7} **Delivery {over_num}** ({bat_dict['name']} vs {bowl_dict['name']})\n"
        f"{E1} **Striker:** {striker_m}\n"
        f"{E5} **Bowler:** {bowler_m} is selecting a delivery in the Bot's DM...",
        reply_markup=InlineKeyboardMarkup([[c_btn("🎳 Go to Bot DM (Bowler)", url=f"https://t.me/{b_uname}", emoji_id=PREMIUM_IDS[4])]])
    )

    try:
        await client.send_message(
            bowler_id,
            f"{E5} **YOUR TURN TO BOWL! (Ball {over_num})** {E3}\n"
            f"{E6} **Match:** {bat_dict['name']} vs {bowl_dict['name']}\n"
            f"{E1} **Facing Striker:** {striker_m}\n"
            f"{E7} *Select your secret delivery number (1 to 6):*",
            reply_markup=get_bowler_numbers_kb("bowl")
        )
    except RPCError:
        await client.send_message(chat_id, f"{E4} {bowler_m} has blocked or not started the Bot DM!")
    
    asyncio.create_task(match_timer_task(client, chat_id, "WAIT_BOWLER", match["turn_id"]))


@app.on_callback_query(filters.regex(r"^bowl_([1-6])$"))
async def handle_bowler_dm(client: Client, cq: CallbackQuery):
    bowler_id = cq.from_user.id
    if bowler_id not in active_bowlers: return await safe_answer(cq, "⚠️ It is not your turn to bowl right now!", show_alert=True)

    chat_id = active_bowlers.pop(bowler_id)
    match = matches.get(chat_id)
    if not match or match["state"] != "WAIT_BOWLER": return await safe_answer(cq, "⚠️ This delivery has already expired!", show_alert=True)

    ball_val = int(cq.data.split("_")[1])
    match["current_ball"] = ball_val
    match["state"] = "WAIT_BATSMAN"
    match["turn_id"] += 1

    await safe_answer(cq, f"🎳 You bowled {ball_val}!")
    await safe_edit(
        cq.message,
        f"{E8} **Ball Delivered!** You bowled `{ball_val}`.\n{E7} Head back to the Group to see the Batsman's shot!",
        reply_markup=InlineKeyboardMarkup([[c_btn(f"✅ Delivered Ball: {ball_val}", "noop", emoji_id=PREMIUM_IDS[7])]])
    )

    striker_id, bat_dict = match["striker"], match[match["bat_team"]]
    striker_m = mention(striker_id, bat_dict["players"][striker_id])
    bowler_m = mention(bowler_id, match[match["bowl_team"]]["players"][bowler_id])
    over_num = f"{bat_dict['balls']//6}.{bat_dict['balls']%6 + 1}"

    await client.send_message(
        chat_id,
        f"{E1} **Delivery {over_num} is Ready!** (Bowled by {bowler_m})\n"
        f"{E3} {striker_m}, play your shot right here in the Group (0-6):",
        reply_markup=get_batsman_numbers_kb("bat")
    )
    
    asyncio.create_task(match_timer_task(client, chat_id, "WAIT_BATSMAN", match["turn_id"]))


@app.on_callback_query(filters.regex(r"^bat_([0-6])$"))
async def handle_batsman_group(client: Client, cq: CallbackQuery):
    chat_id, match = cq.message.chat.id, matches.get(cq.message.chat.id)
    if not match or match["state"] != "WAIT_BATSMAN": return await safe_answer(cq, "⚠️ This ball has already been played!", show_alert=True)
    if cq.from_user.id != match["striker"]: return await safe_answer(cq, "❌ You are not the current Striker!", show_alert=True)

    match["state"] = "PROCESSING"
    bat_val, bowl_val = int(cq.data.split("_")[1]), match["current_ball"]
    bat_dict, bowl_dict = match[match["bat_team"]], match[match["bowl_team"]]
    striker_id, bowler_id = match["striker"], match["bowler"]
    striker_m, bowler_m = mention(striker_id, bat_dict["players"][striker_id]), mention(bowler_id, bowl_dict["players"][bowler_id])

    bat_dict["balls"] += 1
    match["stats"][striker_id]["balls_faced"] += 1
    match["stats"][bowler_id]["balls_bowled"] += 1
    overs_str = f"{bat_dict['balls']//6}.{bat_dict['balls']%6}"
    
    is_wicket = bat_val == bowl_val
    gif_to_play, gif_caption = None, None

    if is_wicket:
        bat_dict["wickets"] += 1
        match["out_players"].append(striker_id)
        match["all_out_history"].add(striker_id)
        match["stats"][bowler_id]["wickets"] += 1
        s_runs, s_balls = match["stats"][striker_id]["runs"], match["stats"][striker_id]["balls_faced"]
        match["consecutive_wickets"] += 1

        if match["consecutive_wickets"] == 3:
            await safe_answer(cq, "🔥 HAT-TRICK WICKET!!", show_alert=True)
            action_header = f"{E3} **HAT-TRICK WICKET!!** {E4}{E4}{E4}\n{E5} **Bowler ({bowler_m}) takes 3 IN A ROW!**\n{E1} **Batsman ({striker_m}):** `{bat_val}`\n{E4} {striker_m} departs for `{s_runs} ({s_balls})`!"
            gif_to_play, gif_caption = "HATTRICK", f"{E3} **HAT-TRICK WICKET!!** {E4}\n{E5} {bowler_m} is ON FIRE!"
            match["consecutive_wickets"] = 0
        else:
            await safe_answer(cq, "💥 OUT! Wicket!", show_alert=True)
            action_header = f"{E4} **HOWZAT!! WICKET!** {E4}\n{E1} **Batsman ({striker_m}):** `{bat_val}`\n{E7} {striker_m} departs for `{s_runs} ({s_balls})`!"
            gif_to_play, gif_caption = "WICKET", f"{E4} **WICKET!! ({bat_dict['name']})** {E4}\n{E5} {bowler_m} dismisses {E1} {striker_m} for `{s_runs} ({s_balls})`!"
    else:
        match["consecutive_wickets"] = 0 
        bat_dict["score"] += bat_val
        match["stats"][striker_id]["runs"] += bat_val
        match["stats"][bowler_id]["runs_conceded"] += bat_val
        s_runs = match["stats"][striker_id]["runs"]

        if bat_val == 0: shot_tag = f"{E6} **DEFENDED! DOT BALL!**"
        elif bat_val == 4:
            match["stats"][striker_id]["fours"] += 1
            shot_tag = f"{E5} **CRACKING FOUR!** {E7}"
            gif_to_play, gif_caption = 4, f"{E5} **CRACKING FOUR!! ({bat_dict['name']})**\n{E1} {striker_m} smashes `4` runs off {E5} {bowler_m}! (`{s_runs}*`)"
        elif bat_val == 6:
            match["stats"][striker_id]["sixes"] += 1
            shot_tag = f"{E3} **MASSIVE SIXER!!** {E8}"
            gif_to_play, gif_caption = 6, f"{E3} **KING KOHLI STYLE SIXER!! ({bat_dict['name']})** {E8}\n{E1} {striker_m} launches `6` runs off {E5} {bowler_m}! (`{s_runs}*`)"
        else: shot_tag = f"{E7} **{bat_val} RUNS!**"

        await safe_answer(cq, f"🏏 {bat_val} Runs!")
        action_header = f"{shot_tag}\n{E1} **Batsman ({striker_m}):** `{bat_val}`"

    target_line = f" | {E5} **Target:** `{match['target']}`" if match["target"] else ""
    board_footer = f"\n━━━━━━━━━━━━━━━━━━━━━━\n{E6} **{bat_dict['name']}:** `{bat_dict['score']}/{bat_dict['wickets']}` ({overs_str} / {match.get('overs_limit', 6)}.0 Overs){target_line}"
    
    await safe_edit(cq.message, action_header + board_footer, reply_markup=InlineKeyboardMarkup([[c_btn("🏏 MATCH SCORE UPDATED", "noop", emoji_id=PREMIUM_IDS[0])]]))

    if gif_to_play:
        await send_event_gif(client, chat_id, gif_to_play, gif_caption, auto_delete=12)
    
    await evaluate_and_continue(client, chat_id, match, is_wicket)


def build_match_summary(match: dict, result_banner: str, win_key: str, lose_key: str) -> str:
    tA, tB = match["team_A"], match["team_B"]
    win_squad_mentions = "Match Tied!" if win_key == lose_key else ", ".join([mention(uid, name) for uid, name in match[win_key]["players"].items()])
    stats_list = list(match["stats"].values())
    if stats_list:
        top_bat = max(stats_list, key=lambda x: (x["runs"], -x["balls_faced"]))
        top_bowl = max(stats_list, key=lambda x: (x["wickets"], -x["runs_conceded"]))
        awards_text = f"{E2} **Best Batsman:** {mention(top_bat['id'], top_bat['name'])} — `{top_bat['runs']} ({top_bat['balls_faced']})`\n{E3} **Best Bowler:** {mention(top_bowl['id'], top_bowl['name'])} — `{top_bowl['wickets']}-{top_bowl['runs_conceded']}`"
    else: awards_text = ""
    return (
        f"{E8} **IPL MATCH COMPLETED!** {E8}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{result_banner}\n"
        f"{E2} **Winning Squad:** {win_squad_mentions}\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{E6} **{tA['name']}:** `{tA['score']}/{tA['wickets']}` ({tA['balls']//6}.{tA['balls']%6} ov)\n"
        f"{E5} **{tB['name']}:** `{tB['score']}/{tB['wickets']}` ({tB['balls']//6}.{tB['balls']%6} ov)\n\n"
        f"{awards_text}"
    )

@app.on_callback_query(filters.regex(r"^noop$"))
async def handle_noop(client: Client, cq: CallbackQuery):
    await safe_answer(cq, "👇 Please select an option below!")

if __name__ == "__main__":
    print("🏏 Dynamic Color Kurigram IPL Cricket Bot Starting with Premium Emojis...")
    app.run()
