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
            logger.info(f"🔑 Logging in to Terabox... (Attempt {attempt}/{max_retries})")
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-features=IsolateOrigins,site-per-process"
                    ]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768}
                )
                page = await context.new_page()

                await page.goto("https://www.terabox.com/login", wait_until="domcontentloaded")
                await asyncio.sleep(4)

                # Flexible selectors for email/username field
                await page.wait_for_selector(
                    'input[type="text"], input[name="userName"], input[placeholder*="email" i], input[placeholder*="手机" i]',
                    timeout=20000
                )
                await page.fill(
                    'input[type="text"], input[name="userName"], input[placeholder*="email" i]',
                    TERABOX_EMAIL
                )

                await asyncio.sleep(1.5)
                await page.fill('input[type="password"]', TERABOX_PASSWORD)

                await asyncio.sleep(1.5)
                await page.click(
                    'button[type="submit"], .login-btn, button:has-text("Log in"), button:has-text("登录"), button:has-text("Sign in")',
                    timeout=15000
                )

                # More reliable success detection
                await page.wait_for_url("**/main**", timeout=60000)
                await asyncio.sleep(5)

                cookies = await context.cookies()
                cookie_dict = {c["name"]: c["value"] for c in cookies}

                # Basic verification that we have useful cookies
                if len(cookie_dict) < 5:
                    raise Exception("Login succeeded but insufficient cookies received")

                with open(COOKIE_FILE, "w") as f:
                    json.dump(cookie_dict, f, indent=2)

                await browser.close()
                logger.info("✅ Terabox login successful.")
                return cookie_dict

        except Exception as e:
            logger.error(f"Login attempt {attempt} failed: {e}")
            if attempt == max_retries:
                raise Exception(f"Terabox login failed after {max_retries} attempts: {e}")
            await asyncio.sleep(8 * attempt)  # exponential backoff

async def get_cookies(force_refresh: bool = False) -> dict:
    if not force_refresh and os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load cookies file: {e}")
    return await login_and_get_cookies()
