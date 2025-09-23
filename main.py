import os
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

# ── ENV ──────────────────────────────────────────
BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
if not BOT_TOKEN or " " in BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN не знайдено або містить пробіли.")

ADMIN_USER_ID_RAW = (os.getenv("ADMIN_USER_ID") or "").strip()
try:
    ADMIN_USER_ID = int(ADMIN_USER_ID_RAW)
except Exception:
    ADMIN_USER_ID = None
    print("⚠️ ADMIN_USER_ID не задано. Спочатку в приваті бота надішли /id і додай змінну ADMIN_USER_ID у Railway.")

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# Пам'ять відповідностей: id повідомлення в чаті адміна -> id користувача
ROUTE = {}  # {admin_msg_id: user_id}

# ── Контент / кнопки (опційно – твій список проєктів) ──
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

# ── Службові команди ─────────────────────────────
@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer(WELCOME_TEXT, reply_markup=start_kb())

@dp.callback_query(F.data == "show:projects")
async def show_projects(cb: CallbackQuery):
    try: await cb.answer()
    except: pass
    await cb.message.answer("📂 Наші проєкти:", reply_markup=projects_kb())

@dp.message(F.text == "/id")
async def cmd_id(m: Message):
    await m.reply(f"chat_id = <code>{m.chat.id}</code>\nuser_id = <code>{m.from_user.id}</code>")

# ── Користувач → Адмін ───────────────────────────
@dp.message(F.chat.type == "private")
async def from_user(m: Message):
    # якщо пише сам адмін у приваті — не маршрутизувати
    if ADMIN_USER_ID and m.from_user.id == ADMIN_USER_ID:
        return

    if ADMIN_USER_ID is None:
        await m.answer("⚠️ Бот ще не налаштований. Адмін має додати ADMIN_USER_ID.")
        return

    u = m.from_user
    header = (
        "📥 <b>Нове звернення</b>\n"
        f"👤 {u.full_name} @{u.username or '—'}\n"
        f"🆔 <code>{u.id}</code>\n"
        f"🔗 <a href='tg://user?id={u.id}'>відкрити профіль</a>\n\n"
        "✍️ Відповідай <b>реплаєм</b> на це повідомлення — я перешлю користувачу."
    )
    # надсилаємо шапку
    head_msg = await bot.send_message(ADMIN_USER_ID, header, disable_web_page_preview=True)
    # копіюємо саме повідомлення (з медіа збереженням)
    copied = await m.copy_to(ADMIN_USER_ID)
    # запам'ятовуємо, на який меседж адмін має відповісти
    ROUTE[copied.message_id] = u.id

# ── Адмін → Користувач (відповідь реплаєм) ─────────
@dp.message((F.chat.type == "private") & (F.from_user.id == ADMIN_USER_ID) & (F.reply_to_message != None))
async def from_admin_reply(m: Message):
    # шукаємо користувача за id повідомлення, на яке відповіли
    reply_to_id = m.reply_to_message.message_id
    user_id = ROUTE.get(reply_to_id)

    if not user_id:
        # можливо відповіли на шапку; спробуємо знайти попереднє повідомлення,
        # але простіше попросити відповісти саме на копію
        await m.reply("ℹ️ Відповідай саме на скопійоване повідомлення користувача, а не на шапку.")
        return

    # надсилаємо користувачу відповідь (збережемо формат і медіа)
    try:
        if m.text:
            await bot.send_message(user_id, f"✉️ <b>Від адміна</b>:\n{m.text}")
        else:
            await m.copy_to(user_id)
        await m.reply("✅ Відповідь надіслана.")
    except Exception as e:
        await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")
        print("Send fail:", e)

# ── Запуск ────────────────────────────────────────
async def main():
    print("✅ Admin relay bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
