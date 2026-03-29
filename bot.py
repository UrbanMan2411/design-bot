#!/usr/bin/env python3
"""
Design Bot v2 — Telegram бот-дизайнер
Генерирует frontend-дизайны через AI и публикует на GitHub Pages.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/xiaomi/mimo-v2-pro")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
PAGES_BASE_URL = f"https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}"

# === Request queue ===
user_locks: dict[int, bool] = defaultdict(bool)

# === System prompt ===
SYSTEM_PROMPT = """You are an expert frontend designer. Create distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics.

## Design Thinking
- Purpose: What problem does this interface solve?
- Tone: Pick an extreme — brutally minimal, maximalist chaos, retro-futuristic, organic/natural, luxury/refined, editorial/magazine, brutalist/raw, art deco/geometric
- Differentiation: What makes this UNFORGETTABLE?

## Rules
- Typography: Google Fonts only. NEVER Inter, Roboto, Arial, system fonts
- Color: CSS variables. Sharp accents. Cohesive palette
- Motion: CSS animations, staggered reveals
- Layout: Asymmetry, overlap, generous negative space
- Backgrounds: Gradient meshes, noise textures, geometric patterns

## Images (CRITICAL)
Include 3-6 images in your design. ALWAYS use Lorem Picsum — it always works:
https://picsum.photos/1200/800?random=1
https://picsum.photos/800/600?random=2
https://picsum.photos/600/400?random=3
Use different random=N numbers for different images.
Use images as hero backgrounds, section images, gallery items.

## Output
Return ONLY a complete, self-contained HTML file with inline CSS and JS.
Use Google Fonts links. Include real Unsplash images. Make it memorable."""


# === Core functions ===

def extract_html(text: str) -> str:
    """Extract HTML from AI response."""
    if not isinstance(text, str):
        text = str(text)
    match = re.search(r'```(?:html)?\s*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    if text.strip().startswith(('<!DOCTYPE', '<html')):
        return text.strip()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Design</title>
</head>
<body>
{text.strip()}
</body>
</html>"""


async def generate_design(user_prompt: str, style: str = "") -> str:
    """Call AI API to generate HTML design."""
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    
    user_content = user_prompt
    if style:
        user_content = f"{user_prompt}\n\nStyle preference: {style}"

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.9,
        "max_tokens": 8000,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers,
                                timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise Exception(f"AI API error {resp.status}: {error}")
            data = await resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise Exception(f"Empty response: {json.dumps(data)[:200]}")
            return content


async def take_screenshot(html: str, filename: str) -> str | None:
    """Render HTML and take screenshot. Returns path or None on failure."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.set_content(html, wait_until="networkidle", timeout=30000)
            path = f"/tmp/{filename}.png"
            await page.screenshot(path=path, full_page=True)
            await browser.close()
            return path
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return None


def publish_to_github(html: str, filename: str) -> str:
    """Push HTML to GitHub Pages. Returns public URL."""
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    path = f"designs/{filename}.html"

    try:
        contents = repo.get_contents(path, ref=GITHUB_BRANCH)
        repo.update_file(path, f"Update: {filename}", html, contents.sha, branch=GITHUB_BRANCH)
    except GithubException:
        repo.create_file(path, f"Add: {filename}", html, branch=GITHUB_BRANCH)

    return f"{PAGES_BASE_URL}/designs/{filename}.html"


# === Keyboards ===

def get_retry_keyboard(prompt: str) -> InlineKeyboardMarkup:
    """Keyboard with retry/regenerate buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"retry:{prompt[:50]}"),
            InlineKeyboardButton(text="🎨 Другой стиль", callback_data=f"style:{prompt[:50]}"),
        ]
    ])


# === Handlers ===
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎨 <b>Design Bot v2</b>\n\n"
        "Опиши дизайн — получишь HTML + скриншот + ссылку.\n\n"
        "<b>Примеры:</b>\n"
        "• Лендинг для кофейни в стиле ретро\n"
        "• Портфолио фотографа, минимализм\n"
        "• Сайт церкви «Высшее призвание»\n"
        "• Карточка SaaS для AI-стартапа\n\n"
        "Просто напиши 👇",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Как пользоваться:</b>\n\n"
        "1️⃣ Напиши описание дизайна\n"
        "2️⃣ Бот сгенерирует HTML\n"
        "3️⃣ Получишь скриншот + ссылку\n\n"
        "Кнопка 🔄 — сгенерировать ещё вариант\n"
        "Кнопка 🎨 — попробовать другой стиль",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("retry:"))
async def cb_retry(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer("Генерирую новый вариант...")
    await process_design(callback.message, callback.from_user.id, prompt, edit=True)


@router.callback_query(F.data.startswith("style:"))
async def cb_style(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer()
    await callback.message.answer(
        f"Опиши желаемый стиль для: <i>{prompt}</i>\n\n"
        "Например: тёмный минимализм, неоновый ретро, природный organic",
        parse_mode="HTML",
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_design_request(message: Message):
    await process_design(message, message.from_user.id, message.text.strip())


async def process_design(target_msg: Message, user_id: int, user_prompt: str, edit: bool = False):
    """Main design generation pipeline."""
    if len(user_prompt) < 5:
        await target_msg.answer("Опиши подробнее, что за дизайн нужен 🤔")
        return

    if user_locks[user_id]:
        await target_msg.answer("⏳ Подожди, предыдущий дизайн ещё генерируется...")
        return

    user_locks[user_id] = True
    status_msg = await target_msg.answer("⏳ Генерирую дизайн...")

    try:
        # 1. Generate HTML
        raw_response = await generate_design(user_prompt)
        html = extract_html(raw_response)

        # 2. Filename
        slug = re.sub(r'[^a-z0-9]+', '-', user_prompt.lower())[:40].strip('-')
        uid = uuid.uuid4().hex[:6]
        filename = f"{slug}-{uid}"

        # 3. Screenshot (non-blocking, fallback to None)
        await status_msg.edit_text("📸 Делаю превью...")
        screenshot_path = await take_screenshot(html, filename)

        # 4. Publish to GitHub
        await status_msg.edit_text("📤 Публикую...")
        url = await asyncio.to_thread(publish_to_github, html, filename)

        # 5. Send result
        await status_msg.delete()
        keyboard = get_retry_keyboard(user_prompt)

        if screenshot_path and os.path.exists(screenshot_path):
            photo = FSInputFile(screenshot_path)
            await target_msg.answer_photo(
                photo=photo,
                caption=(
                    f"✅ <b>Готово!</b>\n\n"
                    f"🔗 <a href=\"{url}\">Открыть сайт</a>"
                ),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            os.remove(screenshot_path)
        else:
            await target_msg.answer(
                f"✅ <b>Готово!</b>\n\n"
                f"🔗 <a href=\"{url}\">Открыть сайт</a>",
                parse_mode="HTML",
                reply_markup=keyboard,
            )

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка: {e}")

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
        print("Copy .env.example to .env and fill in the values.")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("🤖 Design Bot v2 started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
