import asyncio
import inspect
import os
import random
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

app = Client(
    "DynamicColorCricketBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Global Storage
matches = {}  # {chat_id: match_dict}
active_bowlers = {}  # {bowler_user_id: chat_id}
BOT_USERNAME = None  # Auto-fetched on startup

# Pre-loaded Reliable GIFs for Wicket, Six, Four & Victory
CRICKET_GIFS = {
    "WICKET": [
        "https://media.giphy.com/media/l0HlPtbGpcnqa0fja/giphy.gif",
        "https://media.giphy.com/media/3o7TKwmnDgQb5jemjK/giphy.gif",
        "https://media.giphy.com/media/xT5LMHxhOfscxPfIfm/giphy.gif",
    ],
    6: [
        "https://media.giphy.com/media/3o7TKUM3IgJBX2as9O/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
        "https://media.giphy.com/media/26u4cqiYI30juCOGY/giphy.gif",
    ],
    4: [
        "https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif",
        "https://media.giphy.com/media/3o6ZtpvPW6fqxkE1xu/giphy.gif",
    ],
    "WIN": [
        "https://media.giphy.com/media/26u4cqiYI30juCOGY/giphy.gif",
        "https://media.giphy.com/media/l0MYt5jPR6QX5pnqM/giphy.gif",
    ],
}

# Inspect InlineKeyboardButton parameters once at startup for 100% crash-free color injection
_BTN_PARAMS = inspect.signature(InlineKeyboardButton.__init__).parameters
_COLOR_CYCLE = ["blue", "green", "red"]
_click_counter = 0


# ================= USER MENTION HELPER =================
def mention(user_id: int, name: str) -> str:
    """Creates a clickable Telegram user mention that notifies the player."""
    clean_name = (
        str(name).replace("[", "").replace("]", "").replace("*", "").strip()
        or "Player"
    )
    return f"[{clean_name}](tg://user?id={user_id})"


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
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url

    # Method 1: Kurigram 'style' parameter (ButtonStyle enum or string)
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

    # Method 2: Kurigram boolean keyword flags (primary=True, success=True, danger=True)
    flag_map = {"blue": "primary", "green": "success", "red": "danger"}
    flag_name = flag_map.get(color)
    if flag_name and flag_name in _BTN_PARAMS:
        kwargs[flag_name] = True
        return InlineKeyboardButton(**kwargs)

    # Method 3: Direct 'color' parameter
    if "color" in _BTN_PARAMS:
        kwargs["color"] = color
        return InlineKeyboardButton(**kwargs)

    return InlineKeyboardButton(**kwargs)


# ================= SAFE TELEGRAM API & GIF WRAPPERS =================
async def safe_edit(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup = None
):
    """Safely edits message without throwing MessageNotModified or FloodWait errors."""
    try:
        return await message.edit_text(text=text, reply_markup=reply_markup)
    except MessageNotModified:
        if reply_markup:
            try:
                return await message.edit_reply_markup(
                    reply_markup=reply_markup
                )
            except Exception:
                pass
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await safe_edit(message, text, reply_markup)
    except Exception:
        pass


async def safe_answer(
    cq: CallbackQuery, text: str = "", show_alert: bool = False
):
    try:
        await cq.answer(text, show_alert=show_alert)
    except Exception:
        pass


async def send_event_gif(
    client: Client,
    chat_id: int,
    event_key,
    caption: str,
    auto_delete: int = 10,
):
    """Sends a celebratory GIF mentioning the player(s) with dynamic color button."""
    gif_list = CRICKET_GIFS.get(event_key, [])
    if not gif_list:
        return
    kb = InlineKeyboardMarkup([[
        c_btn(
            "🎬 Match Highlight",
            callback_data="noop",
            color=next_random_color(),
        )
    ]])
    for gif_url in random.sample(gif_list, len(gif_list)):
        try:
            gif_msg = await client.send_animation(
                chat_id=chat_id,
                animation=gif_url,
                caption=caption,
                reply_markup=kb,
            )
            if auto_delete > 0:
                await asyncio.sleep(auto_delete)
                try:
                    await gif_msg.delete()
                except Exception:
                    pass
            return
        except Exception:
            continue


# ================= DYNAMIC KEYBOARD GENERATORS =================
def get_lobby_kb(bot_username: str) -> InlineKeyboardMarkup:
    colors = random.sample(_COLOR_CYCLE, 3)
    return InlineKeyboardMarkup([
        [
            c_btn("🔵 Join Team A", callback_data="join_A", color=colors[0]),
            c_btn("🔴 Join Team B", callback_data="join_B", color=colors[1]),
        ],
        [
            c_btn(
                "🔄 Refresh Colors",
                callback_data="refresh_lobby",
                color=colors[2],
            ),
            c_btn(
                "🚪 Leave Lobby",
                callback_data="leave_lobby",
                color=next_random_color(),
            ),
        ],
        [
            c_btn(
                "🤖 Activate Bot DM",
                url=f"https://t.me/{bot_username}?start=cricket",
                color=next_random_color(),
            ),
        ],
        [
            c_btn(
                "🚀 Start Match (Host)",
                callback_data="start_game",
                color=next_random_color(),
            ),
            c_btn(
                "✖ End Lobby (Host)",
                callback_data="cancel_game",
                color=next_random_color(),
            ),
        ],
    ])


def get_numbers_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            c_btn("1️⃣", callback_data=f"{prefix}_1", color=next_random_color()),
            c_btn("2️⃣", callback_data=f"{prefix}_2", color=next_random_color()),
            c_btn("3️⃣", callback_data=f"{prefix}_3", color=next_random_color()),
        ],
        [
            c_btn(
                "4️⃣ FOUR",
                callback_data=f"{prefix}_4",
                color=next_random_color(),
            ),
            c_btn("5️⃣", callback_data=f"{prefix}_5", color=next_random_color()),
            c_btn(
                "6️⃣ SIX", callback_data=f"{prefix}_6", color=next_random_color()
            ),
        ],
    ])


def get_toss_kb() -> InlineKeyboardMarkup:
    c1, c2 = random.sample(_COLOR_CYCLE, 2)
    return InlineKeyboardMarkup([[
        c_btn("🪙 Heads", callback_data="toss_Heads", color=c1),
        c_btn("🪙 Tails", callback_data="toss_Tails", color=c2),
    ]])


def get_toss_decision_kb() -> InlineKeyboardMarkup:
    c1, c2 = random.sample(_COLOR_CYCLE, 2)
    return InlineKeyboardMarkup([[
        c_btn("🏏 Batting", callback_data="decide_bat", color=c1),
        c_btn("🎳 Bowling", callback_data="decide_bowl", color=c2),
    ]])


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

    a_list = (
        "\n".join([
            f"  {i+1}. {mention(uid, name)}"
            for i, (uid, name) in enumerate(team_a.items())
        ])
        or "  *Empty*"
    )
    b_list = (
        "\n".join([
            f"  {i+1}. {mention(uid, name)}"
            for i, (uid, name) in enumerate(team_b.items())
        ])
        or "  *Empty*"
    )

    return (
        "🏏 **6-OVER MULTIPLAYER CRICKET LOBBY**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Match Host:** {mention(match['host'], match['host_name'])}\n\n"
        f"🔵 **Team A ({len(team_a)}):**\n{a_list}\n\n"
        f"🔴 **Team B ({len(team_b)}):**\n{b_list}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "• **Min Players:** 2 vs 2 (Max Unlimited)\n"
        "• **Format:** 6 Overs (36 Balls)\n"
        "🎨 *Click any button to dynamically shift button colors!*\n"
        "⚠ *Note: Every player must click 'Activate Bot DM' and press `/start`!*"
    )


def init_player_stats(match: dict, uid: int, name: str):
    if uid not in match["stats"]:
        match["stats"][uid] = {
            "id": uid,
            "name": name,
            "runs": 0,
            "balls_faced": 0,
            "fours": 0,
            "sixes": 0,
            "wickets": 0,
            "runs_conceded": 0,
            "balls_bowled": 0,
        }


def cleanup_match(chat_id: int):
    for b_id, c_id in list(active_bowlers.items()):
        if c_id == chat_id:
            active_bowlers.pop(b_id, None)
    matches.pop(chat_id, None)


# ================= BOT COMMANDS =================
@app.on_message(filters.command("start") & filters.private)
async def start_private(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[
        c_btn(
            "🎨 Test Dynamic Color!",
            callback_data="dm_color_test",
            color=next_random_color(),
        )
    ]])
    await message.reply(
        f"👋 **Hello {mention(message.from_user.id, message.from_user.first_name)}!**\n\n"
        "✅ **Your Bot DM is now Activated!**\n"
        "You can now join Multiplayer Cricket Matches in your group.\n"
        "🎳 When it is your turn to bowl, you will receive the **1-6 Colored Delivery Buttons** right here!",
        reply_markup=kb,
    )


@app.on_callback_query(filters.regex(r"^dm_color_test$"))
async def test_dm_color_change(client: Client, cq: CallbackQuery):
    new_color = next_random_color()
    kb = InlineKeyboardMarkup([[
        c_btn(
            f"🎨 Color Changed! ({new_color.upper()}) - Click Again",
            callback_data="dm_color_test",
            color=new_color,
        )
    ]])
    await safe_answer(cq, f"Button color shifted to {new_color.upper()}!")
    await safe_edit(cq.message, cq.message.text.markdown, reply_markup=kb)


@app.on_message(filters.command("help") & (filters.group | filters.private))
async def help_command(client: Client, message: Message):
    kb = InlineKeyboardMarkup([[
        c_btn(
            "🎨 Click to Shift Color",
            callback_data="noop",
            color=next_random_color(),
        )
    ]])
    await message.reply(
        "🏏 **HOW TO PLAY MULTIPLAYER CRICKET**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "1️⃣ **Start Match:** Send `/cricket` in a group to open the Lobby.\n"
        "2️⃣ **Join Teams:** Minimum **2 players per team** (Unlimited Max). All players must start the bot in DM first.\n"
        "3️⃣ **Host Controls:** Only the user who started the game (`/cricket`) can **Start** or **End** the match.\n"
        "4️⃣ **Bowling (DM):** The Bowler secretly selects a number (`1-6`) inside the **Bot's Private DM**.\n"
        "5️⃣ **Batting (Group):** Once bowled, the Striker selects a shot (`1-6`) inside the **Group Chat**.\n"
        "   • **Same Number** = 💥 **OUT (Wicket + GIF!)**\n"
        "   • **Different Number** = 🏏 **Runs Scored (4 & 6 trigger GIFs!)**\n"
        "6️⃣ **Commands:** `/cricket`, `/score`, `/endcricket`, `/help`",
        reply_markup=kb,
    )


@app.on_message(filters.command("cricket") & filters.group)
async def create_lobby(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in matches:
        m = matches[chat_id]
        return await message.reply(
            f"⚠️ **A match is already active in this group!**\n"
            f"👑 Only the Match Host ({mention(m['host'], m['host_name'])}) can end it using `/endcricket`."
        )

    matches[chat_id] = {
        "host": message.from_user.id,
        "host_name": message.from_user.first_name,
        "status": "LOBBY",
        "overs_limit": 6,
        "max_balls": 36,
        "innings": 1,
        "target": None,
        "max_wickets": 2,
        "team_A": {
            "name": "Team A 🔵",
            "players": {},
            "score": 0,
            "wickets": 0,
            "balls": 0,
        },
        "team_B": {
            "name": "Team B 🔴",
            "players": {},
            "score": 0,
            "wickets": 0,
            "balls": 0,
        },
        "bat_team": "team_A",
        "bowl_team": "team_B",
        "striker": None,
        "bowler": None,
        "out_players": [],
        "current_ball": None,
        "state": None,
        "stats": {},
    }

    b_uname = await get_bot_username(client)
    await message.reply(
        format_lobby_text(matches[chat_id]), reply_markup=get_lobby_kb(b_uname)
    )


@app.on_message(filters.command("endcricket") & filters.group)
async def force_end_match(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match:
        return await message.reply(
            "❌ **There is no active match in this group!**"
        )

    if message.from_user.id != match["host"]:
        return await message.reply(
            f"❌ **Access Denied!**\n"
            f"Only the Match Host ({mention(match['host'], match['host_name'])}) can end this match!"
        )

    cleanup_match(chat_id)
    await message.reply(
        f"🛑 **Match has been ended by the Host ({mention(message.from_user.id, message.from_user.first_name)})!**"
    )


@app.on_message(filters.command("score") & filters.group)
async def show_scorecard(client: Client, message: Message):
    chat_id = message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE":
        return await message.reply(
            "❌ **No live match is currently in progress!**"
        )

    bat = match[match["bat_team"]]
    bowl = match[match["bowl_team"]]
    overs = f"{bat['balls']//6}.{bat['balls']%6}"

    striker_id = match["striker"]
    bowler_id = match["bowler"]
    striker_mention = mention(
        striker_id, bat["players"].get(striker_id, "Striker")
    )
    bowler_mention = mention(bowler_id, bowl["players"].get(bowler_id, "Bowler"))

    s_stat = match["stats"].get(striker_id, {"runs": 0, "balls_faced": 0})
    b_stat = match["stats"].get(
        bowler_id, {"wickets": 0, "runs_conceded": 0, "balls_bowled": 0}
    )

    kb = InlineKeyboardMarkup([[
        c_btn(
            "📊 Live Scoreboard",
            callback_data="noop",
            color=next_random_color(),
        )
    ]])
    text = (
        f"📊 **LIVE SCORECARD (Innings {match['innings']})**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Host:** {mention(match['host'], match['host_name'])}\n"
        f"🏏 **{bat['name']}:** `{bat['score']}/{bat['wickets']}` ({overs} / 6.0 Overs)\n"
        f"🎯 **Target:** `{match['target'] or '1st Innings'}` | **Max Wickets:** `{match['max_wickets']}`\n\n"
        f"👤 **Striker:** {striker_mention} — `{s_stat['runs']}* ({s_stat['balls_faced']})`\n"
        f"🎳 **Bowler:** {bowler_mention} — `{b_stat['wickets']}-{b_stat['runs_conceded']} ({b_stat['balls_bowled']//6}.{b_stat['balls_bowled']%6})`\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    await message.reply(text, reply_markup=kb)


# ================= LOBBY & TOSS HANDLERS =================
@app.on_callback_query(
    filters.regex(
        r"^(join_A|join_B|refresh_lobby|leave_lobby|start_game|cancel_game)$"
    )
)
async def handle_lobby_buttons(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    user = cq.from_user
    match = matches.get(chat_id)

    if not match or match["status"] != "LOBBY":
        return await safe_answer(
            cq, "⚠️ This Lobby is already closed!", show_alert=True
        )

    data = cq.data
    b_uname = await get_bot_username(client)

    if data == "refresh_lobby":
        await safe_answer(cq, "🎨 Button colors shifted!")
        return await safe_edit(
            cq.message,
            format_lobby_text(match),
            reply_markup=get_lobby_kb(b_uname),
        )

    elif data in ["join_A", "join_B"]:
        try:
            await client.send_chat_action(user.id, enums.ChatAction.TYPING)
        except Exception:
            return await safe_answer(
                cq,
                "❌ Please click 'Activate Bot DM' below and press /start first!",
                show_alert=True,
            )

        match["team_A"]["players"].pop(user.id, None)
        match["team_B"]["players"].pop(user.id, None)

        t_key = "team_A" if data == "join_A" else "team_B"
        match[t_key]["players"][user.id] = user.first_name
        init_player_stats(match, user.id, user.first_name)

        await safe_answer(cq, f"✅ You joined {match[t_key]['name']}!")
        await safe_edit(
            cq.message,
            format_lobby_text(match),
            reply_markup=get_lobby_kb(b_uname),
        )

    elif data == "leave_lobby":
        rem_a = match["team_A"]["players"].pop(user.id, None)
        rem_b = match["team_B"]["players"].pop(user.id, None)
        if rem_a or rem_b:
            await safe_answer(cq, "👋 You left the lobby!")
            await safe_edit(
                cq.message,
                format_lobby_text(match),
                reply_markup=get_lobby_kb(b_uname),
            )
        else:
            await safe_answer(
                cq, "⚠️ You have not joined any team yet!", show_alert=True
            )

    elif data == "cancel_game":
        if user.id != match["host"]:
            await safe_edit(
                cq.message,
                format_lobby_text(match),
                reply_markup=get_lobby_kb(b_uname),
            )
            return await safe_answer(
                cq,
                f"❌ Only the Match Host ({match['host_name']}) can cancel the game!",
                show_alert=True,
            )
        cleanup_match(chat_id)
        await safe_answer(cq, "🛑 Lobby Cancelled!")
        await safe_edit(
            cq.message,
            f"🛑 **Match Lobby was cancelled by the Host ({mention(user.id, user.first_name)}).**",
        )

    elif data == "start_game":
        if user.id != match["host"]:
            await safe_edit(
                cq.message,
                format_lobby_text(match),
                reply_markup=get_lobby_kb(b_uname),
            )
            return await safe_answer(
                cq,
                f"❌ Only the Match Host ({match['host_name']}) can start the match!",
                show_alert=True,
            )

        if (
            len(match["team_A"]["players"]) < 2
            or len(match["team_B"]["players"]) < 2
        ):
            await safe_edit(
                cq.message,
                format_lobby_text(match),
                reply_markup=get_lobby_kb(b_uname),
            )
            return await safe_answer(
                cq,
                "❌ Minimum 2 players per team required! (At least 2 vs 2)",
                show_alert=True,
            )

        match["status"] = "TOSS"
        match["max_wickets"] = min(
            len(match["team_A"]["players"]), len(match["team_B"]["players"])
        )
        cap_a_id = list(match["team_A"]["players"].keys())[0]
        cap_a_name = match["team_A"]["players"][cap_a_id]
        match["toss_caller"] = cap_a_id

        await safe_answer(cq, "🪙 Time for the Toss!")
        await safe_edit(
            cq.message,
            f"🪙 **TIME FOR THE TOSS!**\n\n"
            f"🔵 **Team A Captain ({mention(cap_a_id, cap_a_name)})**, please call Heads or Tails:",
            reply_markup=get_toss_kb(),
        )


@app.on_callback_query(filters.regex(r"^toss_(Heads|Tails)$"))
async def handle_toss_call(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "TOSS":
        return await safe_answer(
            cq, "⚠️ The toss is already over!", show_alert=True
        )

    if cq.from_user.id != match["toss_caller"]:
        await safe_edit(
            cq.message, cq.message.text.markdown, reply_markup=get_toss_kb()
        )
        return await safe_answer(
            cq, "❌ Only Team A Captain can call the toss!", show_alert=True
        )

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
    await safe_edit(
        cq.message,
        f"🪙 **Toss Coin Landed On:** `{result}`!\n"
        f"🎉 **{winner_name}** won the toss!\n\n"
        f"👑 Captain {cap_mention}, choose whether to Bat or Bowl first:",
        reply_markup=get_toss_decision_kb(),
    )


@app.on_callback_query(filters.regex(r"^decide_(bat|bowl)$"))
async def handle_toss_decision(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)
    if not match or match["status"] != "TOSS":
        return await safe_answer(
            cq, "⚠️ Decision has already been made!", show_alert=True
        )

    if cq.from_user.id != match["toss_winner_cap"]:
        await safe_edit(
            cq.message,
            cq.message.text.markdown,
            reply_markup=get_toss_decision_kb(),
        )
        return await safe_answer(
            cq,
            "❌ Only the Toss-Winning Captain can make this choice!",
            show_alert=True,
        )

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

    match["striker"] = list(bat_dict["players"].keys())[0]
    match["bowler"] = list(bowl_dict["players"].keys())[0]

    striker_m = mention(
        match["striker"], bat_dict["players"][match["striker"]]
    )
    bowler_m = mention(match["bowler"], bowl_dict["players"][match["bowler"]])

    await safe_answer(cq, "🔥 Match Started!")
    await safe_edit(
        cq.message,
        f"🔥 **MATCH STARTED! (6 Overs | Max Wickets: {match['max_wickets']})**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 **Match Host:** {mention(match['host'], match['host_name'])}\n"
        f"🏏 **Batting:** {bat_dict['name']}\n"
        f"🎳 **Bowling:** {bowl_dict['name']}\n\n"
        f"👤 **Opening Striker:** {striker_m}\n"
        f"🎯 **Opening Bowler:** {bowler_m}",
    )

    await prompt_bowler_dm(client, chat_id)


# ================= GAMEPLAY: DM BOWLING & GROUP BATTING =================
async def prompt_bowler_dm(client: Client, chat_id: int):
    match = matches.get(chat_id)
    if not match or match["status"] != "LIVE":
        return

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
        f"⏳ **Delivery {over_num}**\n"
        f"🏏 **Striker:** {striker_m}\n"
        f"🎳 **Bowler:** {bowler_m} is selecting a delivery in the Bot's DM...",
        reply_markup=dm_btn,
    )

    try:
        await client.send_message(
            bowler_id,
            f"🎳 **YOUR TURN TO BOWL! (Ball {over_num})**\n"
            f"👤 **Facing Striker:** {striker_m}\n"
            f"🎨 *Select your secret delivery number (1 to 6):*",
            reply_markup=get_numbers_kb("bowl"),
        )
    except RPCError:
        await client.send_message(
            chat_id,
            f"⚠️ {bowler_m} has blocked or not started the Bot DM! Please open @{b_uname} and send `/start`.",
        )


@app.on_callback_query(filters.regex(r"^bowl_([1-6])$"))
async def handle_bowler_dm(client: Client, cq: CallbackQuery):
    bowler_id = cq.from_user.id
    if bowler_id not in active_bowlers:
        return await safe_answer(
            cq, "⚠️ It is not your turn to bowl right now!", show_alert=True
        )

    chat_id = active_bowlers.pop(bowler_id)
    match = matches.get(chat_id)
    if not match or match["state"] != "WAIT_BOWLER":
        return await safe_answer(
            cq, "⚠️ This delivery has already expired!", show_alert=True
        )

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
        f"✅ **Ball Delivered!** You bowled `{ball_val}`.\n"
        f"👉 Head back to the Group to see the Batsman's shot!",
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
        f"🔥 {striker_m}, play your shot right here in the Group (1-6):",
        reply_markup=get_numbers_kb("bat"),
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


@app.on_callback_query(filters.regex(r"^bat_([1-6])$"))
async def handle_batsman_group(client: Client, cq: CallbackQuery):
    chat_id = cq.message.chat.id
    match = matches.get(chat_id)

    if not match or match["state"] != "WAIT_BATSMAN":
        return await safe_answer(
            cq, "⚠️ This ball has already been played!", show_alert=True
        )

    if cq.from_user.id != match["striker"]:
        await safe_edit(
            cq.message,
            cq.message.text.markdown,
            reply_markup=get_numbers_kb("bat"),
        )
        return await safe_answer(
            cq,
            "❌ You are not the current Striker! Only the active Batsman can play this ball.",
            show_alert=True,
        )

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
    is_wicket = bat_val == bowl_val

    if is_wicket:
        bat_dict["wickets"] += 1
        match["out_players"].append(striker_id)
        match["stats"][bowler_id]["wickets"] += 1
        s_runs = match["stats"][striker_id]["runs"]
        s_balls = match["stats"][striker_id]["balls_faced"]

        await safe_answer(cq, "💥 OUT! Wicket!", show_alert=True)
        action_header = (
            f"💥 **HOWZAT!! WICKET!** ☝️\n"
            f"🎳 **Bowler ({bowler_m}):** `{bowl_val}` | 🏏 **Batsman ({striker_m}):** `{bat_val}`\n"
            f"🚶 {striker_m} departs for `{s_runs} ({s_balls})`!"
        )
        badge_btn = c_btn(
            f"💥 WICKET! ({bowl_val} == {bat_val})",
            callback_data="noop",
            color="red",
        )

        # Trigger Wicket GIF mentioning both Bowler & Batsman!
        gif_caption = (
            f"💥 **WICKET!!** ☝️\n"
            f"🎳 {bowler_m} dismisses 🏏 {striker_m} for `{s_runs} ({s_balls})`!"
        )
        asyncio.create_task(
            send_event_gif(client, chat_id, "WICKET", gif_caption)
        )
    else:
        bat_dict["score"] += bat_val
        match["stats"][striker_id]["runs"] += bat_val
        match["stats"][bowler_id]["runs_conceded"] += bat_val
        s_runs = match["stats"][striker_id]["runs"]
        s_balls = match["stats"][striker_id]["balls_faced"]

        if bat_val == 4:
            match["stats"][striker_id]["fours"] += 1
            shot_tag = "🔵 **CRACKING FOUR!**"
            gif_caption = (
                f"🔵 **CRACKING FOUR!!**\n"
                f"🏏 {striker_m} smashes `4` runs off 🎳 {bowler_m}! (`{s_runs}*`)"
            )
            asyncio.create_task(
                send_event_gif(client, chat_id, 4, gif_caption)
            )
        elif bat_val == 6:
            match["stats"][striker_id]["sixes"] += 1
            shot_tag = "🟢 **MASSIVE SIXER!!**"
            gif_caption = (
                f"🟢 **MASSIVE SIXER!!** 🚀\n"
                f"🏏 {striker_m} launches `6` runs off 🎳 {bowler_m}! (`{s_runs}*`)"
            )
            asyncio.create_task(
                send_event_gif(client, chat_id, 6, gif_caption)
            )
        else:
            shot_tag = f"🏃 **{bat_val} RUNS!**"

        await safe_answer(cq, f"🏏 {bat_val} Runs!")
        action_header = (
            f"{shot_tag}\n"
            f"🎳 **Bowler ({bowler_m}):** `{bowl_val}` | 🏏 **Batsman ({striker_m}):** `{bat_val}`"
        )
        badge_btn = c_btn(
            f"🏏 +{bat_val} RUNS (Score: {bat_dict['score']}/{bat_dict['wickets']})",
            callback_data="noop",
            color=next_random_color(),
        )

    target_line = (
        f" | 🎯 **Target:** `{match['target']}`" if match["target"] else ""
    )
    board_footer = (
        f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 **{bat_dict['name']}:** `{bat_dict['score']}/{bat_dict['wickets']}` ({overs_str} / 6.0 Overs){target_line}"
    )

    await safe_edit(
        cq.message,
        action_header + board_footer,
        reply_markup=InlineKeyboardMarkup([[badge_btn]]),
    )

    # Check Innings or Match End Conditions
    target_chased = (
        match["target"] is not None and bat_dict["score"] >= match["target"]
    )
    all_out = bat_dict["wickets"] >= match["max_wickets"]
    overs_done = bat_dict["balls"] >= match["max_balls"]

    if target_chased or all_out or overs_done:
        if match["innings"] == 1:
            match["innings"] = 2
            match["target"] = bat_dict["score"] + 1
            match["bat_team"], match["bowl_team"] = (
                match["bowl_team"],
                match["bat_team"],
            )
            match["out_players"] = []

            new_bat = match[match["bat_team"]]
            new_bowl = match[match["bowl_team"]]
            match["striker"] = list(new_bat["players"].keys())[0]
            match["bowler"] = list(new_bowl["players"].keys())[0]

            next_striker_m = mention(
                match["striker"], new_bat["players"][match["striker"]]
            )
            next_bowler_m = mention(
                match["bowler"], new_bowl["players"][match["bowler"]]
            )

            await client.send_message(
                chat_id,
                f"🔄 **INNINGS BREAK!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏏 **{bat_dict['name']}** finished at `{bat_dict['score']}/{bat_dict['wickets']}`.\n"
                f"🎯 **Target for {new_bat['name']}:** `{match['target']}` runs in 36 balls!\n\n"
                f"👤 **Next Batting (Striker):** {next_striker_m}\n"
                f"🎳 **Next Bowling (Bowler):** {next_bowler_m}",
            )
            await asyncio.sleep(2)
            return await prompt_bowler_dm(client, chat_id)
        else:
            if target_chased:
                rem_w = match["max_wickets"] - bat_dict["wickets"]
                result_msg = f"🏆 **{bat_dict['name']} WON BY {rem_w} WICKETS!** 🎉"
            elif bat_dict["score"] == match["target"] - 1:
                result_msg = "🤝 **MATCH TIED! What a thriller!** 🔥"
            else:
                runs_margin = (match["target"] - 1) - bat_dict["score"]
                result_msg = (
                    f"🏆 **{bowl_dict['name']} WON BY {runs_margin} RUNS!** 🎉"
                )

            summary = build_match_summary(match, result_msg)
            cleanup_match(chat_id)
            end_kb = InlineKeyboardMarkup([[
                c_btn(
                    "🏆 Match Completed",
                    callback_data="noop",
                    color=next_random_color(),
                )
            ]])
            asyncio.create_task(
                send_event_gif(client, chat_id, "WIN", result_msg, auto_delete=0)
            )
            return await client.send_message(
                chat_id, summary, reply_markup=end_kb
            )

    # Bring Next Batsman if Wicket Fell (With Clickable Mention!)
    if is_wicket:
        avail_batsmen = [
            uid
            for uid in bat_dict["players"]
            if uid not in match["out_players"]
        ]
        match["striker"] = avail_batsmen[0]
        next_bat_m = mention(
            match["striker"], bat_dict["players"][match["striker"]]
        )
        await client.send_message(
            chat_id,
            f"🧢 **Next Batting (New Striker In):** {next_bat_m}",
        )

    # Rotate Bowler Every Over (6 Balls) (With Clickable Mention!)
    if bat_dict["balls"] % 6 == 0:
        bowl_uids = list(bowl_dict["players"].keys())
        next_idx = (bowl_uids.index(bowler_id) + 1) % len(bowl_uids)
        match["bowler"] = bowl_uids[next_idx]
        next_bowl_m = mention(
            match["bowler"], bowl_dict["players"][match["bowler"]]
        )
        curr_bat_m = mention(
            match["striker"], bat_dict["players"][match["striker"]]
        )
        await client.send_message(
            chat_id,
            f"📣 **End of Over {bat_dict['balls']//6}!**\n"
            f"🎳 **Next Bowling (New Bowler):** {next_bowl_m}\n"
            f"🏏 **Current Batting (Striker):** {curr_bat_m}",
        )

    await asyncio.sleep(1)
    await prompt_bowler_dm(client, chat_id)


def build_match_summary(match: dict, result_banner: str) -> str:
    tA = match["team_A"]
    tB = match["team_B"]

    stats_list = list(match["stats"].values())
    if stats_list:
        top_bat = max(stats_list, key=lambda x: (x["runs"], -x["balls_faced"]))
        top_bowl = max(
            stats_list, key=lambda x: (x["wickets"], -x["runs_conceded"])
        )
        bat_m = mention(top_bat["id"], top_bat["name"])
        bowl_m = mention(top_bowl["id"], top_bowl["name"])
        awards_text = (
            f"⭐ **Best Batsman:** {bat_m} — `{top_bat['runs']} ({top_bat['balls_faced']})`\n"
            f"🔥 **Best Bowler:** {bowl_m} — `{top_bowl['wickets']}-{top_bowl['runs_conceded']}`"
        )
    else:
        awards_text = ""

    return (
        f"🏁 **MATCH COMPLETED!** 🏁\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{result_banner}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔵 **Team A:** `{tA['score']}/{tA['wickets']}` ({tA['balls']//6}.{tA['balls']%6} ov)\n"
        f"🔴 **Team B:** `{tB['score']}/{tB['wickets']}` ({tB['balls']//6}.{tB['balls']%6} ov)\n\n"
        f"{awards_text}"
    )


# Optional: Send any GIF to the Bot in DM to automatically add it to the match GIF pool!
@app.on_message(filters.animation & filters.private)
async def auto_save_gif_id(client: Client, message: Message):
    fid = message.animation.file_id
    CRICKET_GIFS[6].append(fid)
    CRICKET_GIFS["WICKET"].append(fid)
    await message.reply(
        f"✅ **GIF Added to Live Match Pool!**\nFile ID: `{fid}`"
    )


if __name__ == "__main__":
    print("🏏 Dynamic Color Kurigram Cricket Bot Starting...")
    app.run()
