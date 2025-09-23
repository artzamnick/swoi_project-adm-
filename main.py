import os
import re
import asyncio
import logging
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

# ================== ЛОГИ ==================
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("admin_bot")

# ================== ENV ===================
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

# ============== ПАМ'ЯТЬ/СТАН ==============
# Прив’язка: message_id у чаті адміна → user_id (працює для реплая на шапку/копію)
ROUTE: Dict[int, int] = {}
# Режим відповіді (кнопка «Відповісти»): {admin_id: user_id}
ACTIVE_TARGET: Dict[int, int] = {}

# ============== ТЕКСТИ/КНОПКИ =============
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

def reply_button(uid: int) -> InlineKeyboardMarkup:
    # Кнопка для ввімкнення режиму відповіді
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Відповісти користувачу", callback_data=f"ans:{uid}")]
    ])

# ============== УТИЛІТИ ===================
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

# ============== БАЗОВІ КОМАНДИ =============
@dp.message(F.text == "/start")
async def cmd_start(m: Message):
    await m.answer(WELCOME_TEXT, reply_markup=start_kb())

@dp.message(F.text == "/id")
async def cmd_id(m: Message):
    await m.reply(f"chat_id = <code>{m.chat.id}</code>\nuser_id = <code>{m.from_user.id}</code>")

@dp.callback_query(F.data == "show:projects")
async def show_projects(cb: CallbackQuery):
    try:
        await cb.answer()
    except Exception:
        pass
    await cb.message.answer("📂 Наші проєкти:", reply_markup=projects_kb())

# ======== КОРИСТУВАЧ → АДМІН (шапка+копія+кнопка) ========
@dp.message(lambda m: m.chat.type == "private" and (ADMIN_USER_ID is None or m.from_user.id != ADMIN_USER_ID))
async def from_user(m: Message):
    if ADMIN_USER_ID is None:
        await m.answer("⚠️ Бот ще не налаштований: ADMIN_USER_ID відсутній.")
        return

    u = m.from_user
    uid_line = f"UID: {u.id}"  # явний UID для фолбеку
    header = (
        "📥 <b>Нове звернення</b>\n"
        f"👤 {u.full_name} @{u.username or '—'}\n"
        f"🆔 <code>{u.id}</code>\n"
        f"{uid_line}\n"
        f"🔗 <a href='tg://user?id={u.id}'>відкрити профіль</a>\n\n"
        "✍️ Можеш відповісти <b>реплаєм</b> на шапку/копію або натисни кнопку нижче."
    )

    # Шапка з КНОПКОЮ
    head_msg = await bot.send_message(
        ADMIN_USER_ID, header, disable_web_page_preview=True, reply_markup=reply_button(u.id)
    )
    # Копія повідомлення (зберігає медіа)
    copy_msg = await m.copy_to(ADMIN_USER_ID)

    # Прив’язуємо обидва message_id до user_id
    ROUTE[head_msg.message_id] = u.id
    ROUTE[copy_msg.message_id] = u.id
    log.info("Route saved head=%s copy=%s -> user=%s", head_msg.message_id, copy_msg.message_id, u.id)

# ======== ВАРІАНТ 1: команда /r <uid> <текст> ========
@dp.message(F.chat.type == "private", F.from_user.id == ADMIN_USER_ID, F.text.regexp(r"^/r\s+\d+\s+"))
async def reply_cmd(m: Message):
    parts = m.text.split(maxsplit=2)
    if len(parts) < 3:
        await m.reply("Формат: /r <uid> <текст>\nПриклад: /r 123456789 Привіт!")
        return
    uid_str, text = parts[1], parts[2]
    try:
        uid = int(uid_str)
    except ValueError:
        await m.reply("UID має бути числом. Приклад: /r 123456789 Привіт!")
        return
    try:
        await bot.send_message(uid, f"✉️ <b>Від адміна</b>:\n{text}")
        await m.reply("✅ Відповідь надіслана.")
        log.info("Reply by /r to user %s", uid)
    except Exception as e:
        log.exception("Reply by /r failed: %s", e)
        await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")

# ======== ВАРІАНТ 2: кнопка «Відповісти» + режим ========
@dp.callback_query(F.data.startswith("ans:"))
async def set_target(cb: CallbackQuery):
    try:
        uid = int(cb.data.split(":", 1)[1])
    except Exception:
        await cb.answer("Помилка UID", show_alert=True)
        return
    ACTIVE_TARGET[cb.from_user.id] = uid
    try:
        await cb.answer("Режим відповіді увімкнено")
    except Exception:
        pass
    await cb.message.answer(
        f"✍️ Тепер просто надішли повідомлення — я перешлю користувачу <code>{uid}</code>.\n"
        f"Щоб скасувати, напиши /cancel."
    )

@dp.message(F.chat.type == "private", F.from_user.id == ADMIN_USER_ID, F.text == "/cancel")
async def cancel_target(m: Message):
    ACTIVE_TARGET.pop(m.from_user.id, None)
    await m.reply("❌ Режим відповіді вимкнено.")

@dp.message(F.chat.type == "private", F.from_user.id == ADMIN_USER_ID)
async def send_when_active(m: Message):
    """
    Якщо ввімкнений «режим відповіді» (натиснута кнопка) —
    наступне будь-яке повідомлення адміна ми пересилаємо юзеру.
    """
    uid = ACTIVE_TARGET.get(m.from_user.id)
    if not uid:
        return  # режим не активний — пропускаємо

    try:
        if m.text and not m.text.startswith("/"):
            await bot.send_message(uid, f"✉️ <b>Від адміна</b>:\n{m.text}")
        elif not m.text:
            await m.copy_to(uid)  # фото/відео/док
        else:
            # якщо це команда — не відправляємо юзеру
            return
        await m.reply("✅ Відповідь надіслана.")
        log.info("Reply (active-mode) delivered to user %s", uid)
    except Exception as e:
        log.exception("Active-mode reply failed to user %s: %s", uid, e)
        await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")
    finally:
        ACTIVE_TARGET.pop(m.from_user.id, None)

# ======== ФОЛБЕК: реплай на шапку/копію ========
@dp.message(F.chat.type == "private", F.from_user.id == ADMIN_USER_ID, F.reply_to_message != None)
async def from_admin_reply(m: Message):
    reply_to_id = m.reply_to_message.message_id
    user_id = ROUTE.get(reply_to_id)

    if not user_id:
        # спробуємо витягти UID із тексту шапки
        src_text = (m.reply_to_message.text or "") + "\n" + (m.reply_to_message.caption or "")
        user_id = extract_uid_from_text(src_text)
        if user_id:
            log.info("Fallback UID parsed from header: %s", user_id)

    if not user_id:
        # Якщо не знайшли — нехай обробляє send_when_active або команда /r
        return

    try:
        if m.text:
            await bot.send_message(user_id, f"✉️ <b>Від адміна</b>:\n{m.text}")
        else:
            await m.copy_to(user_id)
        await m.reply("✅ Відповідь надіслана.")
        log.info("Reply (reply-to) delivered to user %s", user_id)
    except Exception as e:
        log.exception("Send fail to user %s: %s", user_id, e)
        await m.reply("⚠️ Не вдалося надіслати. Можливо, користувач закрив чат із ботом.")

# ================== ЗАПУСК =================
async def main():
    print("✅ Admin relay bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
