# bot.py
import logging, os, sqlite3
from contextlib import closing
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, CallbackQueryHandler, ConversationHandler, filters
)

# ---------- Load env ----------
load_dotenv()
TOKEN = os.getenv("TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
REF_LINK = os.getenv("REF_LINK")

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dk_win_signal_bot")

# ---------- DB Setup ----------
DB_PATH = "dkbot.db"
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    tg_id INTEGER PRIMARY KEY,
    tg_username TEXT,
    platform_uid TEXT,
    approved INTEGER DEFAULT 0,
    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stats (
    tg_id INTEGER PRIMARY KEY,
    loss_streak INTEGER DEFAULT 0,
    win_streak INTEGER DEFAULT 0,
    last_signal TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

def db_init():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)
        cur = conn.execute("SELECT value FROM settings WHERE key='ref_link'")
        if not cur.fetchone():
            conn.execute("INSERT INTO settings(key,value) VALUES('ref_link',?)", (REF_LINK,))
        conn.commit()

# ---------- DB Helpers ----------
def upsert_user(tg_id, tg_username=None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO users(tg_id,tg_username) VALUES(?,?) ON CONFLICT(tg_id) DO UPDATE SET tg_username=excluded.tg_username",
            (tg_id, tg_username),
        )
        conn.commit()

def set_platform_uid(tg_id, platform_uid):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET platform_uid=? WHERE tg_id=?", (platform_uid, tg_id))
        conn.commit()

def set_approval(tg_id, approved):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE users SET approved=? WHERE tg_id=?", (1 if approved else 0, tg_id))
        conn.commit()

def is_approved(tg_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT approved FROM users WHERE tg_id=?", (tg_id,))
        row = cur.fetchone()
        return bool(row and row[0]==1)

def inc_result(tg_id, win):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO stats(tg_id,loss_streak,win_streak,last_signal) VALUES(?,0,0,NULL) ON CONFLICT(tg_id) DO NOTHING",
            (tg_id,),
        )
        if win:
            conn.execute("UPDATE stats SET win_streak=win_streak+1, loss_streak=0 WHERE tg_id=?", (tg_id,))
        else:
            conn.execute("UPDATE stats SET loss_streak=loss_streak+1, win_streak=0 WHERE tg_id=?", (tg_id,))
        conn.commit()

def get_streaks(tg_id):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("SELECT loss_streak, win_streak FROM stats WHERE tg_id=?", (tg_id,))
        row = cur.fetchone()
        return (row[0], row[1]) if row else (0,0)

def set_last_signal(tg_id, sig):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO stats(tg_id,loss_streak,win_streak,last_signal) VALUES(?,?,?,?) "
            "ON CONFLICT(tg_id) DO UPDATE SET last_signal=excluded.last_signal",
            (tg_id,0,0,sig)
        )
        conn.commit()

def is_owner(user_id):
    return user_id == OWNER_ID

# ---------- Signal Engine ----------
def signal_engine(period, recents, loss_streak):
    p_tail = int(period[-1]) if period and period[-1].isdigit() else 0
    r = recents.lower()
    big_count = r.count("big")
    small_count = r.count("small")
    green_count = r.count("green")
    red_count = r.count("red")
    big_small = "Big" if (p_tail%2==1 or big_count<small_count) else "Small"
    color = "Green" if (p_tail in (1,4,7) or green_count<=red_count) else "Red"
    base_digit = (p_tail*3 + big_count - small_count) % 10
    note = []
    if loss_streak>=6:
        note.append("⚠️ Go Safe/Skip এই রাউন্ড — 6 টা টানা লস।")
        big_small = "Small" if big_small=="Big" else "Big"
        color="Green"
        base_digit=(base_digit+5)%10
    return {"big_small":big_small, "color":color, "digit":base_digit, "note":" ".join(note) if note else ""}

# ---------- Handlers ----------
ASK_PERIOD, ASK_RECENTS = range(2)

async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user=update.effective_user
    upsert_user(user.id,user.username if user else None)
    await update.message.reply_text(f"স্বাগতম! /register দিয়ে শুরু করুন। রেফারেল: {REF_LINK}")

async def help_cmd(update:Update,context:ContextTypes.DEFAULT_TYPE):
    text="/register - UID সাবমিট\n/signal - 1m সিগনাল\n/result win|lose - ফল\n/my - স্ট্যাটাস\nOwner: /approve, /reject, /users, /setref, /broadcast"
    await update.message.reply_text(text)

# ... এখানে আগের পুরো handlers + conversation + admin cb + result_cmd etc. থাকবে, previous code মতো ...

# ---------- Main ----------
def main():
    db_init()
    app = ApplicationBuilder().token(TOKEN).build()
    # Commands
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("help",help_cmd))
    # Add rest of handlers (register, signal, result, approve, reject, broadcast etc.)
    # Conversation handler for /signal
    # CallbackQueryHandler for approve/reject
    # MessageHandler for UID submission
    logger.info("🤖 DK Win Signal Bot started (Background Worker)…")
    app.run_polling(close_loop=False)

if __name__=="__main__":
    main()
