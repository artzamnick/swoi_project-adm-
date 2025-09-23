import os
import asyncio
import logging
from typing import Dict

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

# ---------- ЛОГИ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
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
    log.warning("⚠️ ADMIN_USER_ID не задано. Надішли /id боту й додай значення у Railway → Variables.")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# message_id у чаті адміна → user_id користувача
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
    # не маршрутизувати, якщо пише сам адмін
    if ADMIN_USER_ID and m.from_user.id == ADMIN_USER_ID:
        return

    if ADMIN_USER_ID is None:
        await m.answer("⚠️ Бот ще не налаштований: ADMIN_USER_ID відсутній.")
        return

    u = m.from_user
    header = (
        "📥 <b>Нове звернення</b>\n"
        f"👤 {u.full_name} @{u.username or '—'}\n"
        f"🆔 <code>{u.id}</code>\n"
        f"🔗 <a href='tg://user?id={u.id}'>відкрити профіль</a>\n\n"
        "✍️ Можеш відповісти <b>реплаєм</b> на <b>будь-яке</b> з двох повідомлень нижче (шапка або копія) — я перешлю користувачу."
    )

    # 1) шапка
    head_msg = await bot.send_message(ADMIN_USER_ID, header, disable_web_page_preview=True)
    # 2) копія оригіналу (медіа збережуться)
    copy_msg = await m.copy_to(ADMIN_USER_ID)

    # Зберігаємо маршрути для ОБОХ варіантів (реплай на шапку або на копію)
    ROUTE[head_msg.message_id] = u.id
    ROUTE[copy_msg.message_id] = u.id

    log.info("Звернення від %s (%s), збережено route for head=%s, copy=%s",
             u.id, u.username, head_msg.message_id, copy_msg.message_id)

# ---------- АДМІН → КОРИСТУВАЧ (реплай на шапку або копію) ----------
@dp.message((F.chat.type == "private") & (F.from_user.id == ADMIN_USER_ID) & (F.reply_to_message != None))
async def from_admin_reply(m: Message):
    reply_to_id = m.reply_to_message.message_id
    user_id = ROUTE.get(reply_to_id)

    if not user_id:
        await m.reply("ℹ️ Не знайшов одержувача. Попроси юзера написати ще раз у бот — і відповідай реплаєм.")
        return

    try:
        if m.text:
            await bot.send_message(user_id, f"✉️ <b>Від адміна</b>:\n{m.text}")
        else:
            # для фото/відео/доків копіюємо як є
            await m.copy_to(user_id)
        await m.reply("✅ Відповідь надіслана.")
        log.info("Відповідь доставлена користувачу %s", user_id)
    except Exception as e:
        log.exception("Send fail: %s", e)
        await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")

# ---------- ЗАПУСК ----------
async def main():
    print("✅ Admin relay bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
