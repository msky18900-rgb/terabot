import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TERABOX_EMAIL = os.getenv("TERABOX_EMAIL")
TERABOX_PASSWORD = os.getenv("TERABOX_PASSWORD")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/tmp/terabox_downloads")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "")

TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")
TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
