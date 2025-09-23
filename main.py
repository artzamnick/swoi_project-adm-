import os
import re
import asyncio
import logging
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F
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
    log.warning("⚠️ ADMIN_USER_ID не задано. Надішли /id боту і додай ADMIN_USER_ID у Railway.")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# admin_msg_id -> user_id
ROUTE: Dict[int, int] = {}

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
                pass
    return None

# ---------- КОМАНДИ ----------
@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer(WELCOME_TEXT, reply_markup=start_kb())

@dp.callback_query(F.data == "show:projects")
async def show_projects(cb: CallbackQuery):
    try:
        await cb.answer()
    except Exception:
        pass
    await cb.message.answer("📂 Наші проєкти:", reply_markup=projects_kb())

@dp.message(F.text == "/id")
async def cmd_id(m: Message):
    await m.reply(f"chat_id = <code>{m.chat.id}</code>\nuser_id = <code>{m.from_user.id}</code>")

# ---------- КОРИСТУВАЧ → АДМІН ----------
@dp.message(F.chat.type == "private")
async def from_user(m: Message):
    if ADMIN_USER_ID and m.from_user.id == ADMIN_USER_ID:
        # адмін пише в бота — ігноруємо як звернення
        return
    if ADMIN_USER_ID is None:
        await m.answer("⚠️ Бот ще не налаштований: ADMIN_USER_ID відсутній.")
        return

    u = m.from_user
    uid_line = f"UID: {u.id}"
    header = (
        "📥 <b>Нове звернення</b>\n"
        f"👤 {u.full_name} @{u.username or '—'}\n"
        f"🆔 <code>{u.id}</code>\n"
        f"{uid_line}\n"
        f"🔗 <a href='tg://user?id={u.id}'>відкрити профіль</a>\n\n"
        "✍️ Відповідай <b>реплаєм</b> на <b>шапку</b> або <b>копію</b> — я перешлю користувачу."
    )

    head_msg = await bot.send_message(ADMIN_USER_ID, header, disable_web_page_preview=True)
    copy_msg = await m.copy_to(ADMIN_USER_ID)

    ROUTE[head_msg.message_id] = u.id
    ROUTE[copy_msg.message_id] = u.id

    log.info("Route saved: head_id=%s copy_id=%s -> user=%s",
             head_msg.message_id, copy_msg.message_id, u.id)

# ---------- АДМІН → КОРИСТУВАЧ ----------
# приймаємо реплай, якщо: приватний чат І (chat.id == ADMIN_USER_ID АБО from_user.id == ADMIN_USER_ID)
@dp.message((F.chat.type == "private") & (F.reply_to_message != None))
async def admin_reply_router(m: Message):
    # діагностика всіх реплаїв у приватах
    log.info(
        "Seen private REPLY: chat.id=%s from_user.id=%s reply_to_id=%s",
        m.chat.id, m.from_user.id, m.reply_to_message.message_id if m.reply_to_message else None
    )

    if not (
        (ADMIN_USER_ID is not None)
        and (m.chat.id == ADMIN_USER_ID or m.from_user.id == ADMIN_USER_ID)
    ):
        return  # не наш адмін/не наш приват

    # 1) пробуємо по ROUTE
    reply_to_id = m.reply_to_message.message_id
    user_id = ROUTE.get(reply_to_id)

    # 2) фолбек — UID із тексту/капшена того, на що відповіли
    if not user_id:
        src_text = (m.reply_to_message.text or "") + "\n" + (m.reply_to_message.caption or "")
        user_id = extract_uid_from_text(src_text)
        if user_id:
            log.info("Fallback UID parsed: %s", user_id)

    if not user_id:
        await m.reply(
            "ℹ️ Не знайшов одержувача. Попроси користувача написати ще раз "
            "або відповідай на «шапку» з рядком <b>UID: …</b>."
        )
        log.warning("No user_id for admin reply. reply_to_id=%s", reply_to_id)
        return

    try:
        if m.text:
            await bot.send_message(user_id, f"✉️ <b>Від адміна</b>:\n{m.text}")
        else:
            await m.copy_to(user_id)
        await m.reply("✅ Відповідь надіслана.")
        log.info("Reply delivered to user %s", user_id)
    except Exception as e:
        log.exception("Send fail to user %s: %s", user_id, e)
        await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")

# ---------- Діагностика: ловимо будь-які приватні повідомлення від адміна (без реплаю)
@dp.message((F.chat.type == "private") & (F.from_user.id == ADMIN_USER_ID))
async def any_admin_pm(m: Message):
    log.info("Admin PM (non-reply): chat.id=%s text=%r", m.chat.id, m.text)

# ---------- ЗАПУСК ----------
async def main():
    log.info("Start polling")
    me = await bot.get_me()
    log.info("Run polling for bot @%s id=%s - %r", me.username, me.id, me.first_name)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
