#!/usr/bin/env python3
"""
Design Bot v4 — Telegram бот-дизайнер
Генерирует frontend-дизайны через AI и публикует на GitHub Pages.
"""

import asyncio
import io
import json
import logging
import os
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

# === State ===
user_locks: dict[int, bool] = defaultdict(bool)
user_history: dict[int, list[dict]] = defaultdict(list)
user_models: dict[int, str] = defaultdict(lambda: OPENROUTER_MODEL)
user_daily_count: dict[int, int] = defaultdict(int)
last_reset: datetime = datetime.now()

# === Available models ===
AVAILABLE_MODELS = {
    "claude": "kr/claude-haiku-4.5",
    "gpt": "openrouter/openai/gpt-4.1-mini",
    "gemini": "openrouter/google/gemini-2.5-flash-lite",
    "qwen": "qwen/qwen3-coder-flash",
    "deepseek": "openrouter/deepseek/deepseek-chat",
}


# === HTML Validator ===
class HTMLValidator(HTMLParser):
    """Basic HTML structure validator."""
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
        if not self.has_html: self.errors.append("Missing <html> tag")
        if not self.has_head: self.errors.append("Missing <head> tag")
        if not self.has_body: self.errors.append("Missing <body> tag")
        if not self.has_title: self.errors.append("Missing <title> tag")
        if not self.has_viewport: self.errors.append("Missing viewport meta tag")
        if "<img" in html and 'alt=' not in html: self.errors.append("Images missing alt attributes")
        return self.errors


# === Themed images (verified Unsplash photo IDs) ===
THEME_IMAGES = {
    "church|церковь|призван|бог|вера|молитв|крест": [
        "1507692049790-de58290a4334", "1543722530-d2c3201371e7",
        "1444703686981-a3abbc4d4fe3", "1519389950473-47ba0277781c",
        "1500382017468-9049fed747ef", "1494783367193-149034c05e8f",
        "1551641506-ee5bf4cb45f1", "1473448912268-2022ce9509d8",
    ],
    "coffee|кофе|кофейня|кафе|чай": [
        "1495474472287-4d71bcdd2085", "1509042239860-f550ce710b93",
        "1501339847302-ac426a4a7cbb", "1442512595331-e89e73853f31",
        "1447991627872-2e80832aa393", "1498804103079-a6351b050096",
        "1514432324894-1f616095b717", "1517701604599-bb29b565090c",
    ],
    "restaurant|ресторан|еда|food|кухня|меню|пицц|бургер|суши": [
        "1414235077428-338989a2e8c0", "1517248135467-4c7edcad34c4",
        "1504674900247-0877df9cc836", "1559339352-11d035aa65de",
        "1565299624946-ad2870638e93", "1540189549336-e6e99c3679fe",
        "1476224203421-9ac39bcb3327", "1482049016gy-130c6b8e0f61",
        "1567620905732-2d1ec7ab7445", "1493770348580-1315afe7bd30",
    ],
    "tech|стартап|AI|технолог|IT|софт|приложен|SaaS|программ": [
        "1518770660439-4636190af475", "1504384308090-c894fdcc538d",
        "1550751827-4bd374c3f58b", "1535378917042-10a22c95931a",
        "1485827404703-89b55fcc595e", "1526374965328-7f61d4dc18c5",
        "1555949963-ff9fe0c870eb", "1519389950473-47ba0277781c",
    ],
    "photo|фото|портфолио|камера|сним": [
        "1452587925148-ce544e77e70d", "1493863641943-9b68992a8d07",
        "1516035069371-29a1b244cc32", "1554080353-321e452ccf19",
        "1502920917128-1aa500764cbd", "1542038784456-1ea8e935640e",
        "1500051638674-ff996a0ec29e", "1471127432458-65207be4a7f3",
    ],
    "fitness|спорт|зал|тренировк|здоров|йога": [
        "1534438327276-14e5300c3a48", "1571019613454-1cb2f99b2d8b",
        "1549060279-7e168fcee0c2", "1517836357463-d25dfeac3438",
        "1574680096145-d05b474e2155", "1518611099724-8aa87e68705e",
        "1571019614242-c5c5dee9f50b", "1552674605-db585a72187c",
    ],
    "fashion|мод|одежд|стиль|бренд|коллекц": [
        "1558618666-fcd25c85f82e", "1445205170230-053b83016050",
        "1483985988355-763728e1935b", "1490481651871-ab68de25d43d",
        "1558171813-9c1e38a0b026", "1509631179647-0177331693ae",
        "1515886657613-9f3515b0c78f", "1496747611176-843222e1e57c",
    ],
    "travel|путешеств|тур|отдых|пляж|горы|отел": [
        "1488646953014-85cb44e25828", "1502602898657-3e91760cbb34",
        "1506905925346-21bda4d32df4", "1476514525535-07fb3b4ae5f1",
        "1469854523086-cc02fe5d8800", "1507525428034-b723cf961d3f",
        "1530789253388-582c481c54b0", "1472396961693-142e6e269027",
    ],
    "music|музык|звук|концерт|трек|альбом": [
        "1511379938547-c1f69419868d", "1514320291840-2e0a9bf2a9ae",
        "1493225457124-a3eb161ffa5f", "1470225620780-dba8ba36b745",
        "1507838153414-b4b713384a76", "1511671782779-c97d3d27a1d4",
        "1459749411175-04bf5292ceea", "1505236858219-8359eb29e329",
    ],
    "real.estate|недвижим|квартир|дом|интерьер|ремонт": [
        "1502672260266-1c1ef2d93688", "1560448204-e02f11c3d0e2",
        "1505691938895-1758d7feb511", "1560185893-a55cbc8c57e8",
        "1600596542815-ffad4c1539a9", "1600585154340-be6161a56a0c",
        "1560185007-c5ca9d2c014d", "1502005229762-cf1b2da7c5d6",
    ],
    "medical|медицин|здоров|клиник|врач|больниц": [
        "1576091160399-112ba8d25d1d", "1519494026892-80bbd2d6fd0d",
        "1538108149393-fbbd81895907", "1579684385127-1ef15d508118",
        "1559757175-5700dde6b740", "1631815588090-d4bfec5b6ccb",
        "1576091160550-2173dba999ef", "1505751172826-f5c3b6b4f094",
    ],
    "education|образован|школ|универ|курс|обучен": [
        "1503676260728-1c00da094a0b", "1523050854058-8df90110c9f1",
        "1522202176988-66273c2fd55f", "1427504494785-3a9ca7044f45",
        "1509062522246-3755977927d7", "1524178232363-1fb2b075b655",
        "1546410531-bb4caa6b4d30", "1580582932707-520aed937b7b",
    ],
    "default": [
        "1497366216548-37526070297c", "1497366811353-6870744d04b2",
        "1486406146926-c627a92ad1ab", "1497215728101-856f4ea42174",
        "1497366754037-f77203309bba", "1486325212027-8081e485255e",
        "1507003211169-0a1dd7228f2d", "1493514782019-c7b49e68400f",
    ],
}


def get_theme_images(prompt: str, count: int = 5) -> list[str]:
    """Get themed image URLs based on prompt keywords. Randomly selects from pool."""
    import random
    prompt_lower = prompt.lower()
    for pattern, photos in THEME_IMAGES.items():
        if re.search(pattern, prompt_lower):
            break
    else:
        photos = THEME_IMAGES["default"]

    selected = random.sample(photos, min(count, len(photos)))
    urls = []
    for i, photo_id in enumerate(selected):
        sizes = [(1200, 800), (800, 600), (600, 400), (800, 800), (1200, 600)]
        w, h = sizes[i % len(sizes)]
        urls.append(f"https://images.unsplash.com/photo-{photo_id}?w={w}&h={h}&fit=crop&q=80")
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

## Images
Use these EXACT URLs — use DIFFERENT images in DIFFERENT places (hero, gallery, cards):
{image_urls}

Don't repeat the same image twice. Wide (1200x800) for heroes, square for cards.

## Output
Return ONLY a complete, self-contained HTML file with inline CSS and JS.
Use Google Fonts. Include viewport meta. Make all images have alt attributes.
Make it stunning on mobile and desktop."""


def build_system_prompt(user_prompt: str) -> str:
    images = get_theme_images(user_prompt, 4)
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
    """Auto-fix common HTML issues."""
    # Add viewport if missing
    if 'viewport' not in html:
        html = html.replace(
            '<head>',
            '<head>\n<meta name="viewport" content="width=device-width, initial-scale=1.0">',
            1
        )
    # Add charset if missing
    if 'charset' not in html:
        html = html.replace('<head>', '<head>\n<meta charset="UTF-8">', 1)
    # Add alt to images without it
    html = re.sub(r'<img(?![^>]*alt=)([^>]*)>', r'<img\1 alt="Image">', html)
    return html


async def generate_design(user_prompt: str) -> str:
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    system_prompt = build_system_prompt(user_prompt)
    model = user_models.get(None, OPENROUTER_MODEL)  # Will be overridden per-user

    payload = {
        "model": model,
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
    """Create a ZIP with HTML, CSS, JS extracted."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{filename}/index.html", html)
    return buf.getvalue()


def check_rate_limit(user_id: int) -> bool:
    """Check if user is within daily rate limit."""
    global last_reset
    now = datetime.now()
    if (now - last_reset) > timedelta(days=1):
        user_daily_count.clear()
        last_reset = now
    return user_daily_count[user_id] < MAX_DESIGNS_PER_DAY


# === Keyboards ===

def get_style_keyboard(prompt: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌑 Минимализм", callback_data=f"gen:{prompt[:30]}:minimal dark"),
            InlineKeyboardButton(text="🌈 Яркий", callback_data=f"gen:{prompt[:30]}:vibrant colorful"),
        ],
        [
            InlineKeyboardButton(text="🏛 Премиум", callback_data=f"gen:{prompt[:30]}:luxury elegant"),
            InlineKeyboardButton(text="🌿 Органик", callback_data=f"gen:{prompt[:30]}:organic natural"),
        ],
        [
            InlineKeyboardButton(text="⚡ Ретро", callback_data=f"gen:{prompt[:30]}:retro 80s neon"),
            InlineKeyboardButton(text="🔥 Брутализм", callback_data=f"gen:{prompt[:30]}:brutalist bold"),
        ],
        [
            InlineKeyboardButton(text="✨ Без стиля", callback_data=f"gen:{prompt[:30]}:"),
        ]
    ])


def get_result_keyboard(prompt: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Ещё вариант", callback_data=f"retry:{prompt[:35]}"),
            InlineKeyboardButton(text="🎨 Стиль", callback_data=f"pickstyle:{prompt[:35]}"),
        ],
        [
            InlineKeyboardButton(text="📦 Скачать HTML", callback_data=f"download:{prompt[:35]}"),
        ]
    ])


def get_model_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅ ' if user_models.get(None) == m else ''}{name}",
                              callback_data=f"setmodel:{name}:{m}")]
        for name, m in AVAILABLE_MODELS.items()
    ])


# === Handlers ===
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🎨 <b>Design Bot v4</b>\n\n"
        "Опиши дизайн — получишь HTML + скриншот + ссылку.\n\n"
        "<b>Команды:</b>\n"
        "/styles — выбрать стиль перед генерацией\n"
        "/model — сменить AI-модель\n"
        "/history — последние дизайны\n"
        "/stats — статистика\n"
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
        "📦 — скачать HTML\n\n"
        f"Лимит: {MAX_DESIGNS_PER_DAY} дизайнов в день",
        parse_mode="HTML",
    )


@router.message(Command("styles"))
async def cmd_styles(message: Message):
    await message.answer(
        "Выбери стиль для следующего дизайна:\n\n"
        "Или просто напиши описание — выберешь стиль после.",
        reply_markup=get_style_keyboard("placeholder"),
    )


@router.message(Command("model"))
async def cmd_model(message: Message):
    current = user_models.get(message.from_user.id, OPENROUTER_MODEL)
    text = f"<b>Текущая модель:</b> <code>{current}</code>\n\nВыбери другую:"
    await message.answer(text, parse_mode="HTML", reply_markup=get_model_keyboard())


@router.message(Command("history"))
async def cmd_history(message: Message):
    history = user_history.get(message.from_user.id, [])
    if not history:
        await message.answer("История пуста. Сгенерируй первый дизайн!")
        return
    text = "<b>📋 Последние дизайны:</b>\n\n"
    for i, item in enumerate(reversed(history[-10:]), 1):
        t = item["time"].strftime("%H:%M")
        text += f"{i}. <i>{item['prompt'][:45]}</i>\n   🔗 <a href=\"{item['url']}\">{item['style'] if item.get('style') else 'default'}</a> • {t}\n\n"
    await message.answer(text, parse_mode="HTML")


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    uid = message.from_user.id
    total = len(user_history.get(uid, []))
    today = user_daily_count.get(uid, 0)
    model = user_models.get(uid, OPENROUTER_MODEL)
    text = (
        f"<b>📊 Статистика</b>\n\n"
        f"Всего дизайнов: <b>{total}</b>\n"
        f"Сегодня: <b>{today}/{MAX_DESIGNS_PER_DAY}</b>\n"
        f"Модель: <code>{model}</code>"
    )
    await message.answer(text, parse_mode="HTML")


# === Callbacks ===

@router.callback_query(F.data.startswith("setmodel:"))
async def cb_set_model(callback: CallbackQuery):
    parts = callback.data.split(":", 2)
    name, model = parts[1], parts[2]
    user_models[callback.from_user.id] = model
    await callback.answer(f"Модель: {name}")
    await callback.message.edit_text(f"✅ Модель изменена на <code>{model}</code>", parse_mode="HTML")


@router.callback_query(F.data.startswith("pickstyle:"))
async def cb_pick_style(callback: CallbackQuery):
    prompt = callback.data[10:]
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
    full_prompt = f"{prompt}\nStyle: {style}" if style else prompt
    await callback.answer("Генерирую...")
    await process_design(callback.message, callback.from_user.id, full_prompt, style=style)


@router.callback_query(F.data.startswith("retry:"))
async def cb_retry(callback: CallbackQuery):
    prompt = callback.data[6:]
    await callback.answer("Генерирую новый вариант...")
    await process_design(callback.message, callback.from_user.id, prompt)


@router.callback_query(F.data.startswith("download:"))
async def cb_download(callback: CallbackQuery):
    prompt = callback.data[9:]
    history = user_history.get(callback.from_user.id, [])
    # Find latest matching design
    for item in reversed(history):
        if prompt[:30] in item["prompt"]:
            zip_data = create_zip("", item["filename"])
            # Re-fetch HTML from GitHub
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
    await callback.answer("Дизайн не найден в истории")


# === Main handler ===

@router.message(F.text & ~F.text.startswith("/"))
async def handle_design_request(message: Message):
    await process_design(message, message.from_user.id, message.text.strip())


async def process_design(target_msg: Message, user_id: int, user_prompt: str, style: str = ""):
    if len(user_prompt) < 3:
        await target_msg.answer("Опиши подробнее, что за дизайн нужен 🤔")
        return

    if not check_rate_limit(user_id):
        await target_msg.answer(
            f"⚠️ Достигнут дневной лимит ({MAX_DESIGNS_PER_DAY} дизайнов).\n"
            "Попробуй завтра или используй /model для смены модели."
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
        keyboard = get_result_keyboard(user_prompt)
        remaining = MAX_DESIGNS_PER_DAY - user_daily_count[user_id]
        caption = (
            f"✅ <b>Готово!</b> ({elapsed:.0f}с)\n\n"
            f"🔗 <a href=\"{url}\">Открыть сайт</a>\n"
            f"🎨 Стиль: {style or 'auto'}\n"
            f"📊 Осталось сегодня: {remaining}"
        )

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
        await status_msg.edit_text(f"❌ Ошибка: {e}\n\nПопробуй ещё раз или /model для смены модели.")

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

    print("🤖 Design Bot v4 started!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
