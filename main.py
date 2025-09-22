# main.py
import os
import asyncio
from decimal import Decimal
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties

from aiocryptopay import AioCryptoPay, Networks

# ── ENV ────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
CRYPTO_TOKEN = (os.getenv("CRYPTO_PAY_API_TOKEN") or "").strip()

if not BOT_TOKEN or " " in BOT_TOKEN:
    raise SystemExit("❌ BOT_TOKEN відсутній або містить пробіли. Перевір .env")
if not CRYPTO_TOKEN or " " in CRYPTO_TOKEN:
    raise SystemExit("❌ CRYPTO_PAY_API_TOKEN відсутній або містить пробіли. Перевір .env")

# ── Core ───────────────────────────────────────────────────────────────────────
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
crypto = AioCryptoPay(token=CRYPTO_TOKEN, network=Networks.MAIN_NET)

# стани
AWAIT_AMOUNT: Dict[int, Dict] = {}     # user_id -> {"asset": "USDT"}
PENDING: Dict[str, int] = {}           # invoice_id -> user_id

DONATELLO_URL = "https://donatello.to/SWOI_community"
ASSETS = ("USDT", "ETH", "BTC", "TON")

# ── Keyboards ─────────────────────────────────────────────────────────────────
def start_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Крипта", callback_data="flow:crypto")
    kb.button(text="☕ Donatello", url=DONATELLO_URL)
    kb.adjust(2)
    return kb.as_markup()

def assets_kb():
    kb = InlineKeyboardBuilder()
    for a in ASSETS:
        kb.button(text=a, callback_data=f"asset:{a}")
    kb.button(text="⬅️ Назад", callback_data="back:start")
    kb.adjust(4, 1)
    return kb.as_markup()

# ── Handlers ──────────────────────────────────────────────────────────────────
@dp.message(F.text == "/start")
async def start(m: Message):
    AWAIT_AMOUNT.pop(m.from_user.id, None)
    await m.answer(
        "Привіт 👋\n\n"
        "Обери зручний спосіб підтримати проєкт:\n"
        "• <b>Крипта</b> — USDT/ETH/BTC/TON (інвойс у Telegram)\n"
        "• <b>Donatello</b> — донат карткою на зовнішньому сайті\n",
        reply_markup=start_kb(),
    )

@dp.callback_query(F.data == "flow:crypto")
async def pick_asset(cb: CallbackQuery):
    # відповідаємо на колбек одразу, щоб не «прострочився»
    try:
        await cb.answer()
    except Exception:
        pass
    await cb.message.answer(
        "Оберіть <b>криптовалюту</b> для донату:",
        reply_markup=assets_kb()
    )

@dp.callback_query(F.data.startswith("asset:"))
async def asset_chosen(cb: CallbackQuery):
    # закриваємо «крутилку» якнайшвидше
    try:
        await cb.answer()
    except Exception:
        pass

    asset = cb.data.split(":", 1)[1]
    if asset not in ASSETS:
        # пробуємо показати алерт, але не падаємо
        try:
            await cb.answer("Невідома валюта", show_alert=True)
        except Exception:
            pass
        return

    AWAIT_AMOUNT[cb.from_user.id] = {"asset": asset}
    await cb.message.answer(
        f"Ви обрали <b>{asset}</b>.\n"
        "Введіть суму <b>числом</b> (наприклад: 1 або 5.5):"
    )

@dp.callback_query(F.data == "back:start")
async def back_to_start(cb: CallbackQuery):
    try:
        await cb.answer()
    except Exception:
        pass
    AWAIT_AMOUNT.pop(cb.from_user.id, None)
    await cb.message.answer("Повернувся в головне меню:", reply_markup=start_kb())

# ловимо введену суму, коли очікуємо її від користувача
@dp.message(F.text)
async def amount_input(m: Message):
    state = AWAIT_AMOUNT.get(m.from_user.id)
    if not state:
        return

    raw = (m.text or "").strip().replace(",", ".")
    try:
        amount = Decimal(raw)
        if amount <= 0:
            raise ValueError
    except Exception:
        await m.reply("Будь ласка, введіть коректну суму числом (наприклад: 1 або 5.5).")
        return

    asset = state["asset"]

    # створюємо інвойс у Crypto Pay
    try:
        inv = await crypto.create_invoice(
            asset=asset,
            amount=float(amount),
            description=f"Support Project ({asset})",
        )
    except Exception as e:
        await m.reply(
            "⚠️ Не вдалося створити рахунок. Спробуйте пізніше або оберіть інший спосіб.\n"
            f"<code>{type(e).__name__}: {e}</code>"
        )
        AWAIT_AMOUNT.pop(m.from_user.id, None)
        return

    AWAIT_AMOUNT.pop(m.from_user.id, None)
    PENDING[inv.invoice_id] = m.from_user.id

    await m.answer(
        f"👉 Рахунок на <b>{amount} {asset}</b>:\n{inv.bot_invoice_url}\n\n"
        "Після оплати зачекай кілька секунд — я надішлю підтвердження."
    )

# ── Background watcher ────────────────────────────────────────────────────────
async def watcher():
    while True:
        try:
            if PENDING:
                ids = list(PENDING.keys())
                invoices = await crypto.get_invoices(invoice_ids=ids)
                for inv in invoices.items:
                    if inv.status == "paid":
                        user_id = PENDING.pop(inv.invoice_id, None)
                        if user_id:
                            await bot.send_message(
                                chat_id=user_id,
                                text="❤️ Платіж отримано! Дякуємо за підтримку 🙌",
                            )
        except Exception as e:
            print("Watcher error:", e)
        await asyncio.sleep(5)

# ── Entrypoint ────────────────────────────────────────────────────────────────
async def main():
    print("✅ Bot started. Waiting for donations…")
    asyncio.create_task(watcher())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
