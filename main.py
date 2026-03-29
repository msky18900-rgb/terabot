import asyncio
import logging
from bot import get_bot_app, tele_client
from userbot import start_userbot, client as userbot_client
from config import TELEGRAM_PHONE

logging.basicConfig(level=logging.INFO)


async def run_all():
    # Start Telethon download client (used inside bot.py)
    await tele_client.start(phone=TELEGRAM_PHONE)

    # Start the userbot
    await userbot_client.start(phone=TELEGRAM_PHONE)

    # Start the bot (non-blocking)
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

    # Run userbot forever
    await userbot_client.run_until_disconnected()

    # Cleanup
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
