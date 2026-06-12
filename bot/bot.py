"""Telegram bot for TradeSim (DEMO).

Shares the backend database. All balances and trades are virtual (учебные
единицы). The bot never processes real payments.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from backend.app import economy, models
from backend.app.config import settings
from backend.app.database import SessionLocal, init_db

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

DEMO_BANNER = "__учебный симулятор. деньги и сделки виртуальные (DEMO)__\n\n"


def _get_or_create(tg_id: int, username: str | None, ref: str | None) -> models.User:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.telegram_id == tg_id).first()
        if user:
            return user
        referred_by = None
        if ref and ref.startswith("ref_"):
            c = ref[4:]
            if c.isdigit() and int(c) != tg_id:
                referred_by = int(c)
        user = models.User(
            telegram_id=tg_id,
            username=username,
            balance=settings.start_balance,
            referred_by=referred_by,
        )
        db.add(user)
        db.flush()
        db.add(
            models.Transaction(
                user_id=user.id,
                type="deposit_demo",
                amount=settings.start_balance,
                note="Стартовый виртуальный баланс (DEMO)",
            )
        )
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="ПРОФИЛЬ", callback_data="profile")],
        [InlineKeyboardButton(text="ЭТАПЫ ПОДПИСКИ", callback_data="tiers")],
        [InlineKeyboardButton(text="РЕФЕРАЛКА", callback_data="referral")],
        [InlineKeyboardButton(text="НАСТРОЙКИ", callback_data="settings")],
    ]
    # Telegram allows Web App buttons only over HTTPS. With an http:// localhost
    # URL the API rejects the whole message, so we add the button only for https.
    if settings.webapp_url.startswith("https://"):
        rows.insert(
            0,
            [InlineKeyboardButton(text="ОТКРЫТЬ MINI APP", web_app=WebAppInfo(url=settings.webapp_url))],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def webapp_hint() -> str:
    if settings.webapp_url.startswith("https://"):
        return ""
    return (
        "\n\n_Кнопка Mini App появится, когда WEBAPP_URL будет на https "
        "(нужен туннель, см. инструкцию). Сейчас задан несовместимый адрес._"
    )


def profile_text(user: models.User) -> str:
    db = SessionLocal()
    try:
        remaining = economy.remaining_trades_today(db, user)
    finally:
        db.close()
    exp = user.tier_expires_at.strftime("%Y-%m-%d") if user.tier_expires_at else "—"
    return (
        f"{DEMO_BANNER}"
        f"`ПРОФИЛЬ`\n"
        f"Telegram ID: `{user.telegram_id}`\n"
        f"Этап: `{user.tier} — {economy.TIERS[user.tier]['name']}`\n"
        f"Действует до: `{exp}`\n"
        f"Баланс: `{round(user.balance, 2)} УЕ`\n"
        f"Уровень: `{user.level}`\n"
        f"Всего сделок: `{user.total_trades}`\n"
        f"Осталось сделок сегодня: `{remaining}`"
    )


def tiers_text() -> str:
    lines = [f"{DEMO_BANNER}`ЭТАПЫ ПОДПИСКИ`"]
    for t, cfg in economy.TIERS.items():
        lines.append(f"Этап {t} — {cfg['name']}: `{cfg['price']} УЕ/мес`, лимит {cfg['daily_limit']}/сутки")
    return "\n".join(lines)


def welcome_text() -> str:
    return (
        f"{DEMO_BANNER}"
        "`TRADESIM`\n"
        "Добро пожаловать в учебный симулятор трейдинга.\n\n"
        "Всё внутри — виртуальное (учебные единицы). Откройте Mini App, "
        "чтобы увидеть дашборд, стакан сделок и блокчейн-обозреватель.\n\n"
        "Команды: /profile /tiers /buy /referral /settings /support"
        f"{webapp_hint()}"
    )


@dp.message(CommandStart(deep_link=True))
async def start_with_ref(message: Message, command):
    ref = command.args
    _get_or_create(message.from_user.id, message.from_user.username, ref)
    await message.answer(welcome_text(), reply_markup=main_menu_kb(), parse_mode="Markdown")


@dp.message(CommandStart())
async def start(message: Message):
    _get_or_create(message.from_user.id, message.from_user.username, None)
    await message.answer(welcome_text(), reply_markup=main_menu_kb(), parse_mode="Markdown")


@dp.message(Command("menu"))
async def menu(message: Message):
    await message.answer(f"{DEMO_BANNER}Главное меню:", reply_markup=main_menu_kb(), parse_mode="Markdown")


@dp.message(Command("profile"))
async def profile(message: Message):
    user = _get_or_create(message.from_user.id, message.from_user.username, None)
    await message.answer(profile_text(user), parse_mode="Markdown")


@dp.message(Command("tiers"))
async def tiers(message: Message):
    await message.answer(tiers_text(), parse_mode="Markdown")


@dp.message(Command("buy"))
async def buy(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Этап {t} — {cfg['price']} УЕ", callback_data=f"buy:{t}")]
            for t, cfg in economy.TIERS.items()
        ]
    )
    await message.answer(f"{DEMO_BANNER}Выберите этап (оплата виртуальным балансом):", reply_markup=kb, parse_mode="Markdown")


@dp.message(Command("referral"))
async def referral(message: Message):
    user = _get_or_create(message.from_user.id, message.from_user.username, None)
    db = SessionLocal()
    try:
        invited = db.query(models.User).filter(models.User.referred_by == user.telegram_id).count()
    finally:
        db.close()
    bot_info = await message.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start=ref_{user.telegram_id}"
    await message.answer(
        f"{DEMO_BANNER}`РЕФЕРАЛКА`\nСсылка: `{link}`\nПриглашено: `{invited}`\nБонус заработан: `{round(user.referral_earnings, 2)} УЕ`",
        parse_mode="Markdown",
    )


@dp.message(Command("settings"))
async def settings_cmd(message: Message):
    user = _get_or_create(message.from_user.id, message.from_user.username, None)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"Звук: {'ВКЛ' if user.sound_enabled else 'ВЫКЛ'}", callback_data="toggle:sound")],
            [InlineKeyboardButton(text=f"Авто-турбо: {'ВКЛ' if user.auto_turbo else 'ВЫКЛ'}", callback_data="toggle:turbo")],
        ]
    )
    await message.answer(f"{DEMO_BANNER}`НАСТРОЙКИ`", reply_markup=kb, parse_mode="Markdown")


@dp.message(Command("support"))
async def support(message: Message):
    await message.answer(f"{DEMO_BANNER}Поддержка: напишите администратору проекта.", parse_mode="Markdown")


@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id not in settings.admin_id_set:
        await message.answer("Доступ только для администраторов.")
        return
    db = SessionLocal()
    try:
        total = db.query(models.User).count()
    finally:
        db.close()
    await message.answer(f"{DEMO_BANNER}`АДМИН`\nВсего пользователей: `{total}`\n(полное управление — через API /api/admin)", parse_mode="Markdown")


@dp.callback_query(F.data == "profile")
async def cb_profile(cb: CallbackQuery):
    user = _get_or_create(cb.from_user.id, cb.from_user.username, None)
    await cb.message.answer(profile_text(user), parse_mode="Markdown")
    await cb.answer()


@dp.callback_query(F.data == "tiers")
async def cb_tiers(cb: CallbackQuery):
    await cb.message.answer(tiers_text(), parse_mode="Markdown")
    await cb.answer()


@dp.callback_query(F.data == "referral")
async def cb_referral(cb: CallbackQuery):
    await referral(cb.message if cb.message else cb)  # reuse
    await cb.answer()


@dp.callback_query(F.data.startswith("buy:"))
async def cb_buy(cb: CallbackQuery):
    tier = int(cb.data.split(":")[1])
    user = _get_or_create(cb.from_user.id, cb.from_user.username, None)
    db = SessionLocal()
    try:
        price = economy.TIERS[tier]["price"]
        u = db.query(models.User).filter(models.User.telegram_id == user.telegram_id).first()
        if u.balance < price:
            await cb.answer(f"Недостаточно средств: нужно {price} УЕ", show_alert=True)
            return
        u.balance -= price
        u.tier = tier
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        u.tier_expires_at = now + timedelta(days=30)
        db.add(models.Transaction(user_id=u.id, type="subscription", amount=-price, note=f"Подписка {tier} (DEMO)"))
        db.commit()
    finally:
        db.close()
    await cb.message.answer(f"Подписка Этап {tier} активирована (DEMO).", parse_mode="Markdown")
    await cb.answer()


@dp.callback_query(F.data.startswith("toggle:"))
async def cb_toggle(cb: CallbackQuery):
    what = cb.data.split(":")[1]
    db = SessionLocal()
    try:
        u = db.query(models.User).filter(models.User.telegram_id == cb.from_user.id).first()
        if what == "sound":
            u.sound_enabled = not u.sound_enabled
        elif what == "turbo":
            u.auto_turbo = not u.auto_turbo
        db.commit()
    finally:
        db.close()
    await cb.answer("Сохранено")


@dp.errors()
async def on_error(event):
    logging.exception("Ошибка при обработке апдейта: %s", event.exception)
    return True


async def main():
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан в .env — бот не может запуститься.")
    init_db()
    bot = Bot(settings.bot_token)
    me = await bot.get_me()
    logging.info("Бот запущен: @%s (id %s)", me.username, me.id)
    if settings.webapp_url.startswith("https://"):
        logging.info("Mini App: %s", settings.webapp_url)
    else:
        logging.warning(
            "WEBAPP_URL=%s не на https — кнопка Mini App отключена. "
            "Поднимите HTTPS-туннель и пропишите его в .env.",
            settings.webapp_url,
        )
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
