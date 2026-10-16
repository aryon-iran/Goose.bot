import os
import time
import random
import threading
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask

# ================== تنظیمات ==================
TOKEN = os.environ.get("BALE_BOT_TOKEN", "1114060877:MElaDbmi0AETIOcQz9F4BBer-VeRwu0-nMU")
API_URL = f"https://tapi.bale.ai/bot{TOKEN}"
ADMIN_USERNAME = "aryon_admin"
RUN_COMMAND = "Run_goose_dark"
MENU_COMMAND = "dark_goose"
DATABASE_URL = os.environ.get("DATABASE_URL")

# ================== وضعیت ==================
bot_active = False
last_update_id = 0
admin_state = {}

# ================== اتصال به دیتابیس ==================
def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS groups (
        chat_id BIGINT PRIMARY KEY, title TEXT, joined_at BIGINT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT, chat_id BIGINT,
        username TEXT, first_name TEXT,
        goose_calls INTEGER DEFAULT 0,
        gif_count INTEGER DEFAULT 0,
        sticker_count INTEGER DEFAULT 0,
        msg_count INTEGER DEFAULT 0,
        coins INTEGER DEFAULT 0,
        birthday TEXT,
        PRIMARY KEY (user_id, chat_id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS exams (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT, subject TEXT, exam_date TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS homeworks (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT, subject TEXT, description TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS achievements (
        user_id BIGINT, chat_id BIGINT, title TEXT,
        awarded_at BIGINT, PRIMARY KEY (user_id, chat_id, title))""")
    c.execute("""CREATE TABLE IF NOT EXISTS blocked (user_id BIGINT PRIMARY KEY)""")
    c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS shop (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT, item_name TEXT, price INTEGER, description TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS purchases (
        user_id BIGINT, chat_id BIGINT, item_name TEXT,
        bought_at BIGINT, PRIMARY KEY (user_id, chat_id, item_name))""")
    c.execute("""CREATE TABLE IF NOT EXISTS game_sessions (
        chat_id BIGINT PRIMARY KEY, game_type TEXT, state TEXT, started_at BIGINT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS keywords (
        id SERIAL PRIMARY KEY,
        keyword TEXT UNIQUE, reply_text TEXT, created_at BIGINT)""")
    conn.commit()
    c.close()
    conn.close()

# ================== توابع دیتابیس ==================
def get_setting(key, default=None):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=%s", (key,))
    row = c.fetchone(); c.close(); conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO settings (key, value) VALUES (%s, %s)
                 ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""",
              (key, str(value)))
    conn.commit(); c.close(); conn.close()

def ensure_user(user_id, chat_id, username, first_name):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO users (user_id, chat_id, username, first_name)
                 VALUES (%s, %s, %s, %s)
                 ON CONFLICT (user_id, chat_id) DO UPDATE
                 SET username=EXCLUDED.username, first_name=EXCLUDED.first_name""",
              (user_id, chat_id, username, first_name))
    conn.commit(); c.close(); conn.close()

def ensure_group(chat_id, title):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO groups (chat_id, title, joined_at)
                 VALUES (%s, %s, %s)
                 ON CONFLICT (chat_id) DO UPDATE SET title=EXCLUDED.title""",
              (chat_id, title, int(time.time())))
    conn.commit(); c.close(); conn.close()

def inc_field(user_id, chat_id, field, amount=1):
    allowed = {"goose_calls", "gif_count", "sticker_count", "msg_count"}
    if field not in allowed:
        return
    conn = get_conn(); c = conn.cursor()
    c.execute(f"UPDATE users SET {field}={field}+%s WHERE user_id=%s AND chat_id=%s",
              (amount, user_id, chat_id))
    conn.commit(); c.close(); conn.close()

def get_user(user_id, chat_id):
    conn = get_conn(); c = conn.cursor(cursor_factory=RealDictCursor)
    c.execute("SELECT * FROM users WHERE user_id=%s AND chat_id=%s", (user_id, chat_id))
    row = c.fetchone(); c.close(); conn.close()
    return row

def get_coins(user_id, chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT coins FROM users WHERE user_id=%s AND chat_id=%s", (user_id, chat_id))
    row = c.fetchone(); c.close(); conn.close()
    return row[0] if row else 0

def add_coins(user_id, chat_id, amount):
    conn = get_conn(); c = conn.cursor()
    c.execute("UPDATE users SET coins=coins+%s WHERE user_id=%s AND chat_id=%s",
              (amount, user_id, chat_id))
    conn.commit(); c.close(); conn.close()

def is_blocked(user_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT 1 FROM blocked WHERE user_id=%s", (user_id,))
    r = c.fetchone(); c.close(); conn.close()
    return r is not None

def award_achievement(user_id, chat_id, title):
    conn = get_conn(); c = conn.cursor()
    c.execute("""INSERT INTO achievements (user_id, chat_id, title, awarded_at)
                 VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
              (user_id, chat_id, title, int(time.time())))
    inserted = c.rowcount > 0
    conn.commit(); c.close(); conn.close()
    return inserted

def get_achievements(user_id, chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT title FROM achievements WHERE user_id=%s AND chat_id=%s",
              (user_id, chat_id))
    rows = c.fetchall(); c.close(); conn.close()
    return [r[0] for r in rows]

def all_groups():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT chat_id, title FROM groups")
    rows = c.fetchall(); c.close(); conn.close()
    return rows

def get_shop(chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT item_name, price, description FROM shop WHERE chat_id=%s", (chat_id,))
    rows = c.fetchall(); c.close(); conn.close()
    return rows

def add_shop_item(chat_id, name, price, desc):
    conn = get_conn(); c = conn.cursor()
    c.execute("INSERT INTO shop (chat_id, item_name, price, description) VALUES (%s, %s, %s, %s)",
              (chat_id, name, price, desc))
    conn.commit(); c.close(); conn.close()

def del_shop_item(chat_id, name):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM shop WHERE chat_id=%s AND item_name=%s", (chat_id, name))
    n = c.rowcount; conn.commit(); c.close(); conn.close()
    return n

def buy_item(user_id, chat_id, item_name):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT price FROM shop WHERE chat_id=%s AND item_name=%s",
              (chat_id, item_name))
    row = c.fetchone()
    if not row:
        c.close(); conn.close(); return "not_found"
    price = row[0]
    c.execute("SELECT coins FROM users WHERE user_id=%s AND chat_id=%s", (user_id, chat_id))
    u = c.fetchone()
    if not u or u[0] < price:
        c.close(); conn.close(); return "no_money"
    c.execute("UPDATE users SET coins=coins-%s WHERE user_id=%s AND chat_id=%s",
              (price, user_id, chat_id))
    c.execute("""INSERT INTO purchases (user_id, chat_id, item_name, bought_at)
                 VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING""",
              (user_id, chat_id, item_name, int(time.time())))
    conn.commit(); c.close(); conn.close()
    return "ok"

def get_purchases(user_id, chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT item_name FROM purchases WHERE user_id=%s AND chat_id=%s",
              (user_id, chat_id))
    rows = c.fetchall(); c.close(); conn.close()
    return [r[0] for r in rows]

# ================== کلیدواژه‌ها ==================
def add_keyword(keyword, reply_text):
    keyword = keyword.strip()
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT id FROM keywords WHERE keyword=%s", (keyword,))
    exists = c.fetchone()
    if exists:
        c.execute("UPDATE keywords SET reply_text=%s WHERE keyword=%s",
                  (reply_text, keyword))
        conn.commit(); c.close(); conn.close()
        return "updated"
    else:
        c.execute("""INSERT INTO keywords (keyword, reply_text, created_at)
                     VALUES (%s, %s, %s)""",
                  (keyword, reply_text, int(time.time())))
        conn.commit(); c.close(); conn.close()
        return "added"

def del_keyword(keyword):
    conn = get_conn(); c = conn.cursor()
    c.execute("DELETE FROM keywords WHERE keyword=%s", (keyword.strip(),))
    n = c.rowcount; conn.commit(); c.close(); conn.close()
    return n

def list_keywords():
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT keyword, reply_text FROM keywords ORDER BY id")
    rows = c.fetchall(); c.close(); conn.close()
    return rows

def find_keyword(text):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT keyword, reply_text FROM keywords")
    rows = c.fetchall(); c.close(); conn.close()
    low = text.lower()
    for kw, reply in rows:
        if kw.lower() in low:
            return reply
    return None

def get_keyword_by_exact(keyword):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT reply_text FROM keywords WHERE keyword=%s", (keyword.strip(),))
    row = c.fetchone(); c.close(); conn.close()
    return row[0] if row else None

# ================== دستاوردها ==================
ACHIEVEMENTS = [
    ("gif_count", 20, "🎬 هتریک گیف"),
    ("gif_count", 50, "🎥 سلطان گیف"),
    ("sticker_count", 50, "🎨 استیکرباز"),
    ("msg_count", 100, "💬 پرحرف"),
    ("goose_calls", 20, "🪿 گوس‌باز حرفه‌ای"),
    ("goose_calls", 50, "🪿 عاشق Goose"),
    ("coins", 100, "💰 پولدار"),
    ("coins", 500, "💎 میلیونر"),
]

def check_achievements(user_id, chat_id):
    u = get_user(user_id, chat_id)
    if not u:
        return []
    values = {
        "goose_calls": u.get("goose_calls", 0),
        "gif_count": u.get("gif_count", 0),
        "sticker_count": u.get("sticker_count", 0),
        "msg_count": u.get("msg_count", 0),
        "coins": u.get("coins", 0),
    }
    new = []
    for field, threshold, title in ACHIEVEMENTS:
        if values.get(field, 0) >= threshold:
            if award_achievement(user_id, chat_id, title):
                new.append(title)
    return new

# ================== حالت‌ها ==================
MOODS = {
    "happy": {"سلام": "سلام رفیق! چه خبر خوب؟ 🎉", "خوبی": "من عالیم! تو چطوری؟ 😄", "خداحافظ": "بای بای! زود برگرد 🥰"},
    "serious": {"سلام": "سلام.", "خوبی": "خوبم.", "خداحافظ": "خداحافظ."},
    "funny": {"سلام": "سلام! چرا آدم‌ها اینقدر جدی‌ان 😂", "خوبی": "خوبم، ولی چرا پنگوئن‌ها پرواز نمی‌کنن؟ 🐧", "خداحافظ": "برو، دلم تنگ می‌شه 😜"},
    "angry": {"سلام": "چیه باز؟ 😒", "خوبی": "به تو چه.", "خداحافظ": "برو دیگه."},
    "kind": {"سلام": "سلام عزیزم 🥰", "خوبی": "خوبم مرسی که پرسیدی 💗", "خداحافظ": "مواظب خودت باش 🥺"},
}

def current_mood():
    return get_setting("mood", "happy")

def mood_reply(key):
    return MOODS.get(current_mood(), MOODS["happy"]).get(key)

def goose_call_reply(count):
    if count <= 3: return "دار آپدیت می‌شم جیگر"
    elif count <= 7: return "دوست داری ها 🪿"
    elif count <= 12: return "باز تو؟ 😏"
    elif count <= 19: return "کم کم داره ازت خوشم میاد..."
    else: return "عاشقتم دیگه 🥰"

# ================== API ==================
def send_message(chat_id, text, reply_markup=None, reply_to=None, parse_mode=None):
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode: payload["parse_mode"] = parse_mode
    if reply_markup: payload["reply_markup"] = reply_markup
    if reply_to: payload["reply_to_message_id"] = reply_to
    try:
        r = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
        res = r.json()
        if not res.get("ok") and parse_mode:
            print(f"[markdown failed] retry: {res}")
            payload.pop("parse_mode", None)
            r = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
            res = r.json()
        return res
    except Exception as e:
        print(f"[send error] {e}")
        return None

def send_photo(chat_id, photo, caption=None):
    payload = {"chat_id": chat_id, "photo": photo}
    if caption: payload["caption"] = caption
    try:
        r = requests.post(f"{API_URL}/sendPhoto", json=payload, timeout=15)
        return r.json()
    except Exception as e:
        print(f"[photo error] {e}")
        return None

def copy_message(to_chat, from_chat, msg_id, caption=None):
    payload = {"chat_id": to_chat, "from_chat_id": from_chat, "message_id": msg_id}
    if caption: payload["caption"] = caption
    try:
        r = requests.post(f"{API_URL}/copyMessage", json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[copy error] {e}")
        return False

def get_updates(offset=0):
    try:
        r = requests.get(f"{API_URL}/getUpdates",
                         params={"offset": offset, "timeout": 25}, timeout=30)
        return r.json()
    except Exception as e:
        print(f"[updates error] {e}")
        return {"ok": False, "result": []}

def answer_callback(cb_id, text=None):
    payload = {"callback_query_id": cb_id}
    if text: payload["text"] = text
    try:
        requests.post(f"{API_URL}/answerCallbackQuery", json=payload, timeout=10)
    except Exception as e:
        print(f"[cb error] {e}")

# ================== منوها ==================
def get_main_menu():
    return {"inline_keyboard": [
        [{"text": "🎓 امتحان‌ها", "callback_data": "menu_exams"},
         {"text": "📚 تکالیف", "callback_data": "menu_hw"}],
        [{"text": "💰 موجودی سکه", "callback_data": "menu_balance"},
         {"text": "🛒 فروشگاه", "callback_data": "menu_shop"}],
        [{"text": "🏆 دستاوردها", "callback_data": "menu_ach"},
         {"text": "🎒 خریدهای من", "callback_data": "menu_inv"}],
        [{"text": "🎮 بازی گروهی", "callback_data": "menu_game"}],
    ]}

def get_admin_menu():
    return {"inline_keyboard": [
        [{"text": "📊 آمار", "callback_data": "adm_stats"},
         {"text": "📝 گروه‌ها", "callback_data": "adm_groups"}],
        [{"text": "🎓 افزودن امتحان", "callback_data": "adm_add_exam"},
         {"text": "📚 افزودن تکلیف", "callback_data": "adm_add_hw"}],
        [{"text": "🗑 حذف امتحان", "callback_data": "adm_del_exam"},
         {"text": "🗑 حذف تکلیف", "callback_data": "adm_del_hw"}],
        [{"text": "📋 لیست امتحان", "callback_data": "adm_list_exam"},
         {"text": "📋 لیست تکلیف", "callback_data": "adm_list_hw"}],
        [{"text": "🔑 مدیریت کلیدواژه‌ها", "callback_data": "adm_kw_menu"}],
        [{"text": "🛒 افزودن به فروشگاه", "callback_data": "adm_shop_add"},
         {"text": "🗑 حذف از فروشگاه", "callback_data": "adm_shop_del"}],
        [{"text": "🎂 ثبت تولد", "callback_data": "adm_birthday"}],
        [{"text": "👋 متن خوش‌آمدگویی", "callback_data": "adm_welcome"}],
        [{"text": "📢 پیام همگانی", "callback_data": "adm_broadcast"}],
        [{"text": "🎭 حالت Goose", "callback_data": "adm_mood"},
         {"text": "🎁 دادن سکه", "callback_data": "adm_give_coin"}],
        [{"text": "🚫 بلاک", "callback_data": "adm_block"},
         {"text": "✅ رفع بلاک", "callback_data": "adm_unblock"}],
        [{"text": "🟢/🔴 روشن/خاموش", "callback_data": "adm_toggle"}],
    ]}

def get_kw_menu():
    return {"inline_keyboard": [
        [{"text": "➕ افزودن کلیدواژه", "callback_data": "adm_kw_add"}],
        [{"text": "📋 لیست کلیدواژه‌ها", "callback_data": "adm_kw_list"}],
        [{"text": "🗑 حذف کلیدواژه", "callback_data": "adm_kw_del"}],
        [{"text": "🔙 بازگشت", "callback_data": "adm_back"}],
    ]}

def get_mood_menu():
    return {"inline_keyboard": [
        [{"text": "😄 شاد", "callback_data": "mood_happy"},
         {"text": "😐 جدی", "callback_data": "mood_serious"}],
        [{"text": "😜 طنز", "callback_data": "mood_funny"},
         {"text": "😠 عصبانی", "callback_data": "mood_angry"}],
        [{"text": "🥰 مهربون", "callback_data": "mood_kind"}],
        [{"text": "🔙 بازگشت", "callback_data": "adm_back"}],
    ]}

def get_game_menu():
    return {"inline_keyboard": [
        [{"text": "🎲 تاس گروهی", "callback_data": "game_dice"}],
        [{"text": "🪙 شیر یا خط", "callback_data": "game_coin"}],
        [{"text": "🔢 حدس عدد", "callback_data": "game_guess"}],
        [{"text": "🧩 چیستان", "callback_data": "game_riddle"}],
    ]}

# ================== چیستان ==================
RIDDLES = [
    ("چیست که هر چه از آن بگیری بزرگ‌تر می‌شود؟", "چاله"),
    ("چیست که وقتی پر است خالی است؟", "کفش"),
    ("چیست که سر دارد اما مو ندارد؟", "کبریت"),
    ("چیست که همیشه می‌آید ولی هیچ‌وقت نمی‌رسد؟", "فردا"),
    ("چیست که وقتی شکسته می‌شود صدا ندارد؟", "قلب"),
    ("چیست که خودش می‌رود ولی جای پا نمی‌گذارد؟", "باد"),
    ("چیست که شما می‌بینید اما خودش نمی‌بیند؟", "آینه"),
    ("چیست که هر چه بیشتر بدوی، کمتر می‌رسی؟", "سایه"),
    ("چیست که در آب می‌افتد ولی خیس نمی‌شود؟", "نور"),
    ("چیست که دو تا پا دارد ولی راه نمی‌رود؟", "صندلی"),
]

# ================== راهنما ==================
def send_help(chat_id):
    text = (
        "🪿 راهنمای کامل Goose v4.0\n\n"
        "🎮 سرگرمی:\n"
        "• dark_goose — منوی کامل\n"
        "• Goose یا گوس — 💰 ۱ سکه\n"
        "• Goose بازی — بازی گروهی\n\n"
        "💰 اقتصاد:\n"
        "• /balance — موجودی سکه\n"
        "• /shop — فروشگاه\n"
        "• /buy اسم — خرید\n"
        "• /inv — خریدهای من\n\n"
        "🏆 دستاوردها:\n"
        "• Goose دستاوردها\n\n"
        "📞 ادمین: /admin توی PV\n"
        "• /help_gose — همین راهنما"
    )
    send_message(chat_id, text)

# ================== PV ادمین ==================
def handle_admin_pv(message):
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()
    photo = message.get("photo")
    reply_to = message.get("reply_to_message")
    state = admin_state.get(chat_id)

    if state:
        t = state.get("type")
        target = state.get("chat_id") or (all_groups()[0][0] if all_groups() else None)

        if t == "add_exam":
            parts = text.split("—")
            if len(parts) != 2:
                send_message(chat_id, "❌ فرمت: موضوع — تاریخ")
                return
            conn = get_conn(); c = conn.cursor()
            c.execute("INSERT INTO exams (chat_id, subject, exam_date) VALUES (%s, %s, %s)",
                      (target, parts[0].strip(), parts[1].strip()))
            conn.commit(); c.close(); conn.close()
            send_message(chat_id, "✅ امتحان اضافه شد.")
            admin_state.pop(chat_id, None)

        elif t == "add_hw":
            parts = text.split("—")
            if len(parts) != 2:
                send_message(chat_id, "❌ فرمت: موضوع — توضیح")
                return
            conn = get_conn(); c = conn.cursor()
            c.execute("INSERT INTO homeworks (chat_id, subject, description) VALUES (%s, %s, %s)",
                      (target, parts[0].strip(), parts[1].strip()))
            conn.commit(); c.close(); conn.close()
            send_message(chat_id, "✅ تکلیف اضافه شد.")
            admin_state.pop(chat_id, None)

        elif t == "del_exam":
            conn = get_conn(); c = conn.cursor()
            c.execute("DELETE FROM exams WHERE chat_id=%s AND subject=%s",
                      (target, text.strip()))
            n = c.rowcount; conn.commit(); c.close(); conn.close()
            send_message(chat_id, f"🗑 {n} حذف شد.")
            admin_state.pop(chat_id, None)

        elif t == "del_hw":
            conn = get_conn(); c = conn.cursor()
            c.execute("DELETE FROM homeworks WHERE chat_id=%s AND subject=%s",
                      (target, text.strip()))
            n = c.rowcount; conn.commit(); c.close(); conn.close()
            send_message(chat_id, f"🗑 {n} حذف شد.")
            admin_state.pop(chat_id, None)

        elif t == "kw_add_keyword":
            state["keyword"] = text
            state["type"] = "kw_add_reply"
            send_message(chat_id,
                f"✅ کلیدواژه: «{text}»\n\n"
                f"حالا متن کامل جواب رو بفرست.\n"
                f"می‌تونی از ایموجی و خط جدید استفاده کنی.")
            return

        elif t == "kw_add_reply":
            kw = state.get("keyword")
            result = add_keyword(kw, text)
            if result == "updated":
                send_message(chat_id, f"♻️ کلیدواژه «{kw}» آپدیت شد.")
            else:
                send_message(chat_id, f"✅ کلیدواژه «{kw}» ذخیره شد.")
            admin_state.pop(chat_id, None)
            return

        elif t == "kw_del":
            n = del_keyword(text)
            send_message(chat_id, f"🗑 {n} کلیدواژه حذف شد.")
            admin_state.pop(chat_id, None)

        elif t == "shop_add":
            parts = text.split("—")
            if len(parts) != 3:
                send_message(chat_id, "❌ فرمت: اسم — قیمت — توضیح")
                return
            name, price, desc = parts[0].strip(), parts[1].strip(), parts[2].strip()
            try:
                price = int(price)
            except:
                send_message(chat_id, "❌ قیمت باید عدد باشه")
                return
            add_shop_item(target, name, price, desc)
            send_message(chat_id, f"✅ «{name}» اضافه شد.")
            admin_state.pop(chat_id, None)

        elif t == "shop_del":
            n = del_shop_item(target, text.strip())
            send_message(chat_id, f"🗑 {n} آیتم حذف شد.")
            admin_state.pop(chat_id, None)

        elif t == "birthday":
            parts = text.split("—")
            if len(parts) != 2:
                send_message(chat_id, "❌ فرمت: آیدی — تاریخ")
                return
            try:
                uid = int(parts[0].strip())
            except:
                send_message(chat_id, "❌ آیدی عددی")
                return
            conn = get_conn(); c = conn.cursor()
            c.execute("UPDATE users SET birthday=%s WHERE user_id=%s",
                      (parts[1].strip(), uid))
            conn.commit(); c.close(); conn.close()
            send_message(chat_id, "✅ تولد ثبت شد.")
            admin_state.pop(chat_id, None)

        elif t == "welcome":
            set_setting("welcome_text", text)
            send_message(chat_id, "✅ ذخیره شد.")
            admin_state.pop(chat_id, None)

        elif t == "broadcast":
            groups = all_groups()
            sent = 0
            if photo:
                caption = message.get("caption") or ""
                file_id = photo[-1]["file_id"]
                for g, _ in groups:
                    if send_photo(g, file_id, caption): sent += 1
            elif reply_to:
                mid = reply_to["message_id"]
                for g, _ in groups:
                    if copy_message(g, chat_id, mid): sent += 1
            else:
                for g, _ in groups:
                    if send_message(g, text): sent += 1
            send_message(chat_id, f"✅ به {sent} گروه ارسال شد.")
            admin_state.pop(chat_id, None)

        elif t == "give_coin":
            parts = text.split("—")
            if len(parts) != 2:
                send_message(chat_id, "❌ فرمت: آیدی — تعداد")
                return
            try:
                uid, amount = int(parts[0].strip()), int(parts[1].strip())
            except:
                send_message(chat_id, "❌ اعداد درست بفرست")
                return
            conn = get_conn(); c = conn.cursor()
            c.execute("UPDATE users SET coins=coins+%s WHERE user_id=%s", (amount, uid))
            conn.commit(); c.close(); conn.close()
            send_message(chat_id, f"✅ {amount} سکه داده شد.")
            admin_state.pop(chat_id, None)

        elif t == "block":
            try:
                uid = int(text.strip())
            except:
                send_message(chat_id, "❌ آیدی عددی"); return
            conn = get_conn(); c = conn.cursor()
            c.execute("INSERT INTO blocked (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
            conn.commit(); c.close(); conn.close()
            send_message(chat_id, "🚫 بلاک شد.")
            admin_state.pop(chat_id, None)

        elif t == "unblock":
            try:
                uid = int(text.strip())
            except:
                send_message(chat_id, "❌ آیدی عددی"); return
            conn = get_conn(); c = conn.cursor()
            c.execute("DELETE FROM blocked WHERE user_id=%s", (uid,))
            conn.commit(); c.close(); conn.close()
            send_message(chat_id, "✅ رفع بلاک شد.")
            admin_state.pop(chat_id, None)
        return

    if text in ("/admin", "admin", "پنل"):
        send_message(chat_id, "🪿 پنل ادمین:", get_admin_menu())
        return
    if text == "/help_gose":
        send_help(chat_id)
        return
    send_message(chat_id, "دستور نامشخص. برای پنل: /admin")

# ================== Callback ==================
def handle_callback(cb):
    data = cb.get("data", "")
    chat_id = cb.get("message", {}).get("chat", {}).get("id")
    chat_type = cb.get("message", {}).get("chat", {}).get("type")
    user = cb.get("from", {})
    uid = user.get("id")
    username = (user.get("username") or "").lower()
    first_name = user.get("first_name") or ""
    is_admin = username == ADMIN_USERNAME.lower()
    is_pv = chat_type == "private"

    # منوی گروه
    if data == "menu_exams": send_exam_list(chat_id)
    elif data == "menu_hw": send_hw_list(chat_id)
    elif data == "menu_balance":
        send_message(chat_id, f"💰 موجودی: {get_coins(uid, chat_id)} سکه")
    elif data == "menu_shop":
        items = get_shop(chat_id)
        if not items:
            send_message(chat_id, "🛒 فروشگاه خالیه.")
        else:
            txt = "🛒 فروشگاه:\n"
            for name, price, desc in items:
                txt += f"• {name} — {price} سکه\n  {desc}\n"
            send_message(chat_id, txt)
    elif data == "menu_ach":
        achs = get_achievements(uid, chat_id)
        send_message(chat_id, "🏆 " + ("\n".join(achs) if achs else "هنوز نداری."))
    elif data == "menu_inv":
        inv = get_purchases(uid, chat_id)
        send_message(chat_id, "🎒 " + (", ".join(inv) if inv else "چیزی نخریدی."))
    elif data == "menu_game":
        send_message(chat_id, "🎮 بازی:", get_game_menu())

    # بازی
    elif data == "game_dice":
        n = random.randint(1, 6)
        add_coins(uid, chat_id, 1)
        send_message(chat_id, f"🎲 {first_name}: {n}\n💰 +1 سکه")
    elif data == "game_coin":
        r = random.choice(["شیر 🦁", "خط ✖️"])
        add_coins(uid, chat_id, 1)
        send_message(chat_id, f"🪙 {r}\n💰 +1 سکه")
    elif data == "game_guess":
        target = random.randint(1, 100)
        conn = get_conn(); c = conn.cursor()
        c.execute("""INSERT INTO game_sessions (chat_id, game_type, state, started_at)
                     VALUES (%s, %s, %s, %s)
                     ON CONFLICT (chat_id) DO UPDATE SET game_type=EXCLUDED.game_type,
                     state=EXCLUDED.state, started_at=EXCLUDED.started_at""",
                  (chat_id, "guess", str(target), int(time.time())))
        conn.commit(); c.close(); conn.close()
        send_message(chat_id, "🔢 یه عدد ۱ تا ۱۰۰ انتخاب کردم! اولین درست = ۱۰ سکه")
    elif data == "game_riddle":
        riddle, answer = random.choice(RIDDLES)
        conn = get_conn(); c = conn.cursor()
        c.execute("""INSERT INTO game_sessions (chat_id, game_type, state, started_at)
                     VALUES (%s, %s, %s, %s)
                     ON CONFLICT (chat_id) DO UPDATE SET game_type=EXCLUDED.game_type,
                     state=EXCLUDED.state, started_at=EXCLUDED.started_at""",
                  (chat_id, "riddle", answer, int(time.time())))
        conn.commit(); c.close(); conn.close()
        send_message(chat_id, f"🧩 {riddle}\n\nاولین جواب درست: ۱۰ سکه!")

    # پنل ادمین
    elif data.startswith("adm_") and is_admin and is_pv:
        handle_admin_cb(data, chat_id, user)
    elif data.startswith("mood_") and is_admin and is_pv:
        m = data.replace("mood_", "")
        set_setting("mood", m)
        names = {"happy":"😄 شاد","serious":"😐 جدی","funny":"😜 طنز","angry":"😠 عصبانی","kind":"🥰 مهربون"}
        send_message(chat_id, f"✅ حالت: {names.get(m, m)}")

    answer_callback(cb["id"])

def handle_admin_cb(data, chat_id, user):
    target = all_groups()[0][0] if all_groups() else None
    if data == "adm_back": send_message(chat_id, "🪿 پنل:", get_admin_menu())
    elif data == "adm_stats":
        conn = get_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM groups"); g = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM users"); u = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM exams"); e = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM homeworks"); h = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM keywords"); k = c.fetchone()[0]
        c.close(); conn.close()
        send_message(chat_id, f"📊 گروه:{g} | کاربر:{u} | امتحان:{e} | تکلیف:{h} | کلیدواژه:{k}")
    elif data == "adm_groups":
        gs = all_groups()
        send_message(chat_id, "\n".join([f"• {t} ({cc})" for cc, t in gs]) if gs else "هیچ گروهی نیست.")
    elif data == "adm_add_exam":
        admin_state[chat_id] = {"type": "add_exam", "chat_id": target}
        send_message(chat_id, "🎓 فرمت: موضوع — تاریخ")
    elif data == "adm_add_hw":
        admin_state[chat_id] = {"type": "add_hw", "chat_id": target}
        send_message(chat_id, "📚 فرمت: موضوع — توضیح")
    elif data == "adm_del_exam":
        admin_state[chat_id] = {"type": "del_exam", "chat_id": target}
        send_message(chat_id, "🗑 اسم موضوع:")
    elif data == "adm_del_hw":
        admin_state[chat_id] = {"type": "del_hw", "chat_id": target}
        send_message(chat_id, "🗑 اسم موضوع:")
    elif data == "adm_list_exam": send_exam_list(chat_id)
    elif data == "adm_list_hw": send_hw_list(chat_id)

    # ======== کلیدواژه‌ها ========
    elif data == "adm_kw_menu":
        send_message(chat_id, "🔑 مدیریت کلیدواژه‌ها:", get_kw_menu())
    elif data == "adm_kw_add":
        admin_state[chat_id] = {"type": "kw_add_keyword"}
        send_message(chat_id,
            "🔑 کلیدواژه رو بفرست (کلمه‌ای که Goose وقتی شنید جواب بده).\n"
            "مثال: امتحان چی داریم")
    elif data == "adm_kw_del":
        admin_state[chat_id] = {"type": "kw_del"}
        send_message(chat_id, "🗑 کلیدواژه‌ای که می‌خوای حذف شه رو بفرست:")
    elif data == "adm_kw_list":
        kws = list_keywords()
        if not kws:
            send_message(chat_id, "هیچ کلیدواژه‌ای نیست.")
        else:
            txt = "📋 کلیدواژه‌ها:\n\n"
            for i, (kw, reply) in enumerate(kws, 1):
                preview = reply[:80].replace("\n", " ")
                txt += f"{i}. 🔑 {kw}\n   ↳ {preview}...\n\n"
            send_message(chat_id, txt)

    elif data == "adm_shop_add":
        admin_state[chat_id] = {"type": "shop_add", "chat_id": target}
        send_message(chat_id, "🛒 فرمت: اسم — قیمت — توضیح")
    elif data == "adm_shop_del":
        admin_state[chat_id] = {"type": "shop_del", "chat_id": target}
        send_message(chat_id, "🗑 اسم آیتم:")
    elif data == "adm_birthday":
        admin_state[chat_id] = {"type": "birthday"}
        send_message(chat_id, "🎂 فرمت: آیدی — تاریخ (1370/05/15)")
    elif data == "adm_welcome":
        admin_state[chat_id] = {"type": "welcome"}
        send_message(chat_id, "👋 متن خوش‌آمدگویی:")
    elif data == "adm_broadcast":
        admin_state[chat_id] = {"type": "broadcast"}
        send_message(chat_id, "📢 متن/عکس/ریپلای:")
    elif data == "adm_mood":
        send_message(chat_id, f"🎭 حالت فعلی: {current_mood()}", get_mood_menu())
    elif data == "adm_give_coin":
        admin_state[chat_id] = {"type": "give_coin"}
        send_message(chat_id, "🎁 فرمت: آیدی — تعداد")
    elif data == "adm_block":
        admin_state[chat_id] = {"type": "block"}
        send_message(chat_id, "🚫 آیدی عددی:")
    elif data == "adm_unblock":
        admin_state[chat_id] = {"type": "unblock"}
        send_message(chat_id, "✅ آیدی عددی:")
    elif data == "adm_toggle":
        global bot_active
        bot_active = not bot_active
        send_message(chat_id, f"{'🟢 فعال' if bot_active else '🔴 خاموش'}")

def send_exam_list(chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT subject, exam_date FROM exams WHERE chat_id=%s", (chat_id,))
    rows = c.fetchall(); c.close(); conn.close()
    if not rows:
        send_message(chat_id, "🎓 امتحانی ثبت نشده.")
    else:
        send_message(chat_id, "🎓 امتحان‌ها:\n" + "\n".join([f"• {s} → {d}" for s, d in rows]))

def send_hw_list(chat_id):
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT subject, description FROM homeworks WHERE chat_id=%s", (chat_id,))
    rows = c.fetchall(); c.close(); conn.close()
    if not rows:
        send_message(chat_id, "📚 تکلیفی ثبت نشده.")
    else:
        send_message(chat_id, "📚 تکالیف:\n" + "\n".join([f"• {s} → {d}" for s, d in rows]))

# ================== هندل پیام ==================
def handle_message(message):
    global bot_active
    chat = message.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    text = (message.get("text") or "").strip()
    user = message.get("from", {})
    uid = user.get("id")
    username = (user.get("username") or "").lower()
    first_name = user.get("first_name") or ""
    is_admin = username == ADMIN_USERNAME.lower()

    print(f"[msg] {chat_type} @{username}: {text[:50]}")

    # خوش‌آمدگویی
    if chat_type in ("group", "supergroup") and message.get("new_chat_members"):
        ensure_group(chat_id, chat.get("title") or "")
        welcome = get_setting("welcome_text", "🎉 خوش اومدی به گروه!")
        for m in message["new_chat_members"]:
            if m.get("is_bot"): continue
            send_message(chat_id, f"👋 {m.get('first_name','')} عزیز، {welcome}")
        return

    # PV ادمین
    if chat_type == "private":
        if is_admin: handle_admin_pv(message)
        else: send_message(chat_id, "🪿 فقط توی گروه‌ها کار می‌کنم.")
        return

    if chat_type in ("group", "supergroup"):
        ensure_group(chat_id, chat.get("title") or "")

    # فعال‌سازی
    if text == RUN_COMMAND:
        if not is_admin: return
        bot_active = True
        send_message(chat_id, "🪿 Goose فعال شد! v4.0")
        return

    if not bot_active: return
    if uid and is_blocked(uid): return

    # ثبت کاربر
    if uid:
        ensure_user(uid, chat_id, username, first_name)
        inc_field(uid, chat_id, "msg_count")
        if message.get("animation"): inc_field(uid, chat_id, "gif_count")
        if message.get("sticker"): inc_field(uid, chat_id, "sticker_count")
        for t in check_achievements(uid, chat_id):
            send_message(chat_id, f"🏆 {first_name} دستاورد گرفت: {t}")

    # کلیدواژه‌های ادمین (اولویت بالا)
    if text and not text.startswith("/"):
        kw_reply = find_keyword(text)
        if kw_reply:
            send_message(chat_id, kw_reply)
            return

    # راهنما
    if text == "/help_gose":
        send_help(chat_id); return

    # موجودی
    if text == "/balance":
        send_message(chat_id, f"💰 {first_name}: {get_coins(uid, chat_id)} سکه"); return

    # فروشگاه
    if text == "/shop":
        items = get_shop(chat_id)
        if not items: send_message(chat_id, "🛒 فروشگاه خالیه.")
        else:
            txt = "🛒 فروشگاه:\n"
            for n, p, d in items: txt += f"• {n} — {p} سکه\n  {d}\n"
            send_message(chat_id, txt)
        return

    # خرید
    if text.startswith("/buy "):
        item = text[5:].strip()
        result = buy_item(uid, chat_id, item)
        if result == "ok": send_message(chat_id, f"✅ «{item}» خریدی!")
        elif result == "no_money": send_message(chat_id, "❌ سکه کافی نداری.")
        else: send_message(chat_id, "❌ این آیتم نیست.")
        return

    if text == "/inv":
        inv = get_purchases(uid, chat_id)
        send_message(chat_id, "🎒 " + (", ".join(inv) if inv else "چیزی نخریدی."))
        return

    # منو
    if text.lower() == MENU_COMMAND:
        send_message(chat_id, "🪿 منوی Goose:", get_main_menu()); return

    # بازی
    if text in ("Goose بازی", "بازی"):
        send_message(chat_id, "🎮 بازی:", get_game_menu()); return

    # امتحان/تکلیف
    if "امتحان" in text and ("goose" in text.lower() or "گوس" in text.lower()):
        send_exam_list(chat_id); return
    if "تکلیف" in text and ("goose" in text.lower() or "گوس" in text.lower()):
        send_hw_list(chat_id); return
    if "دستاورد" in text and ("goose" in text.lower() or "گوس" in text.lower()):
        achs = get_achievements(uid, chat_id)
        send_message(chat_id, "🏆 " + ("\n".join(achs) if achs else "هنوز نداری.")); return

    # چک بازی
    conn = get_conn(); c = conn.cursor()
    c.execute("SELECT game_type, state FROM game_sessions WHERE chat_id=%s", (chat_id,))
    gs = c.fetchone(); c.close(); conn.close()
    if gs and text:
        gt, st = gs
        if gt == "guess":
            try:
                n = int(text)
                if n == int(st):
                    add_coins(uid, chat_id, 10)
                    send_message(chat_id, f"🎉 {first_name} درست گفت! +10 سکه")
                    conn = get_conn(); c = conn.cursor()
                    c.execute("DELETE FROM game_sessions WHERE chat_id=%s", (chat_id,))
                    conn.commit(); c.close(); conn.close()
                    return
                elif n < int(st):
                    send_message(chat_id, "⬆️ بالاتره"); return
                else:
                    send_message(chat_id, "⬇️ پایین‌تره"); return
            except: pass
        if gt == "riddle":
            if st.lower() in text.lower():
                add_coins(uid, chat_id, 10)
                send_message(chat_id, f"🎉 {first_name} درست گفت! +10 سکه")
                conn = get_conn(); c = conn.cursor()
                c.execute("DELETE FROM game_sessions WHERE chat_id=%s", (chat_id,))
                conn.commit(); c.close(); conn.close()
                return

    # پاسخ‌های هوشمند
    if "سلام" in text:
        send_message(chat_id, mood_reply("سلام")); return
    if "خوبی" in text or "چطوری" in text:
        send_message(chat_id, mood_reply("خوبی")); return
    if "خداحافظ" in text or "بای" in text:
        send_message(chat_id, mood_reply("خداحافظ")); return

    # صدا زدن Goose → سکه
    lower = text.lower()
    if "goose" in lower or "گوس" in lower:
        if uid:
            inc_field(uid, chat_id, "goose_calls")
            add_coins(uid, chat_id, 1)
            u = get_user(uid, chat_id)
            calls = u.get("goose_calls", 1) if u else 1
            send_message(chat_id, f"{goose_call_reply(calls)}\n💰 +1 سکه")
            for t in check_achievements(uid, chat_id):
                send_message(chat_id, f"🏆 {first_name} دستاورد گرفت: {t}")

# ================== حلقه ==================
def bot_loop():
    global bot_active, last_update_id
    print("🪿 Goose v4.0 started")
    try:
        me = requests.get(f"{API_URL}/getMe", timeout=10).json()
        print(f"[getMe] {me}")
    except Exception as e:
        print(f"[getMe error] {e}")

    while True:
        data = get_updates(last_update_id + 1)
        if not data.get("ok"):
            time.sleep(3); continue
        for update in data.get("result", []):
            last_update_id = update["update_id"]
            cb = update.get("callback_query")
            if cb: handle_callback(cb); continue
            msg = update.get("message")
            if msg: handle_message(msg)

# ================== Flask ==================
app = Flask(__name__)

@app.route("/")
def index(): return "Goose v4.0 (PostgreSQL) 🪿"

@app.route("/health")
def health(): return "OK"

if __name__ == "__main__":
    init_db()
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
