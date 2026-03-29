import asyncio
import logging
from bot import get_bot_app, tele_client
from userbot import client as userbot_client
from queue_manager import upload_queue
from config import TELEGRAM_PHONE

logging.basicConfig(level=logging.INFO)


async def run_all():
    # Start upload queue processor
    upload_queue.start()

    # Start Telethon downloader client
    await tele_client.start(phone=TELEGRAM_PHONE)

    # Start userbot (forwards videos to bot)
    await userbot_client.start(phone=TELEGRAM_PHONE)

    # Start bot
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

    logging.info("All services running.")

    # Keep running
    await userbot_client.run_until_disconnected()

    # Graceful shutdown
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
