"""Image keyword extraction and URL generation."""
import random
import re

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
    "medical|медицин|здоров|клиник|врач|больниц": ["medical", "hospital", "doctor", "health", "laboratory"],
    "education|образован|школ|универ|курс|обучен": ["education", "school", "students", "library", "classroom"],
    "default": ["business", "office", "team", "modern", "architecture"],
}

IMAGE_SIZES = [(1200, 800), (800, 600), (600, 400), (800, 800), (1200, 600)]


def get_theme_keywords(prompt: str) -> list[str]:
    """Extract keywords from prompt for image search."""
    prompt_lower = prompt.lower()
    for pattern, keywords in THEME_KEYWORDS.items():
        if re.search(pattern, prompt_lower):
            return keywords
    return THEME_KEYWORDS["default"]


def get_image_urls(prompt: str, count: int = 5) -> list[str]:
    """Generate image URLs based on prompt keywords."""
    keywords = get_theme_keywords(prompt)
    selected = random.sample(keywords, min(count, len(keywords)))
    urls = []
    for i, keyword in enumerate(selected):
        w, h = IMAGE_SIZES[i % len(IMAGE_SIZES)]
        lock = random.randint(1, 99999)
        urls.append(f"https://loremflickr.com/{w}/{h}/{keyword}?lock={lock}")
    return urls


def build_images_prompt_section(prompt: str) -> str:
    """Build image URLs section for system prompt."""
    urls = get_image_urls(prompt, 5)
    return "\n".join(f"- {url}" for url in urls)
