import json
import os
import asyncio
import logging
from playwright.async_api import async_playwright
from config import TERABOX_EMAIL, TERABOX_PASSWORD

logger = logging.getLogger(__name__)
COOKIE_FILE = "/tmp/terabox_cookies.json"

async def login_and_get_cookies(max_retries: int = 3) -> dict:
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Logging in to Terabox... (Attempt {attempt}/{max_retries})")
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()

                await page.goto("https://www.terabox.com/login", wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # More flexible and robust selectors
                await page.wait_for_selector('input[type="text"], input[name="userName"], input[placeholder*="email" i]', timeout=15000)
                await page.fill('input[type="text"], input[name="userName"], input[placeholder*="email" i]', TERABOX_EMAIL)

                await asyncio.sleep(1)
                await page.fill('input[type="password"]', TERABOX_PASSWORD)

                await asyncio.sleep(1)
                await page.click('button[type="submit"], .login-btn, button:has-text("Log in"), button:has-text("登录")', timeout=10000)

                # Wait for successful login (more reliable than URL pattern)
                await page.wait_for_url("**/main**", timeout=45000)
                await asyncio.sleep(4)

                # Verify we are actually logged in
                cookies = await context.cookies()
                cookie_dict = {c["name"]: c["value"] for c in cookies}

                if not any(k in cookie_dict for k in ["BDUSS", "STOKEN"]):  # Common Terabox cookies
                    raise Exception("Login successful but required cookies missing")

                with open(COOKIE_FILE, "w") as f:
                    json.dump(cookie_dict, f, indent=2)

                await browser.close()
                logger.info("✅ Terabox login successful.")
                return cookie_dict

        except Exception as e:
            logger.error(f"Login attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(5 * attempt)  # backoff

    raise Exception("All login attempts failed")

async def get_cookies(force_refresh: bool = False) -> dict:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return await login_and_get_cookies()
