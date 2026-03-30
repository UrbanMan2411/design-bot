#!/usr/bin/env python3
"""
Design Bot v6 — Telegram бот-дизайнер
Модульная архитектура с тестами.
"""

import asyncio
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile, BufferedInputFile, InputMediaPhoto
from dotenv import load_dotenv

from modules.config import BOT_TOKEN, GITHUB_TOKEN, GITHUB_REPO, MAX_DESIGNS_PER_DAY, OPENROUTER_MODEL
from modules.generator import generate_design
from modules.screenshots import take_screenshots
from modules.publisher import publish_to_github, fetch_from_github, create_zip
from modules.html_utils import extract_html, fix_html_issues, add_watermark, validate_html
from modules.keyboards import get_style_keyboard, get_result_keyboard, map_style

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === State ===
user_locks: dict[int, bool] = defaultdict(bool)
user_history: dict[int, list[dict]] = defaultdict(list)
user_daily_count: dict[int, int] = defaultdict(int)
user_last_request: dict[int, datetime] = {}
user_feedback: dict[str, str] = {}
user_referrals: dict[int, set] = defaultdict(set)
user_referred_by: dict[int, int] = {}
user_bonus: dict[int, int] = defaultdict(int)
REFERRAL_BONUS = 5
COOLDOWN_SECONDS = 0
last_reset: datetime = datetime.now()


def check_rate_limit(user_id: int) -> bool:
    global last_reset
    now = datetime.now()
    if (now - last_reset) > timedelta(days=1):
        user_daily_count.clear()
        last_reset = now
    limit = MAX_DESIGNS_PER_DAY + user_bonus.get(user_id, 0)
    return user_daily_count[user_id] < limit


def get_user_limit(user_id: int) -> int:
    return MAX_DESIGNS_PER_DAY + user_bonus.get(user_id, 0)


# === Handlers ===
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
            if referrer_id != message.from_user.id and message.from_user.id not in user_referred_by:
                user_referred_by[message.from_user.id] = referrer_id
                user_referrals[referrer_id].add(message.from_user.id)
                user_bonus[referrer_id] += REFERRAL_BONUS
                await message.answer("🎉 Вы приглашены! Пригласитель получит +5 дизайнов в день.")
        except (ValueError, IndexError):
            pass

    referral_link = f"https://t.me/LandAIpagebot?start=ref{message.from_user.id}"
    await message.answer(
        "🎨 <b>Design Bot v6</b>\n\n"
        "Опиши дизайн — получишь HTML + скриншот + ссылку.\n\n"
        "<b>Команды:</b>\n"
        "/styles — выбрать стиль\n"
        "/history — последние дизайны\n"
        "/stats — статистика\n"
        "/referral — пригласить друга (+5 дизайнов)\n"
        "/gallery — галерея дизайнов\n"
        "/help — помощь",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Как пользоваться:</b>\n\n"
        "1️⃣ Напиши что за сайт нужен\n"
        "2️⃣ Выбери стиль (или пропусти)\n"
        "3️⃣ Получишь скриншот + ссылку\n\n"
        "🔄 Ещё — новый вариант\n"
        "🎨 Стиль — сменить стиль\n"
        "👍👎 — оценить дизайн\n"
        "📦 — скачать HTML\n\n"
        f"Лимит: {MAX_DESIGNS_PER_DAY} дизайнов в день\n"
        "Пригласи друга — получи +5 к лимиту: /referral",
        parse_mode="HTML",
    )


@router.message(Command("styles"))
async def cmd_styles(message: Message):
    await message.answer(
        "Сначала напиши что за сайт нужен, затем выбери стиль.\n\n"
        "Например: <i>Лендинг для кофейни в стиле ретро</i>",
        parse_mode="HTML",
    )


@router.message(Command("history"))
async def cmd_history(message: Message):
    history = user_history.get(message.from_user.id, [])
    if not history:
        await message.answer("История пуста. Сгенерируй первый дизайн!")
        return
    text = "<b>📋 Последние дизайны:</b>\n\n"
    for i, item in enumerate(reversed(history[-10:]), 1):
        t = item["time"].strftime("%H:%M")
        style = item.get("style", "auto")
        rating = ""
        if item["filename"] in user_feedback:
            rating = " 👍" if user_feedback[item["filename"]] == "like" else " 👎"
        text += f"{i}. <i>{item['prompt'][:40]}</i>{rating}\n   🔗 <a href=\"{item['url']}\">{style}</a> • {t}\n\n"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    uid = message.from_user.id
    total = len(user_history.get(uid, []))
    today = user_daily_count.get(uid, 0)
    limit = get_user_limit(uid)
    refs = len(user_referrals.get(uid, set()))
    text = (
        f"<b>📊 Статистика</b>\n\n"
        f"Всего дизайнов: <b>{total}</b>\n"
        f"Сегодня: <b>{today}/{limit}</b>\n"
        f"Рефералы: <b>{refs}</b> (+{refs * REFERRAL_BONUS} дизайнов)"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("referral"))
async def cmd_referral(message: Message):
    uid = message.from_user.id
    link = f"https://t.me/LandAIpagebot?start=ref{uid}"
    refs = len(user_referrals.get(uid, set()))
    bonus = user_bonus.get(uid, 0)
    await message.answer(
        f"<b>🎁 Пригласи друзей!</b>\n\n"
        f"За каждого друга: <b>+{REFERRAL_BONUS} дизайнов в день</b>\n\n"
        f"Твоя ссылка:\n<code>{link}</code>\n\n"
        f"Приглашено: <b>{refs}</b> чел.\n"
        f"Бонус: <b>+{bonus}</b> дизайнов/день",
        parse_mode="HTML",
    )


@router.message(Command("gallery"))
async def cmd_gallery(message: Message):
    gallery_url = "https://urbanman2411.github.io/design-pages/"
    await message.answer(
        f"🖼 <b>Галерея дизайнов</b>\n\n"
        f"🔗 <a href=\"{gallery_url}\">Открыть галерею</a>",
        parse_mode="HTML",
    )


# === Callbacks ===

@router.callback_query(F.data.startswith("pick:"))
async def cb_pick_style(callback: CallbackQuery):
    prompt = callback.data[5:]
    await callback.answer()
    await callback.message.answer(
        f"Выбери стиль для: <i>{prompt[:40]}...</i>",
        parse_mode="HTML",
        reply_markup=get_style_keyboard(prompt),
    )


@router.callback_query(F.data.startswith("gen:"))
async def cb_generate_with_style(callback: CallbackQuery):
    parts = callback.data.split(":", 2)
    prompt, style = parts[1], parts[2]
    if not prompt or prompt == "placeholder" or len(prompt) < 5:
        await callback.answer("Сначала напиши описание дизайна!", show_alert=True)
        return
    full_style = map_style(style)
    full_prompt = f"{prompt}. Style: {full_style}" if full_style else prompt
    await callback.answer("Генерирую...")
    await process_design(callback.message, callback.from_user.id, full_prompt, style=style)


@router.callback_query(F.data.startswith("retry:"))
async def cb_retry(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer("Генерирую новый вариант...")
    await process_design(callback.message, callback.from_user.id, prompt)


@router.callback_query(F.data.startswith("ab:"))
async def cb_ab_test(callback: CallbackQuery):
    prompt = callback.data[3:]
    await callback.answer("Генерирую 2 варианта...")
    for style in ["dark", "color"]:
        full_prompt = f"{prompt}. Style: {map_style(style)}"
        await process_design(callback.message, callback.from_user.id, full_prompt, style=style)
        await asyncio.sleep(1)


@router.callback_query(F.data.startswith("like:"))
async def cb_like(callback: CallbackQuery):
    fn = callback.data[5:]
    for item in reversed(user_history.get(callback.from_user.id, [])):
        if fn in item["filename"]:
            user_feedback[item["filename"]] = "like"
            await callback.answer("👍 Спасибо за оценку!")
            return
    await callback.answer("Дизайн не найден")


@router.callback_query(F.data.startswith("no:"))
async def cb_dislike(callback: CallbackQuery):
    fn = callback.data[3:]
    for item in reversed(user_history.get(callback.from_user.id, [])):
        if fn in item["filename"]:
            user_feedback[item["filename"]] = "dislike"
            await callback.answer("👎 Учтём!")
            return
    await callback.answer("Дизайн не найден")


@router.callback_query(F.data.startswith("dl:"))
async def cb_download(callback: CallbackQuery):
    fn = callback.data[3:]
    for item in reversed(user_history.get(callback.from_user.id, [])):
        if fn in item["filename"]:
            try:
                html = await asyncio.to_thread(fetch_from_github, item["filename"])
                if html:
                    zip_data = create_zip(html, item["filename"])
                    await callback.message.answer_document(
                        BufferedInputFile(zip_data, filename=f"{item['filename']}.zip"),
                        caption=f"📦 <b>{item['filename']}</b>",
                        parse_mode="HTML",
                    )
                else:
                    await callback.answer("Не удалось скачать")
            except Exception as e:
                await callback.answer(f"Ошибка: {e}")
            return
    await callback.answer("Дизайн не найден")


# === Main handler ===

@router.message(F.text & ~F.text.startswith("/"))
async def handle_design_request(message: Message):
    await process_design(message, message.from_user.id, message.text.strip())


async def process_design(target_msg: Message, user_id: int, user_prompt: str, style: str = ""):
    if len(user_prompt) < 3:
        await target_msg.answer("Опиши подробнее, что за дизайн нужен 🤔")
        return

    if not check_rate_limit(user_id):
        limit = get_user_limit(user_id)
        await target_msg.answer(
            f"⚠️ Достигнут дневной лимит ({limit} дизайнов).\n"
            "Попробуй завтра или пригласи друга: /referral"
        )
        return

    # Cooldown
    if COOLDOWN_SECONDS > 0:
        last = user_last_request.get(user_id)
        if last:
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed < COOLDOWN_SECONDS:
                remaining = int(COOLDOWN_SECONDS - elapsed)
                await target_msg.answer(f"⏳ Подожди <b>{remaining}с</b>.", parse_mode="HTML")
                return

    if user_locks[user_id]:
        await target_msg.answer("⏳ Подожди, предыдущий дизайн ещё генерируется...")
        return

    user_locks[user_id] = True
    start_time = datetime.now()
    status_msg = await target_msg.answer("⏳ Генерирую дизайн...")

    try:
        # 1. Generate
        await status_msg.edit_text("🤖 AI создаёт дизайн...")
        raw_response = await generate_design(user_prompt)
        html = extract_html(raw_response)
        html = fix_html_issues(html)
        html = add_watermark(html)

        # 2. Validate
        issues = validate_html(html)
        if issues:
            logger.warning(f"HTML issues: {issues}")

        # 3. Screenshot
        slug = re.sub(r'[^a-z0-9]+', '-', user_prompt.lower())[:40].strip('-')
        uid = uuid.uuid4().hex[:6]
        filename = f"{slug}-{uid}"
        await status_msg.edit_text("📸 Делаю превью...")
        desktop_path, mobile_path = await take_screenshots(html, filename)

        # 4. Publish
        await status_msg.edit_text("📤 Публикую...")
        url = await asyncio.to_thread(publish_to_github, html, filename)

        # 5. Track
        elapsed = (datetime.now() - start_time).total_seconds()
        user_daily_count[user_id] += 1
        user_last_request[user_id] = datetime.now()
        user_history[user_id].append({
            "prompt": user_prompt,
            "url": url,
            "filename": filename,
            "style": style or "auto",
            "time": datetime.now(),
        })

        # 6. Send
        await status_msg.delete()
        keyboard = get_result_keyboard(user_prompt, filename)
        limit = get_user_limit(user_id)
        remaining = limit - user_daily_count[user_id]
        refs = len(user_referrals.get(user_id, set()))
        caption = (
            f"✅ <b>Готово!</b> ({elapsed:.0f}с)\n\n"
            f"🔗 <a href=\"{url}\">Открыть сайт</a>\n"
            f"🎨 {style or 'auto'} • 📊 {remaining} дизайнов сегодня"
        )
        if refs > 0:
            caption += f"\n👥 Рефералы: {refs} (+{refs * REFERRAL_BONUS})"

        has_desktop = desktop_path and os.path.exists(desktop_path)
        has_mobile = mobile_path and os.path.exists(mobile_path)

        if has_desktop and has_mobile:
            media = [
                InputMediaPhoto(media=FSInputFile(desktop_path), caption=caption, parse_mode="HTML"),
                InputMediaPhoto(media=FSInputFile(mobile_path)),
            ]
            await target_msg.answer_media_group(media)
            await target_msg.answer("Действия:", reply_markup=keyboard)
        elif has_desktop:
            await target_msg.answer_photo(
                photo=FSInputFile(desktop_path), caption=caption,
                parse_mode="HTML", reply_markup=keyboard,
            )
        else:
            await target_msg.answer(caption, parse_mode="HTML", reply_markup=keyboard)

        for path in [desktop_path, mobile_path]:
            if path and os.path.exists(path):
                os.remove(path)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        try:
            await status_msg.edit_text(f"❌ Ошибка: {e}\n\nПопробуй ещё раз.")
        except Exception:
            await target_msg.answer(f"❌ Ошибка: {e}\n\nПопробуй ещё раз.")

    finally:
        user_locks[user_id] = False


# === Main ===

async def main():
    missing = []
    if not BOT_TOKEN: missing.append("BOT_TOKEN")
    if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
    if not GITHUB_REPO: missing.append("GITHUB_REPO")
    if missing:
        print(f"❌ Missing: {', '.join(missing)}")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("🤖 Design Bot v6 started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
