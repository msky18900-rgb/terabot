import asyncio
import logging
from bot import get_bot_app, tele_client
from userbot import client as userbot_client
from queue_manager import upload_queue
from config import TELEGRAM_PHONE, BOT_TOKEN
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def clear_old_sessions():
    """Force delete any existing webhook and clear update queue."""
    async with httpx.AsyncClient() as client:
        # Delete webhook
        await client.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            json={"drop_pending_updates": True}
        )
        logger.info("Cleared old webhook and pending updates.")


async def run_all():
    # Clear any duplicate sessions first
    await clear_old_sessions()
    await asyncio.sleep(2)  # Give Telegram time to clear

    # Start upload queue processor
    upload_queue.start()

    # Start Telethon downloader client
    await tele_client.start(phone=TELEGRAM_PHONE)

    # Start userbot
    await userbot_client.start(phone=TELEGRAM_PHONE)

    # Start bot
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    logger.info("All services running.")

    # Keep running
    await userbot_client.run_until_disconnected()

    # Graceful shutdown
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
