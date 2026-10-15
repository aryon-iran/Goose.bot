import os
import threading
import asyncio
from flask import Flask
from baleio import Bot, Dispatcher
from baleio.filters import Command

# ===== تنظیمات =====
TOKEN = os.environ.get("BALE_BOT_TOKEN")   # از متغیرهای محیطی Render خوانده می‌شود
ADMIN_USERNAME = "aryon_admin"              # با حروف کوچک، بله معمولاً case-insensitive است
RUN_COMMAND = "Run_goose_dark"

# ===== وضعیت داخلی =====
bot_active = False
user_call_counts = {}

dp = Dispatcher()

@dp.message(Command(RUN_COMMAND))
async def run_goose(message):
    global bot_active
    if message.from_user.username != ADMIN_USERNAME:
        return
    if bot_active:
        await message.answer("Goose از قبل فعاله جیگر 🪿")
        return
    bot_active = True
    await message.answer("🪿 Goose فعال شد! من Goose هستم، می‌تونی منو این شکلی صدا کنی ولی اذیتم نکن v1.4")

@dp.message()
async def goose_listener(message):
    global bot_active
    if not bot_active:
        return
    text = (message.text or "").lower()
    if "goose" in text or "گوس" in text:
        user_id = message.from_user.id
        user_call_counts[user_id] = user_call_counts.get(user_id, 0) + 1
        if user_call_counts[user_id] > 3:
            await message.answer("دوست داری ها 🪿")
        else:
            await message.answer("دار آپدیت می‌شم جیگر")

# ===== راه‌اندازی bot در thread پس‌زمینه =====
def run_bot():
    asyncio.run(start_bot())

async def start_bot():
    bot = Bot(token=TOKEN)
    await dp.start_polling(bot)

# ===== سرور Flask برای اشغال پورت =====
app = Flask(__name__)

@app.route("/")
def index():
    return "Goose is running 🪿"

@app.route("/health")
def health():
    return "OK"

if __name__ == "__main__":
    # راه‌اندازی bot در thread پس‌زمینه
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    # Flask پورت Render را اشغال می‌کند
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
