import json
import os
import asyncio
import logging
from playwright.async_api import async_playwright
from config import TERABOX_EMAIL, TERABOX_PASSWORD

logger = logging.getLogger(__name__)
COOKIE_FILE = "/tmp/terabox_cookies.json"


async def login_and_get_cookies() -> dict:
    logger.info("Logging in to Terabox...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        await page.goto("https://www.terabox.com/login", wait_until="networkidle")
        await asyncio.sleep(2)

        await page.fill('input[type="text"], input[name="userName"]', TERABOX_EMAIL)
        await asyncio.sleep(0.5)
        await page.fill('input[type="password"]', TERABOX_PASSWORD)
        await asyncio.sleep(0.5)
        await page.click('button[type="submit"], .login-btn, #submitBtn')

        await page.wait_for_url("**/main**", timeout=30000)
        await asyncio.sleep(3)

        cookies = await context.cookies()
        cookie_dict = {c["name"]: c["value"] for c in cookies}

        with open(COOKIE_FILE, "w") as f:
            json.dump(cookie_dict, f)

        await browser.close()
        logger.info("Terabox login successful.")
        return cookie_dict


async def get_cookies(force_refresh=False) -> dict:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE) as f:
            return json.load(f)
    return await login_and_get_cookies()
