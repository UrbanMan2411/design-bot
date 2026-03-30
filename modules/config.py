"""Configuration module."""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/xiaomi/mimo-v2-pro")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "main")
PAGES_BASE_URL = f"https://{GITHUB_REPO.split('/')[0]}.github.io/{GITHUB_REPO.split('/')[1]}" if GITHUB_REPO else ""
MAX_DESIGNS_PER_DAY = int(os.getenv("MAX_DESIGNS_PER_DAY", "20"))
WATERMARK_TEXT = "Made with LandingAI"
WATERMARK_URL = "https://t.me/LandAIpagebot"

# Rate tiers
RATE_TIERS = {
    "free": {"daily_limit": 5, "watermark": True, "priority": False},
    "basic": {"daily_limit": 20, "watermark": True, "priority": False},
    "pro": {"daily_limit": 100, "watermark": False, "priority": True},
}

# User tiers (user_id -> tier)
user_tiers: dict[int, str] = {}  # Managed externally

# Languages
LANGUAGES = {
    "ru": {
        "start": "🎨 <b>Design Bot v6</b>\n\nОпиши дизайн — получишь HTML + скриншот + ссылку.\n\n<b>Команды:</b>\n/styles — выбрать стиль\n/history — последние дизайны\n/stats — статистика\n/referral — пригласить друга (+5 дизайнов)\n/gallery — галерея дизайнов\n/help — помощь",
        "help": "<b>Как пользоваться:</b>\n\n1️⃣ Напиши что за сайт нужен\n2️⃣ Выбери стиль (или пропусти)\n3️⃣ Получишь скриншот + ссылку\n\n🔄 Ещё — новый вариант\n🎨 Стиль — сменить стиль\n👍👎 — оценить дизайн\n📦 — скачать HTML\n\nЛимит: {limit} дизайнов в день",
        "generating": "⏳ Генерирую дизайн...",
        "ai_thinking": "🤖 AI создаёт дизайн...",
        "expanding": "🧠 Расширяю запрос...",
        "screenshot": "📸 Делаю превью...",
        "publishing": "📤 Публикую...",
        "ready": "✅ <b>Готово!</b> ({time}с)\n\n🔗 <a href=\"{url}\">Открыть сайт</a>\n🎨 {style} • 📊 {remaining} дизайнов сегодня",
        "error": "❌ Ошибка: {error}\n\nПопробуй ещё раз.",
        "rate_limit": "⚠️ Достигнут дневной лимит ({limit} дизайнов).\nПопробуй завтра или пригласи друга: /referral",
        "too_short": "Опиши подробнее, что за дизайн нужен 🤔",
        "busy": "⏳ Подожди, предыдущий дизайн ещё генерируется...",
        "lang_changed": "Язык изменён на русский 🇷🇺",
    },
    "en": {
        "start": "🎨 <b>Design Bot v6</b>\n\nDescribe a design — get HTML + screenshot + link.\n\n<b>Commands:</b>\n/styles — choose style\n/history — recent designs\n/stats — statistics\n/referral — invite a friend (+5 designs/day)\n/gallery — design gallery\n/help — help",
        "help": "<b>How to use:</b>\n\n1️⃣ Describe what website you need\n2️⃣ Choose a style (or skip)\n3️⃣ Get screenshot + link\n\n🔄 Another — new variant\n🎨 Style — change style\n👍👎 — rate design\n📦 — download HTML\n\nLimit: {limit} designs per day",
        "generating": "⏳ Generating design...",
        "ai_thinking": "🤖 AI is creating...",
        "expanding": "🧠 Expanding your request...",
        "screenshot": "📸 Taking preview...",
        "publishing": "📤 Publishing...",
        "ready": "✅ <b>Done!</b> ({time}s)\n\n🔗 <a href=\"{url}\">Open site</a>\n🎨 {style} • 📊 {remaining} designs today",
        "error": "❌ Error: {error}\n\nPlease try again.",
        "rate_limit": "⚠️ Daily limit reached ({limit} designs).\nTry tomorrow or invite a friend: /referral",
        "too_short": "Please describe what website you need 🤔",
        "busy": "⏳ Please wait, previous design is still generating...",
        "lang_changed": "Language changed to English 🇬🇧",
    },
}
