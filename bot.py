#!/usr/bin/env python3
"""
Design Bot v3 — Telegram бот-дизайнер
Генерирует frontend-дизайны через AI и публикует на GitHub Pages.
"""

import asyncio
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
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

# === State ===
user_locks: dict[int, bool] = defaultdict(bool)
user_history: dict[int, list[dict]] = defaultdict(list)  # user_id -> [{prompt, url, filename, time}]

# === Themed Unsplash images ===
THEME_IMAGES = {
    "church|церковь|призван|бог|вера|молитв|крест": [
        "photo-1548625149-fc4a24cf7e90", "photo-1507692049790-de58290a4334",
        "photo-1438761681033-6461ffad8d80", "photo-1543722530-d2c3201371e7",
    ],
    "coffee|кофе|кофейня|кафе|чай": [
        "photo-1495474472287-4d71bcdd2085", "photo-1509042239860-f550ce710b93",
        "photo-1501339847302-ac426a4a7cbb", "photo-1442512595331-e89e73853f31",
    ],
    "restaurant|ресторан|еда|food|кухня|меню|пицц|бургер|суши": [
        "photo-1414235077428-338989a2e8c0", "photo-1517248135467-4c7edcad34c4",
        "photo-1504674900247-0877df9cc836", "photo-1559339352-11d035aa65de",
    ],
    "tech|стартап|AI|технолог|IT|софт|приложен|SaaS|программ": [
        "photo-1518770660439-4636190af475", "photo-1504384308090-c894fdcc538d",
        "photo-1550751827-4bd374c3f58b", "photo-1535378917042-10a22c95931a",
    ],
    "photo|фото|портфолио|камера|сним": [
        "photo-1452587925148-ce544e77e70d", "photo-1493863641943-9b68992a8d07",
        "photo-1516035069371-29a1b244cc32", "photo-1554080353-321e452ccf19",
    ],
    "fitness|спорт|зал|тренировк|здоров|йога": [
        "photo-1534438327276-14e5300c3a48", "photo-1571019613454-1cb2f99b2d8b",
        "photo-1549060279-7e168fcee0c2", "photo-1517836357463-d25dfeac3438",
    ],
    "fashion|мод|одежд|стиль|бренд|коллекц": [
        "photo-1558618666-fcd25c85f82e", "photo-1445205170230-053b83016050",
        "photo-1483985988355-763728e1935b", "photo-1490481651871-ab68de25d43d",
    ],
    "travel|путешеств|тур|отдых|пляж|горы|отел": [
        "photo-1488646953014-85cb44e25828", "photo-1502602898657-3e91760cbb34",
        "photo-1506905925346-21bda4d32df4", "photo-1476514525535-07fb3b4ae5f1",
    ],
    "music|музык|звук|концерт|трек|альбом": [
        "photo-1511379938547-c1f69419868d", "photo-1514320291840-2e0a9bf2a9ae",
        "photo-1493225457124-a3eb161ffa5f", "photo-1470225620780-dba8ba36b745",
    ],
    "real.estate|недвижим|квартир|дом|интерьер|ремонт": [
        "photo-1502672260266-1c1ef2d93688", "photo-1560448204-e02f11c3d0e2",
        "photo-1505691938895-1758d7feb511", "photo-1560185893-a55cbc8c57e8",
    ],
    "medical|медицин|здоров|клиник|врач|больниц": [
        "photo-1576091160399-112ba8d25d1d", "photo-1519494026892-80bbd2d6fd0d",
        "photo-1538108149393-fbbd81895907", "photo-1579684385127-1ef15d508118",
    ],
    "education|образован|школ|универ|курс|обучен": [
        "photo-1503676260728-1c00da094a0b", "photo-1523050854058-8df90110c9f1",
        "photo-1522202176988-66273c2fd55f", "photo-1427504494785-3a9ca7044f45",
    ],
    "law|юрид|адвокат|закон|право|консалт": [
        "photo-1589829545856-d10d557cf95f", "photo-1479142506502-19b3a3b7ff33",
        "photo-1521791055366-0d553872125f", "photo-1450101499163-c8848c66ca85",
    ],
    "default": [
        "photo-1497366216548-37526070297c", "photo-1497366811353-6870744d04b2",
        "photo-1486406146926-c627a92ad1ab", "photo-1497215728101-856f4ea42174",
    ],
}


def get_theme_images(prompt: str, count: int = 4) -> list[str]:
    """Get themed image URLs based on prompt keywords."""
    prompt_lower = prompt.lower()
    for pattern, photos in THEME_IMAGES.items():
        if re.search(pattern, prompt_lower):
            break
    else:
        photos = THEME_IMAGES["default"]

    urls = []
    for i, photo_id in enumerate(photos[:count]):
        width = 1200 if i == 0 else 800
        height = 800 if i == 0 else 600
        urls.append(f"https://images.unsplash.com/photo-{photo_id}?w={width}&h={height}&fit=crop&q=80")
    return urls


# === System prompt ===
SYSTEM_PROMPT_TEMPLATE = """You are an expert frontend designer. Create distinctive, production-grade frontend interfaces.

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

## Responsive Design (CRITICAL)
The HTML MUST be fully responsive and mobile-first:
- Use CSS media queries for breakpoints: 390px (mobile), 768px (tablet), 1280px (desktop)
- Fluid typography: clamp() for font sizes
- Flexible grids: CSS Grid or Flexbox with wrapping
- Images: max-width: 100%, height: auto
- Touch-friendly: buttons min 44px, links spaced apart
- Hide/show elements per viewport if needed
- Test: must look stunning on both iPhone and desktop

## Images (IMPORTANT)
Use these EXACT image URLs in your design:
{image_urls}

Use them as hero backgrounds, section images, gallery items. Mix wide (1200x800) and square (800x600) formats.

## Output
Return ONLY a complete, self-contained HTML file with inline CSS and JS.
Use Google Fonts links. Make it visually stunning and memorable.
The design MUST work perfectly on mobile (390px) and desktop (1280px)."""


def build_system_prompt(user_prompt: str) -> str:
    """Build system prompt with themed images."""
    images = get_theme_images(user_prompt, 4)
    image_list = "\n".join(f"- {url}" for url in images)
    return SYSTEM_PROMPT_TEMPLATE.format(image_urls=image_list)


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


async def generate_design(user_prompt: str) -> str:
    """Call AI API to generate HTML design."""
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    system_prompt = build_system_prompt(user_prompt)

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
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


async def take_screenshots(html: str, filename: str) -> tuple[str | None, str | None]:
    """Render HTML and take desktop + mobile screenshots."""
    desktop_path, mobile_path = None, None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()

            # Desktop screenshot
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.set_content(html, wait_until="networkidle", timeout=30000)
            desktop_path = f"/tmp/{filename}-desktop.png"
            await page.screenshot(path=desktop_path, full_page=True)
            await page.close()

            # Mobile screenshot
            page = await browser.new_page(viewport={"width": 390, "height": 844})
            await page.set_content(html, wait_until="networkidle", timeout=30000)
            mobile_path = f"/tmp/{filename}-mobile.png"
            await page.screenshot(path=mobile_path, full_page=True)
            await page.close()

            await browser.close()
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")

    return desktop_path, mobile_path


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
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"retry:{prompt[:40]}"),
            InlineKeyboardButton(text="🎨 Другой стиль", callback_data=f"style:{prompt[:40]}"),
        ],
        [
            InlineKeyboardButton(text="📱 Мобильная версия", callback_data=f"mobile:{prompt[:40]}"),
        ]
    ])


# === Handlers ===
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎨 <b>Design Bot v3</b>\n\n"
        "Опиши дизайн — получишь HTML + скриншот + ссылку.\n\n"
        "<b>Примеры:</b>\n"
        "• Лендинг для кофейни, ретро стиль\n"
        "• Портфолио фотографа, минимализм\n"
        "• Сайт церкви «Высшее призвание»\n"
        "• Карточка SaaS для AI-стартапа\n\n"
        "Команды: /history /help",
        parse_mode="HTML",
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "<b>Как пользоваться:</b>\n\n"
        "1️⃣ Напиши описание дизайна\n"
        "2️⃣ Получишь скриншот + ссылку\n\n"
        "🔄 Ещё вариант — новая генерация\n"
        "🎨 Другой стиль — изменить стиль\n"
        "📱 Мобильная версия — превью на телефоне\n\n"
        "/history — последние дизайны",
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
        time_str = item["time"].strftime("%H:%M")
        text += f"{i}. <i>{item['prompt'][:50]}</i>\n   🔗 <a href=\"{item['url']}\">Открыть</a> • {time_str}\n\n"

    await message.answer(text, parse_mode="HTML")


@router.callback_query(F.data.startswith("retry:"))
async def cb_retry(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer("Генерирую новый вариант...")
    await process_design(callback.message, callback.from_user.id, prompt)


@router.callback_query(F.data.startswith("style:"))
async def cb_style(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer()
    await callback.message.answer(
        f"Опиши стиль для: <i>{prompt[:50]}</i>\n\n"
        "Например: тёмный минимализм, неоновый ретро, природный organic",
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("mobile:"))
async def cb_mobile(callback: CallbackQuery):
    await callback.answer("Мобильная версия в следующей генерации будет отдельным скриншотом")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_design_request(message: Message):
    await process_design(message, message.from_user.id, message.text.strip())


async def process_design(target_msg: Message, user_id: int, user_prompt: str):
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
        await status_msg.edit_text("🤖 AI думает над дизайном...")
        raw_response = await generate_design(user_prompt)
        html = extract_html(raw_response)

        # 2. Filename
        slug = re.sub(r'[^a-z0-9]+', '-', user_prompt.lower())[:40].strip('-')
        uid = uuid.uuid4().hex[:6]
        filename = f"{slug}-{uid}"

        # 3. Screenshots (desktop + mobile)
        await status_msg.edit_text("📸 Делаю превью (desktop + mobile)...")
        desktop_path, mobile_path = await take_screenshots(html, filename)

        # 4. Publish to GitHub
        await status_msg.edit_text("📤 Публикую...")
        url = await asyncio.to_thread(publish_to_github, html, filename)

        # 5. Save to history
        user_history[user_id].append({
            "prompt": user_prompt,
            "url": url,
            "filename": filename,
            "time": datetime.now(),
        })

        # 6. Send result
        await status_msg.delete()
        keyboard = get_retry_keyboard(user_prompt)

        has_desktop = desktop_path and os.path.exists(desktop_path)
        has_mobile = mobile_path and os.path.exists(mobile_path)

        if has_desktop and has_mobile:
            # Send as media group (desktop + mobile)
            media = [
                InputMediaPhoto(media=FSInputFile(desktop_path), caption=(
                    f"✅ <b>Готово!</b>\n\n"
                    f"🔗 <a href=\"{url}\">Открыть сайт</a>\n"
                    f"📐 Desktop (1280px) + Mobile (390px)"
                ), parse_mode="HTML"),
                InputMediaPhoto(media=FSInputFile(mobile_path)),
            ]
            await target_msg.answer_media_group(media)
            await target_msg.answer("Действия:", reply_markup=keyboard)
        elif has_desktop:
            await target_msg.answer_photo(
                photo=FSInputFile(desktop_path),
                caption=f"✅ <b>Готово!</b>\n\n🔗 <a href=\"{url}\">Открыть сайт</a>",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        else:
            await target_msg.answer(
                f"✅ <b>Готово!</b>\n\n🔗 <a href=\"{url}\">Открыть сайт</a>",
                parse_mode="HTML",
                reply_markup=keyboard,
            )

        # Cleanup
        for path in [desktop_path, mobile_path]:
            if path and os.path.exists(path):
                os.remove(path)

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
        return

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    print("🤖 Design Bot v3 started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
