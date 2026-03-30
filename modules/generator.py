"""AI generation module."""
import asyncio
import json
import logging

import aiohttp

from modules.config import OPENROUTER_BASE_URL, OPENROUTER_MODEL
from modules.images import build_images_prompt_section

logger = logging.getLogger(__name__)

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
- Images: max-width: 100%, height: auto, object-fit: cover
- Touch-friendly: buttons min 44px, links spaced apart
- CRITICAL: Add `overflow-x: hidden` to html and body
- CRITICAL: All elements must have `max-width: 100%` or `box-sizing: border-box`
- CRITICAL: No horizontal scroll — content must fit viewport width

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
CRITICAL: Write ALL text content in the SAME LANGUAGE as the user's request. If user writes in Russian, ALL text must be in Russian. If in English — in English. Match the user's language exactly.
Make it stunning on mobile and desktop."""


def build_system_prompt(user_prompt: str) -> str:
    """Build system prompt with themed images."""
    images_section = build_images_prompt_section(user_prompt)
    return SYSTEM_PROMPT_TEMPLATE.format(image_urls=images_section)


async def generate_design(user_prompt: str, model: str = None) -> str:
    """Call AI API to generate HTML design. Retries up to 3 times."""
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    system_prompt = build_system_prompt(user_prompt)
    use_model = model or OPENROUTER_MODEL

    payload = {
        "model": use_model,
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
