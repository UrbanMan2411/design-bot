#!/usr/bin/env python3
"""
Design Bot — Telegram бот-дизайнер
Генерирует frontend-дизайны через OpenRouter и публикует на GitHub Pages.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()

# === Config ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/xiaomi/mimo-v2-pro")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
PAGES_BASE_URL = f"https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}"

# === System prompt (based on frontend-design-3 skill) ===
SYSTEM_PROMPT = """You are an expert frontend designer. Create distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics.

## Design Thinking
Before coding, understand the context:
- Purpose: What problem does this interface solve?
- Tone: Pick an extreme — brutally minimal, maximalist chaos, retro-futuristic, organic/natural, luxury/refined, playful/toy-like, editorial/magazine, brutalist/raw, art deco/geometric, soft/pastel, industrial/utilitative
- Differentiation: What makes this UNFORGETTABLE?

## Aesthetics Guidelines
- Typography: Use distinctive, beautiful fonts (Google Fonts). NEVER use Inter, Roboto, Arial, or system fonts
- Color: Cohesive palette with sharp accents. CSS variables for consistency
- Motion: CSS animations for micro-interactions. Staggered reveals on page load
- Layout: Unexpected layouts. Asymmetry. Overlap. Generous negative space OR controlled density
- Backgrounds: Gradient meshes, noise textures, geometric patterns, layered transparencies, dramatic shadows
- Vary between light/dark themes. No two designs should look the same

## Anti-Patterns
NEVER use: Inter, Roboto, Arial, system fonts, purple gradients on white, predictable layouts, cookie-cutter patterns

## Images (CRITICAL)
Include HIGH-QUALITY images from Unsplash. Use this URL format:
https://images.unsplash.com/photo-XXXXX?w=1200&q=80

Or use Unsplash Source for topic-based images:
https://source.unsplash.com/1200x800/?<relevant-keywords>

For example, for a church website use keywords like: church, stained-glass, community, bible, cross, sunlight, nature, prayer
For a restaurant: food, restaurant, chef, kitchen, dining
For a tech startup: technology, office, computer, innovation

Use 3-6 relevant images throughout the design. Make them hero backgrounds, section images, or gallery items.

## Output
Return ONLY a complete, self-contained HTML file with inline CSS and JS. 
The file must be production-grade, visually striking, and work standalone.
Use external Google Fonts links. Include real Unsplash images. Make it memorable."""


def extract_html(text: str) -> str:
    """Extract HTML from markdown code blocks or raw text."""
    if not isinstance(text, str):
        text = str(text)
    # Try to find ```html ... ``` blocks
    match = re.search(r'```(?:html)?\s*\n(.*?)```', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If it starts with <!DOCTYPE or <html, return as-is
    if text.strip().startswith(('<!DOCTYPE', '<html')):
        return text.strip()
    # Wrap in basic HTML if it's just fragments
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


async def take_screenshot(html: str, filename: str) -> str:
    """Render HTML and take a screenshot. Returns path to the PNG file."""
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.set_content(html, wait_until="networkidle")
        screenshot_path = f"/tmp/{filename}.png"
        await page.screenshot(path=screenshot_path, full_page=True)
        await browser.close()
        return screenshot_path
    if match:
        return match.group(1).strip()
    # If it starts with <!DOCTYPE or <html, return as-is
    if text.strip().startswith(('<!DOCTYPE', '<html')):
        return text.strip()
    # Wrap in basic HTML if it's just fragments
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


async def generate_design(user_prompt: str) -> str:
    """Call OpenRouter API to generate HTML design."""
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.9,
        "max_tokens": 8000,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                error = await resp.text()
                raise Exception(f"OpenRouter error {resp.status}: {error}")
            data = await resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                raise Exception(f"Empty response from API. Full response: {json.dumps(data, indent=2)}")
            return content


def publish_to_github(html: str, filename: str) -> str:
    """Push HTML file to GitHub repo for Pages. Returns the public URL."""
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)

    path = f"designs/{filename}.html"
    commit_message = f"Add design: {filename}"

    try:
        # Try to update existing file
        contents = repo.get_contents(path, ref=GITHUB_BRANCH)
        repo.update_file(path, commit_message, html, contents.sha, branch=GITHUB_BRANCH)
    except GithubException:
        # File doesn't exist, create it
        repo.create_file(path, commit_message, html, branch=GITHUB_BRANCH)

    return f"{PAGES_BASE_URL}/designs/{filename}.html"


# === Bot handlers ===
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎨 <b>Design Bot</b>\n\n"
        "Опиши дизайн, который хочешь — я сгенерирую HTML и опубликую на GitHub Pages.\n\n"
        "<b>Примеры:</b>\n"
        "• Лендинг для кофейни в стиле ретро\n"
        "• Портфолио фотографа, тёмная тема, минимализм\n"
        "• Карточка продукта для лавандового мыла\n\n"
        "Просто напиши, что нужно 👇",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Как пользоваться:</b>\n\n"
        "1️⃣ Напиши описание дизайна\n"
        "2️⃣ Бот сгенерирует HTML\n"
        "3️⃣ Получишь ссылку на GitHub Pages\n\n"
        "Чем детальнее опишешь — тем лучше результат.\n"
        "Укажи стиль, цвета, аудиторию, mood.",
        parse_mode="HTML",
    )


@router.message(F.text & ~F.text.startswith("/"))
async def handle_design_request(message: Message):
    user_prompt = message.text.strip()
    logger.info(f"Received prompt: {user_prompt}")
    if len(user_prompt) < 5:
        await message.answer("Опиши подробнее, что за дизайн нужен 🤔")
        return

    # Send "typing" action
    await message.bot.send_chat_action(message.chat.id, "typing")

    status_msg = await message.answer("⏳ Генерирую дизайн...")

    try:
        # Generate HTML via OpenRouter
        raw_response = await generate_design(user_prompt)
        html = extract_html(raw_response)

        # Generate unique filename
        slug = re.sub(r'[^a-z0-9]+', '-', user_prompt.lower())[:40].strip('-')
        uid = uuid.uuid4().hex[:6]
        filename = f"{slug}-{uid}"

        # Take screenshot
        await status_msg.edit_text("📸 Делаю превью...")
        screenshot_path = await take_screenshot(html, filename)

        # Publish to GitHub Pages
        await status_msg.edit_text("📤 Публикую на GitHub Pages...")

        url = publish_to_github(html, filename)

        # Send screenshot + result
        await status_msg.delete()
        
        from aiogram.types import FSInputFile
        photo = FSInputFile(screenshot_path)
        await message.answer_photo(
            photo=photo,
            caption=(
                f"✅ <b>Готово!</b>\n\n"
                f"🔗 <a href=\"{url}\">{url}</a>\n\n"
                f"📝 <i>{user_prompt}</i>"
            ),
            parse_mode="HTML",
        )
        
        # Clean up screenshot
        os.remove(screenshot_path)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Ошибка: {e}")


async def main():
    if not all([BOT_TOKEN, GITHUB_TOKEN, GITHUB_REPO]):
        missing = []
        if not BOT_TOKEN: missing.append("BOT_TOKEN")
        if not GITHUB_TOKEN: missing.append("GITHUB_TOKEN")
        if not GITHUB_REPO: missing.append("GITHUB_REPO")
        print(f"❌ Missing env vars: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in the values.")
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("🤖 Design Bot started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
