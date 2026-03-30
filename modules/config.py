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
