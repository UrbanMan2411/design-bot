"""Telegram keyboard builders."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_style_keyboard(prompt: str) -> InlineKeyboardMarkup:
    """Style selection keyboard."""
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
    """Result action keyboard."""
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


def get_after_test_keyboard() -> InlineKeyboardMarkup:
    """Post-test action keyboard."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Ещё тест", callback_data="menu:tests")],
        [InlineKeyboardButton(text="💬 Обсудить результат", callback_data="menu:discuss")],
        [InlineKeyboardButton(text="🔙 В меню", callback_data="menu:main")],
    ])


STYLE_MAP = {
    "dark": "minimal dark elegant",
    "color": "vibrant colorful energetic",
    "luxury": "luxury premium elegant gold",
    "organic": "organic natural earthy warm",
    "retro": "retro 80s neon synthwave",
    "brutal": "brutalist bold raw industrial",
}


def map_style(short: str) -> str:
    """Map short style code to full description."""
    return STYLE_MAP.get(short, short)
