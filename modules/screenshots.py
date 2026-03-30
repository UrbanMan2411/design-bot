"""Screenshot capture module."""
import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)


async def take_screenshots(html: str, filename: str) -> tuple[str | None, str | None]:
    """Render HTML and take optimized desktop + mobile screenshots."""
    desktop_path, mobile_path = None, None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()

            # Desktop — visible area
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.set_content(html, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1000)
            desktop_path = f"/tmp/{filename}-desktop.jpg"
            await page.screenshot(path=desktop_path, type="jpeg", quality=85)
            await page.close()

            # Mobile — visible area
            page = await browser.new_page(viewport={"width": 390, "height": 844})
            await page.set_content(html, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1000)
            mobile_path = f"/tmp/{filename}-mobile.jpg"
            await page.screenshot(path=mobile_path, type="jpeg", quality=85)
            await page.close()

            await browser.close()
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")

    return desktop_path, mobile_path


async def screenshot_url(url: str, filename: str) -> str | None:
    """Take screenshot of a URL."""
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(viewport={"width": 1280, "height": 720})
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(1000)
            path = f"/tmp/{filename}.jpg"
            await page.screenshot(path=path, type="jpeg", quality=85)
            await browser.close()
            return path
    except Exception as e:
        logger.error(f"URL screenshot failed: {e}")
        return None
