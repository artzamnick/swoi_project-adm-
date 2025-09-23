import os
import re
import asyncio
import logging
from typing import Dict, Optional

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

# ---------- ЛОГИ ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("admin_bot")

# ---------- ENV ----------
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not BOT_TOKEN or " " in BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не знайдено або містить пробіли. Додай у Railway → Service → Variables.")

ADMIN_USER_ID_RAW = (os.getenv("ADMIN_USER_ID") or "").strip()
try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_RAW)
except Exception:
    ADMIN_USER_ID = None
    log.warning("⚠️ ADMIN_USER_ID не задано. Надішли /id боту й додай ADMIN_USER_ID у Railway.")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# message_id у чаті адміна → user_id користувача (живе в пам'яті процесу)
ROUTE: Dict[int, int] = {}

# ---------- ТЕКСТИ / КНОПКИ ----------
WELCOME_TEXT = (
    "🤖 Привіт! Ти в чаті з адмінами\n"
    "🍓🔞 SWої люди: Клуб України 🔞🍓🇺🇦\n\n"
    "В першому повідомлені вкажи причину звернення:\n\n"
    "[РОЗБАН] — зняти бан/блок\n"
    "[ПОЗАЧЕРГОВО] — опублікувати оголошення поза чергою\n"
    "[РЕКЛАМА] — замовити рекламу на каналі\n"
    "[ІНШЕ] — співпраця або будь-які інші питання до адмінів\n\n"
    "⚠️ Увага: форму привітання сюди надсилати не потрібно.\n"
    "👉 Вітання залишай у гостьовому чаті, а тут лише звернення до адмінів."
)

PROJECTS = [
    ("📝 Блог в Telegram", "https://t.me/joinchat/6jJS6kpFh6dhMDIy"),
    ("📌 Дошка оголошень", "https://t.me/joinchat/AAAAAEtVgqgxtKQ-MxwMMw"),
    ("🌶 SWOI-Shop", "http://t.me/swoishop"),
    ("✉️ Гостьовий чат", "https://t.me/joinchat/pMIwfwXDcEQxNTNi"),
    ("📸 Контент-чат", "https://t.me/+3gPoOsKhGF8zZWRi"),
    ("📝 Instagram блог", "https://instagram.com/esmeralda_kissa"),
    ("📽️ Фільмотека кіно", "https://t.me/swoi_kino"),
    ("🚕 SWої Taxi/Bla-blaCar", "https://t.me/+bfqsxj8G3-0xZjNi"),
    ("☠️ Чат-анархія", "https://t.me/komenty_swoih"),
    ("✌️ Резервний чат в Signal",
     "https://signal.group/#CjQKIMLrwXMW3n_zvvA_vQsIh5wuSvKpb9SoDXD8KwOJJl7FEhA-5oVc-cdP00VFwuLF1IRG"),
    ("💵 Донат «SWої Люди UA»", "https://t.me/swoi_donate_bot"),
]

def start_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📂 Список проєктів", callback_data="show:projects")
    return kb.as_markup()

def projects_kb():
    kb = InlineKeyboardBuilder()
    for name, url in PROJECTS:
        kb.button(text=name, url=url)
    kb.adjust(1)
    return kb.as_markup()

UID_PATTERNS = [
    re.compile(r"UID:\s*(\d+)"),
    re.compile(r"user_id\s*=\s*<code>(\d+)</code>"),
    re.compile(r"tg://user\?id=(\d+)"),
    re.compile(r"\bID[:=]\s*(\d+)\b"),
]

def extract_uid_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    for pat in UID_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                continue
    return None

# ---------- БАЗОВІ КОМАНДИ ----------
@dp.message()
async def router(m: Message):
    """
    Єдиний «надійний» роутер:
    - ловимо всі повідомлення
    - всередині розгалужуємо сценарії
    """
    # Безпечні значення
    chat_type = getattr(m.chat, "type", None)
    from_id = getattr(m.from_user, "id", None)

    # /start, /id, кнопки
    if m.text == "/start":
        await m.answer(WELCOME_TEXT, reply_markup=start_kb())
        return
    if m.text == "/id":
        await m.reply(f"chat_id = <code>{m.chat.id}</code>\nuser_id = <code>{from_id}</code>")
        return

    # CallbackQuery тут не прилетить, але тримаємо кнопки через окремий handler:
    # (див. нижче on_callback)

    # 1) КОРИСТУВАЧ → АДМІН (приват не від адміна)
    if chat_type == "private" and ADMIN_USER_ID and from_id != ADMIN_USER_ID:
        u = m.from_user
        uid_line = f"UID: {u.id}"  # явний рядок для фолбеку
        header = (
            "📥 <b>Нове звернення</b>\n"
            f"👤 {u.full_name} @{u.username or '—'}\n"
            f"🆔 <code>{u.id}</code>\n"
            f"{uid_line}\n"
            f"🔗 <a href='tg://user?id={u.id}'>відкрити профіль</a>\n\n"
            "✍️ Відповідай <b>реплаєм</b> на <b>шапку або копію</b> нижче — я перешлю користувачу."
        )
        head_msg = await bot.send_message(ADMIN_USER_ID, header, disable_web_page_preview=True)
        copy_msg = await m.copy_to(ADMIN_USER_ID)

        ROUTE[head_msg.message_id] = u.id
        ROUTE[copy_msg.message_id] = u.id
        log.info("Route saved head=%s copy=%s -> user=%s", head_msg.message_id, copy_msg.message_id, u.id)
        return

    # 2) АДМІН → КОРИСТУВАЧ (приват від адміна І це відповідь)
    if chat_type == "private" and ADMIN_USER_ID and from_id == ADMIN_USER_ID and m.reply_to_message:
        reply_to_id = m.reply_to_message.message_id
        user_id = ROUTE.get(reply_to_id)

        if not user_id:
            # Фолбек: спроба дістати UID з тексту/підпису повідомлення, на яке відповідаємо (шапка)
            src_text = (m.reply_to_message.text or "") + "\n" + (m.reply_to_message.caption or "")
            user_id = extract_uid_from_text(src_text)
            if user_id:
                log.info("Fallback UID parsed: %s", user_id)

        if not user_id:
            await m.reply("ℹ️ Не знайшов одержувача. Відповідай саме на шапку/копію останнього звернення (де є рядок «UID: …»).")
            log.warning("No route/UID for admin reply. reply_to_id=%s", reply_to_id)
            return

        try:
            if m.text:
                await bot.send_message(user_id, f"✉️ <b>Від адміна</b>:\n{m.text}")
            else:
                await m.copy_to(user_id)  # фото/відео/док
            await m.reply("✅ Відповідь надіслана.")
            log.info("Reply delivered to user %s", user_id)
        except Exception as e:
            log.exception("Send fail to user %s: %s", user_id, e)
            await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")
        return

    # 3) Інше — ігноруємо тихо
    # (наприклад, приват адміна без реплая, або групові чати тощо)
    return

@dp.callback_query()
async def on_callback(cb: CallbackQuery):
    # єдина кнопка — «Список проєктів»
    if cb.data == "show:projects":
        try:
            await cb.answer()
        except Exception:
            pass
        kb = projects_kb()
        await cb.message.answer("📂 Наші проєкти:", reply_markup=kb)

# ---------- ЗАПУСК ----------
async def main():
    print("✅ Admin relay bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
