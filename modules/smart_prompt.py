"""Smart prompt expansion module."""
import asyncio
import json
import logging

import aiohttp
from modules.config import OPENROUTER_BASE_URL, OPENROUTER_MODEL

logger = logging.getLogger(__name__)

EXPAND_PROMPT = """You are a UX copywriter. A user gave a brief description of a website they want. 
Expand it into a detailed design brief.

User input: "{user_input}"

Return a JSON object with these fields:
- title: business/site name (invent if not given)
- description: 2-3 sentence site purpose
- target_audience: who is this for
- sections: list of 4-6 sections the site should have (e.g. "hero with CTA", "features grid", "testimonials")
- color_mood: suggested color mood (e.g. "warm earthy tones", "dark with neon accents")
- style: design style (e.g. "modern minimalist", "luxury editorial")
- cta: main call-to-action text

Return ONLY valid JSON, no markdown."""


async def expand_prompt(user_input: str) -> dict:
    """Expand a brief input into a detailed design brief."""
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "user", "content": EXPAND_PROMPT.format(user_input=user_input)},
        ],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                content = content.strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                return json.loads(content)
    except Exception as e:
        logger.warning(f"Prompt expansion failed: {e}")
        return {}


def format_expanded_prompt(original: str, expanded: dict) -> str:
    """Format expanded brief into a detailed prompt for the AI."""
    if not expanded:
        return original

    sections = expanded.get("sections", [])
    sections_str = "\n".join(f"- {s}" for s in sections) if sections else ""

    return f"""Create a landing page for: {expanded.get('title', 'Business')}

Purpose: {expanded.get('description', original)}
Target audience: {expanded.get('target_audience', 'General')}
Style: {expanded.get('style', 'Modern')}
Color mood: {expanded.get('color_mood', 'Professional')}
CTA button: {expanded.get('cta', 'Get Started')}

Sections to include:
{sections_str}
- Footer with contact info

Make it visually stunning and responsive."""


async def fetch_website_content(url: str) -> dict:
    """Fetch and parse website content for context."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return {}
                html = await resp.text()

        # Extract key info
        import re
        title = ""
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.I | re.S)
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()

        meta_desc = ""
        desc_match = re.search(r'<meta[^>]*name=["\']description["\'][^>]*content=["\'](.*?)["\']', html, re.I)
        if desc_match:
            meta_desc = desc_match.group(1)

        h1s = [re.sub(r'<[^>]+>', '', h).strip()[:100]
               for h in re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.I | re.S)[:3]]

        return {
            "title": title,
            "description": meta_desc,
            "headings": h1s,
        }
    except Exception as e:
        logger.warning(f"Website fetch failed: {e}")
        return {}
