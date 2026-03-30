"""Vercel deployment module."""
import logging
import aiohttp
from modules.config import OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

VERCEL_API = "https://api.vercel.com"


async def deploy_to_vercel(html: str, project_name: str, vercel_token: str) -> str | None:
    """Deploy HTML to Vercel. Returns deployment URL."""
    try:
        headers = {
            "Authorization": f"Bearer {vercel_token}",
            "Content-Type": "application/json",
        }

        # Create deployment
        payload = {
            "name": project_name,
            "files": [
                {
                    "file": "index.html",
                    "data": html,
                }
            ],
            "projectSettings": {
                "framework": None,
            },
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{VERCEL_API}/v13/deployments",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    url = data.get("url", "")
                    return f"https://{url}" if url else None
                else:
                    error = await resp.text()
                    logger.error(f"Vercel deploy failed: {resp.status} - {error}")
                    return None

    except Exception as e:
        logger.error(f"Vercel deploy error: {e}")
        return None
