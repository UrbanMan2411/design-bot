#!/usr/bin/env python3
"""
Design Bot v5 — Telegram бот-дизайнер
Генерирует frontend-дизайны через AI и публикует на GitHub Pages.
"""

import asyncio
import io
import json
import logging
import os
import random
import re
import zipfile
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from html.parser import HTMLParser

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, FSInputFile, BufferedInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto,
)
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
MAX_DESIGNS_PER_DAY = int(os.getenv("MAX_DESIGNS_PER_DAY", "20"))
REFERRAL_BONUS = 5  # extra designs per referral

# === State ===
user_locks: dict[int, bool] = defaultdict(bool)
user_history: dict[int, list[dict]] = defaultdict(list)
user_models: dict[int, str] = defaultdict(lambda: OPENROUTER_MODEL)
user_daily_count: dict[int, int] = defaultdict(int)
user_referrals: dict[int, set] = defaultdict(set)
user_referred_by: dict[int, int] = {}
user_bonus: dict[int, int] = defaultdict(int)
user_feedback: dict[str, str] = {}
user_last_request: dict[int, datetime] = {}
COOLDOWN_SECONDS = 0  # disabled
last_reset: datetime = datetime.now()

AVAILABLE_MODELS = {
    "claude": "kr/claude-haiku-4.5",
    "gpt": "openrouter/openai/gpt-4.1-mini",
    "qwen": "qwen/qwen3-coder-flash",
    "deepseek": "openrouter/deepseek/deepseek-chat",
}


# === HTML Validator ===
class HTMLValidator(HTMLParser):
    def __init__(self):
        super().__init__()
        self.has_doctype = False
        self.has_html = False
        self.has_head = False
        self.has_body = False
        self.has_title = False
        self.has_viewport = False
        self.errors: list[str] = []

    def handle_decl(self, decl):
        if "DOCTYPE" in decl.upper():
            self.has_doctype = True

    def handle_starttag(self, tag, attrs):
        if tag == "html": self.has_html = True
        elif tag == "head": self.has_head = True
        elif tag == "body": self.has_body = True
        elif tag == "title": self.has_title = True
        elif tag == "meta":
            for name, value in attrs:
                if name == "name" and value == "viewport":
                    self.has_viewport = True

    def validate(self, html: str) -> list[str]:
        self.errors = []
        self.feed(html)
        if not self.has_doctype: self.errors.append("Missing DOCTYPE")
        if not self.has_html: self.errors.append("Missing <html>")
        if not self.has_head: self.errors.append("Missing <head>")
        if not self.has_body: self.errors.append("Missing <body>")
        if not self.has_title: self.errors.append("Missing <title>")
        if not self.has_viewport: self.errors.append("Missing viewport")
        return self.errors


# === Theme keywords for image search ===
THEME_KEYWORDS = {
    "church|церковь|призван|бог|вера|молитв|крест": ["church", "cathedral", "cross", "sunset", "nature"],
    "coffee|кофе|кофейня|кафе|чай": ["coffee", "cafe", "latte", "bakery", "interior"],
    "restaurant|ресторан|еда|food|кухня|меню|пицц|бургер|суши": ["restaurant", "food", "dining", "chef", "kitchen"],
    "tech|стартап|AI|технолог|IT|софт|приложен|SaaS|программ": ["technology", "computer", "office", "startup", "coding"],
    "photo|фото|портфолио|камера|сним": ["camera", "photography", "studio", "portrait", "gallery"],
    "fitness|спорт|зал|тренировк|здоров|йога": ["fitness", "gym", "yoga", "running", "workout"],
    "fashion|мод|одежд|стиль|бренд|коллекц": ["fashion", "model", "clothing", "style", "runway"],
    "travel|путешеств|тур|отдых|пляж|горы|отел": ["travel", "beach", "mountains", "hotel", "adventure"],
    "music|музык|звук|концерт|трек|альбом": ["music", "concert", "guitar", "studio", "instrument"],
    "real.estate|недвижим|квартир|дом|интерьер|ремонт": ["house", "interior", "architecture", "apartment", "design"],
    "medical|медицин|доров|клиник|врач|больниц": ["medical", "hospital", "doctor", "health", "laboratory"],
    "education|образован|школ|универ|курс|обучен": ["education", "school", "students", "library", "classroom"],
    "default": ["business", "office", "team", "modern", "architecture"],
}


def get_theme_images(prompt: str, count: int = 5) -> list[str]:
    """Get image URLs based on prompt keywords using LoremFlickr."""
    prompt_lower = prompt.lower()
    keywords = THEME_KEYWORDS["default"]
    for pattern, kw in THEME_KEYWORDS.items():
        if re.search(pattern, prompt_lower):
            keywords = kw
            break

    selected = random.sample(keywords, min(count, len(keywords)))
    sizes = [(1200, 800), (800, 600), (600, 400), (800, 800), (1200, 600)]
    urls = []
    for i, keyword in enumerate(selected):
        w, h = sizes[i % len(sizes)]
        urls.append(f"https://loremflickr.com/{w}/{h}/{keyword}?lock={random.randint(1, 99999)}")
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
- Breakpoints: 390px mobile, 768px tablet, 1280px desktop
- Fluid typography: clamp() for font sizes
- Flexible grids: CSS Grid/Flexbox with wrapping
- Touch-friendly: buttons min 44px, spaced links
- Images: max-width: 100%, height: auto

## SEO (IMPORTANT)
Include in <head>:
- <meta name="description" content="...">
- <meta property="og:title" content="...">
- <meta property="og:description" content="...">
- <meta property="og:image" content="[first image URL]">
- <meta property="og:type" content="website">
- <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎨</text></svg>">

## Images
Use these EXACT URLs — use DIFFERENT images in DIFFERENT places (hero, gallery, cards):
{image_urls}

Don't repeat the same image twice. Wide (1200x800) for heroes, square for cards.

## Output
Return ONLY a complete, self-contained HTML file with inline CSS and JS.
Use Google Fonts. Include viewport meta. All images must have alt attributes.
Make it stunning on mobile and desktop."""


def build_system_prompt(user_prompt: str) -> str:
    images = get_theme_images(user_prompt, 5)
    image_list = "\n".join(f"- {url}" for url in images)
    return SYSTEM_PROMPT_TEMPLATE.format(image_urls=image_list)


# === Core functions ===

def extract_html(text: str) -> str:
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


def fix_html_issues(html: str) -> str:
    if 'viewport' not in html:
        html = html.replace('<head>', '<head>\n<meta name="viewport" content="width=device-width, initial-scale=1.0">', 1)
    if 'charset' not in html:
        html = html.replace('<head>', '<head>\n<meta charset="UTF-8">', 1)
    html = re.sub(r'<img(?![^>]*alt=)([^>]*)>', r'<img\1 alt="Image">', html)
    return html


def add_watermark(html: str) -> str:
    """Add small watermark to bottom of page."""
    watermark = """
<div style="position:fixed;bottom:8px;right:12px;font-size:11px;color:rgba(128,128,128,0.5);font-family:sans-serif;z-index:9999;pointer-events:none;">
  Made with <a href="https://t.me/LandAIpagebot" style="color:rgba(128,128,128,0.5);text-decoration:none;">LandingAI</a>
</div>"""
    html = html.replace('</body>', watermark + '\n</body>')
    return html


async def generate_design(user_prompt: str) -> str:
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

    last_error = None
    for attempt in range(3):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers,
                                        timeout=aiohttp.ClientTimeout(total=120)) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        raise Exception(f"API error {resp.status}: {error}")
                    data = await resp.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    if not content:
                        raise Exception(f"Empty response: {json.dumps(data)[:200]}")
                    return content
        except (aiohttp.ClientError, Exception) as e:
            last_error = e
            logger.warning(f"Attempt {attempt+1}/3 failed: {e}")
            if attempt < 2:
                await asyncio.sleep(3)
    raise Exception(f"API failed after 3 attempts: {last_error}")


async def take_screenshots(html: str, filename: str) -> tuple[str | None, str | None]:
    desktop_path, mobile_path = None, None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.set_content(html, wait_until="networkidle", timeout=30000)
            desktop_path = f"/tmp/{filename}-desktop.png"
            await page.screenshot(path=desktop_path, full_page=True)
            await page.close()
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
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    path = f"designs/{filename}.html"
    try:
        contents = repo.get_contents(path, ref=GITHUB_BRANCH)
        repo.update_file(path, f"Update: {filename}", html, contents.sha, branch=GITHUB_BRANCH)
    except GithubException:
        repo.create_file(path, f"Add: {filename}", html, branch=GITHUB_BRANCH)
    return f"{PAGES_BASE_URL}/designs/{filename}.html"


def create_zip(html: str, filename: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{filename}/index.html", html)
    return buf.getvalue()


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


# === Keyboards ===

def get_style_keyboard(prompt: str) -> InlineKeyboardMarkup:
    # Max 64 bytes per callback_data. "gen:" + 25 chars + ":" + style = ~45 max
    p = prompt[:25]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌑 Минимализм", callback_data=f"gen:{p}:dark"),
            InlineKeyboardButton(text="🌈 Яркий", callback_data=f"gen:{p}:color"),
        ],
        [
            InlineKeyboardButton(text="🏛 Премиум", callback_data=f"gen:{p}:luxury"),
            InlineKeyboardButton(text="🌿 Органик", callback_data=f"gen:{p}:organic"),
        ],
        [
            InlineKeyboardButton(text="⚡ Ретро", callback_data=f"gen:{p}:retro"),
            InlineKeyboardButton(text="🔥 Брутализм", callback_data=f"gen:{p}:brutal"),
        ],
        [
            InlineKeyboardButton(text="✨ Свой выбор AI", callback_data=f"gen:{p}:"),
        ]
    ])


def get_result_keyboard(prompt: str, filename: str = "") -> InlineKeyboardMarkup:
    fn = filename[:15] if filename else prompt[:15]
    p = prompt[:25]
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Ещё", callback_data=f"retry:{p}"),
            InlineKeyboardButton(text="🎨 Стиль", callback_data=f"pick:{p}"),
        ],
        [
            InlineKeyboardButton(text="🔀 A/B", callback_data=f"ab:{p}"),
            InlineKeyboardButton(text="📦 ZIP", callback_data=f"dl:{fn}"),
        ],
        [
            InlineKeyboardButton(text="👍", callback_data=f"like:{fn}"),
            InlineKeyboardButton(text="👎", callback_data=f"no:{fn}"),
        ]
    ])


# === Handlers ===
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    # Check for referral code
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
            if referrer_id != message.from_user.id and message.from_user.id not in user_referred_by:
                user_referred_by[message.from_user.id] = referrer_id
                user_referrals[referrer_id].add(message.from_user.id)
                user_bonus[referrer_id] += REFERRAL_BONUS
                await message.answer(
                    f"🎉 Вы приглашены! Пригласитель получит +{REFERRAL_BONUS} дизайнов в день."
                )
        except (ValueError, IndexError):
            pass

    referral_link = f"https://t.me/LandAIpagebot?start=ref{message.from_user.id}"
    await message.answer(
        "🎨 <b>Design Bot v5</b>\n\n"
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
        "<b>Кнопки под результатом:</b>\n"
        "🔄 — новый вариант\n"
        "🎨 — сменить стиль\n"
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
    likes = sum(1 for f in user_feedback.values() if f == "like")
    dislikes = sum(1 for f in user_feedback.values() if f == "dislike")
    text = (
        f"<b>📊 Статистика</b>\n\n"
        f"Всего дизайнов: <b>{total}</b>\n"
        f"Сегодня: <b>{today}/{limit}</b>\n"
        f"Рефералы: <b>{refs}</b> (+{refs * REFERRAL_BONUS} дизайнов)\n"
        f"Лайки: <b>{likes}</b> • Дизлайки: <b>{dislikes}</b>"
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
        f"Бонус: <b>+{bonus}</b> дизайнов/день\n\n"
        f"Нажми на ссылку чтобы скопировать.",
        parse_mode="HTML",
    )


@router.message(Command("gallery"))
async def cmd_gallery(message: Message):
    gallery_url = f"{PAGES_BASE_URL}/"
    await message.answer(
        f"🖼 <b>Галерея дизайнов</b>\n\n"
        f"Все сгенерированные дизайны:\n"
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
    
    # Map short style names to full descriptions
    style_map = {
        "dark": "minimal dark elegant",
        "color": "vibrant colorful energetic",
        "luxury": "luxury premium elegant gold",
        "organic": "organic natural earthy warm",
        "retro": "retro 80s neon synthwave",
        "brutal": "brutalist bold raw industrial",
    }
    full_style = style_map.get(style, style)
    full_prompt = f"{prompt}. Style: {full_style}" if full_style else prompt
    await callback.answer("Генерирую...")
    await process_design(callback.message, callback.from_user.id, full_prompt, style=style)


@router.callback_query(F.data.startswith("retry:"))
async def cb_retry(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer("Генерирую новый вариант...")
    await process_design(callback.message, callback.from_user.id, prompt)


@router.callback_query(F.data.startswith("like:"))
async def cb_like(callback: CallbackQuery):
    fn = callback.data[5:]
    # Find full filename from history
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
            await callback.answer("👎 Учтём! Попробуй другой стиль.")
            return
    await callback.answer("Дизайн не найден")


@router.callback_query(F.data.startswith("ab:"))
async def cb_ab_test(callback: CallbackQuery):
    prompt = callback.data[3:]
    await callback.answer("Генерирую 2 варианта для A/B теста...")
    # Generate two designs with different styles
    styles = ["minimal dark", "vibrant colorful"]
    for style in styles:
        full_prompt = f"{prompt}\nStyle: {style}"
        await process_design(callback.message, callback.from_user.id, full_prompt, style=style)
        await asyncio.sleep(1)  # Small delay between generations


@router.callback_query(F.data.startswith("dl:"))
async def cb_download(callback: CallbackQuery):
    fn = callback.data[3:]
    for item in reversed(user_history.get(callback.from_user.id, [])):
        if fn in item["filename"]:
            try:
                g = Github(GITHUB_TOKEN)
                repo = g.get_repo(GITHUB_REPO)
                file = repo.get_contents(f"designs/{item['filename']}.html", ref=GITHUB_BRANCH)
                html = file.decoded_content.decode()
                zip_data = create_zip(html, item["filename"])
                await callback.message.answer_document(
                    BufferedInputFile(zip_data, filename=f"{item['filename']}.zip"),
                    caption=f"📦 <b>{item['filename']}</b>",
                    parse_mode="HTML",
                )
            except Exception as e:
                await callback.answer(f"Ошибка: {e}")
            return
    await callback.answer("Дизайн не найден")


# === Main handler ===

# @router.message(F.text & F.text.startswith("http"))
# async def handle_reference_url(message: Message):
    """Handle URL reference — analyze and generate similar design."""
    url = message.text.strip()
    if not re.match(r'https?://', url):
        await message.answer("Отправьте корректную ссылку (начинается с http:// или https://)")
        return

    user_id = message.from_user.id
    if user_locks[user_id]:
        await message.answer("⏳ Подожди, предыдущий дизайн ещё генерируется...")
        return

    user_locks[user_id] = True
    status_msg = await message.answer("🔍 Анализирую референс...")

    try:
        # 1. Fetch page HTML
        await status_msg.edit_text("📥 Скачиваю страницу...")
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    await status_msg.edit_text(f"❌ Не удалось загрузить страницу (HTTP {resp.status})")
                    return
                page_html = await resp.text()

        # 2. Take screenshot of the reference
        await status_msg.edit_text("📸 Делаю скриншот референса...")
        ref_slug = re.sub(r'[^a-z0-9]+', '-', url.lower())[:30].strip('-')
        ref_uid = uuid.uuid4().hex[:6]
        ref_filename = f"ref-{ref_slug}-{ref_uid}"
        
        ref_desktop, _ = await take_screenshots(page_html, ref_filename)

        # 3. Extract key info from HTML (styles, structure)
        style_info = extract_style_info(page_html)

        # 4. Generate similar design with AI
        await status_msg.edit_text("🤖 Генерирую похожий дизайн...")
        
        # Trim reference HTML for AI context
        import html as html_module
        clean_html = re.sub(r'<script[^>]*>.*?</script>', '', html_page, flags=re.S)
        clean_html = re.sub(r'<style[^>]*>.*?</style>', '', clean_html, flags=re.S)
        clean_html = re.sub(r'<svg[^>]*>.*?</svg>', '', clean_html, flags=re.S)
        clean_html = re.sub(r'\s+', ' ', clean_html).strip()
        # Take first 3000 chars as structure reference
        html_snippet = clean_html[:3000]

        clone_prompt = f"""Here is HTML code from a website. Rewrite it as a NEW, DIFFERENT website with original content. Keep the same visual structure and styling approach but change ALL text, images, and business type.

ORIGINAL HTML:
{html_snippet}

Create a completely new landing page. Change:
- All text content (headings, paragraphs, buttons)
- All images (use different Unsplash URLs)
- Business type and purpose
- Keep the visual style, layout, and CSS approach

Make it responsive, use Google Fonts, include SEO tags.

Return ONLY a complete HTML file."""

        raw_response = await generate_design(clone_prompt)
        html = extract_html(raw_response)
        html = fix_html_issues(html)
        html = add_watermark(html)

        # 5. Screenshot generated design
        slug = re.sub(r'[^a-z0-9]+', '-', url.lower())[:30].strip('-')
        uid = uuid.uuid4().hex[:6]
        filename = f"{slug}-{uid}"
        
        await status_msg.edit_text("📸 Делаю превью...")
        desktop_path, mobile_path = await take_screenshots(html, filename)

        # 6. Publish
        await status_msg.edit_text("📤 Публикую...")
        pub_url = await asyncio.to_thread(publish_to_github, html, filename)

        # 7. Track
        user_daily_count[user_id] += 1
        user_last_request[user_id] = datetime.now()
        user_history[user_id].append({
            "prompt": f"Clone: {url}",
            "url": pub_url,
            "filename": filename,
            "style": "reference",
            "time": datetime.now(),
            "model": OPENROUTER_MODEL,
        })

        # 8. Send result with reference preview
        await status_msg.delete()
        keyboard = get_result_keyboard(url[:25], filename)

        caption = (
            f"✅ <b>Похожий дизайн готов!</b>\n\n"
            f"📎 Референс: <a href=\"{url}\">{url[:40]}...</a>\n"
            f"🔗 Результат: <a href=\"{pub_url}\">Открыть</a>"
        )

        # Send reference screenshot + result
        has_ref = ref_desktop and os.path.exists(ref_desktop)
        has_desktop = desktop_path and os.path.exists(desktop_path)

        if has_ref and has_desktop:
            media = [
                InputMediaPhoto(media=FSInputFile(ref_desktop), caption=f"📎 <b>Референс:</b> {url[:30]}...", parse_mode="HTML"),
                InputMediaPhoto(media=FSInputFile(desktop_path)),
            ]
            await message.answer_media_group(media)
            await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)
        elif has_desktop:
            await message.answer_photo(
                photo=FSInputFile(desktop_path), caption=caption,
                parse_mode="HTML", reply_markup=keyboard,
            )
        else:
            await message.answer(caption, parse_mode="HTML", reply_markup=keyboard)

        # Cleanup
        for path in [ref_desktop, desktop_path, mobile_path]:
            if path and os.path.exists(path):
                os.remove(path)

    except Exception as e:
        logger.error(f"Reference error: {e}", exc_info=True)
        try:
            await status_msg.edit_text(f"❌ Ошибка: {e}")
        except Exception:
            await message.answer(f"❌ Ошибка: {e}")

    finally:
        user_locks[user_id] = False


def extract_style_info(html: str) -> str:
    """Deep style analysis from HTML reference."""
    lines = []

    # Colors
    color_set = set(re.findall(r'(?:background|color|border-color):\s*(#[0-9a-fA-F]{3,8})', html))
    colors = list(color_set)[:10]
    if colors:
        lines.append(f"COLOR PALETTE:\n{', '.join(colors)}")

    # Fonts
    font_set = set()
    for m in re.findall(r"font-family:\s*['\"]?([^;'\"\},]+)", html):
        f = m.strip()
        if 2 < len(f) < 50:
            font_set.add(f)
    fonts = list(font_set)[:5]
    if fonts:
        lines.append(f"FONTS:\n{', '.join(fonts)}")

    # Layout structure
    sections = []
    bt = html.lower()
    if '<nav' in bt or 'header' in bt: sections.append('Navigation/Header')
    if 'hero' in bt or 'banner' in bt: sections.append('Hero section with CTA')
    if 'feature' in bt or 'service' in bt: sections.append('Features/Services grid')
    if 'testimonial' in bt or 'review' in bt: sections.append('Testimonials')
    if 'pricing' in bt or 'plan' in bt: sections.append('Pricing table')
    if 'gallery' in bt or 'portfolio' in bt: sections.append('Gallery')
    if 'about' in bt or 'team' in bt: sections.append('About/Team')
    if 'contact' in bt or 'form' in bt: sections.append('Contact form')
    if 'faq' in bt: sections.append('FAQ')
    if 'footer' in bt: sections.append('Footer')
    if sections:
        lines.append(f"LAYOUT (top to bottom):\n{' → '.join(sections)}")

    # Visual style
    styles = []
    r_match = re.search(r'border-radius:\s*(\d+)px', html)
    if r_match:
        r = int(r_match.group(1))
        styles.append(f"Rounded corners ({r}px)" if r > 10 else "Sharp corners")
    if re.search(r'gradient', html, re.I): styles.append('Uses gradients')
    if re.search(r'box-shadow', html, re.I): styles.append('Has shadows/depth')
    if re.search(r'animation|@keyframes', html, re.I): styles.append('Animated')
    if re.search(r'background:\s*#[012][012][012]', html, re.I): styles.append('Dark theme')
    if re.search(r'background:\s*#[fF]{3,6}', html, re.I): styles.append('Light theme')
    if re.search(r'backdrop-filter|blur', html, re.I): styles.append('Glassmorphism')
    if re.search(r'uppercase', html, re.I): styles.append('Uppercase text')
    if re.search(r'letter-spacing', html, re.I): styles.append('Letter-spacing')
    if styles:
        lines.append(f"VISUAL STYLE:\n{', '.join(styles)}")

    # Headings
    h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)
    if h1_match:
        h1_text = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()[:100]
        lines.append(f"H1: {h1_text}")
    h2s = [re.sub(r'<[^>]+>', '', h).strip()[:60] for h in re.findall(r'<h2[^>]*>(.*?)</h2>', html, re.I | re.S)[:5]]
    if h2s:
        lines.append(f"H2s: {' | '.join(h2s)}")

    # CSS variables
    css_vars = re.findall(r'--[a-z-]+:\s*[^;]+', html)[:10]
    if css_vars:
        lines.append(f"CSS VARIABLES:\n{chr(10).join(css_vars)}")

    return '\n\n'.join(lines) if lines else 'Standard modern landing page'


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

    # Cooldown check (disabled)
    if COOLDOWN_SECONDS > 0:
        last = user_last_request.get(user_id)
        if last:
            elapsed_since_last = (datetime.now() - last).total_seconds()
            if elapsed_since_last < COOLDOWN_SECONDS:
                remaining_cd = int(COOLDOWN_SECONDS - elapsed_since_last)
                await target_msg.answer(
                    f"⏳ Подожди <b>{remaining_cd}с</b> перед следующим запросом.",
                    parse_mode="HTML",
                )
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
        validator = HTMLValidator()
        issues = validator.validate(html)
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
            "model": user_models.get(user_id, OPENROUTER_MODEL),
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

    print("🤖 Design Bot v5 started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
