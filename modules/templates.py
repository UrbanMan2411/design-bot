"""Pre-built templates for quick generation."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TEMPLATES = {
    "landing": {
        "name": "🚀 Лендинг",
        "prompt": "Professional landing page with hero section, features, testimonials, pricing, and CTA. Modern, clean design.",
    },
    "portfolio": {
        "name": "💼 Портфолио",
        "prompt": "Personal portfolio website with hero, about me, project gallery with hover effects, skills section, and contact form. Creative, editorial style.",
    },
    "restaurant": {
        "name": "🍕 Ресторан",
        "prompt": "Restaurant website with hero image, menu section with categories, photo gallery, reservation form, location map, and reviews. Warm, appetizing colors.",
    },
    "agency": {
        "name": "🏢 Агентство",
        "prompt": "Digital agency website with hero, services overview, team section, case studies/portfolio, client logos, and contact form. Professional, trustworthy.",
    },
    "saas": {
        "name": "💻 SaaS",
        "prompt": "SaaS product landing page with hero with CTA, feature comparison, pricing table, FAQ, testimonials, and integration logos. Modern tech aesthetic.",
    },
    "ecommerce": {
        "name": "🛒 Магазин",
        "prompt": "E-commerce landing page with featured products, categories, special offers, customer reviews, newsletter signup. Clean, conversion-focused.",
    },
    "blog": {
        "name": "📝 Блог",
        "prompt": "Personal blog with featured post hero, article grid, sidebar with categories and tags, newsletter signup. Editorial, readable typography.",
    },
    "fitness": {
        "name": "💪 Фитнес",
        "prompt": "Fitness/gym website with hero, class schedule, trainer profiles, membership pricing, testimonials, and signup form. Energetic, bold design.",
    },
}


def get_templates_keyboard() -> InlineKeyboardMarkup:
    """Get template selection keyboard."""
    buttons = []
    row = []
    for tid, tmpl in TEMPLATES.items():
        row.append(InlineKeyboardButton(text=tmpl["name"], callback_data=f"tmpl:{tid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🔙 Отмена", callback_data="tmpl:cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_template_prompt(template_id: str) -> str:
    """Get prompt for template."""
    return TEMPLATES.get(template_id, {}).get("prompt", "")
