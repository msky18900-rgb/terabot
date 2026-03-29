import asyncio
import logging
import httpx
from bot import get_bot_app
from userbot import client as userbot_client
from queue_manager import upload_queue
from config import BOT_TOKEN

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def clear_old_sessions():
    async with httpx.AsyncClient() as http:
        await http.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
            json={"drop_pending_updates": True}
        )
    logger.info("Cleared old webhook and pending updates.")


async def keepalive_userbot():
    """Reconnect userbot if it drops."""
    while True:
        try:
            if not userbot_client.is_connected():
                logger.warning("Userbot disconnected — reconnecting...")
                await userbot_client.connect()
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Keepalive error: {e}")
            await asyncio.sleep(10)


async def run_all():
    await clear_old_sessions()
    await asyncio.sleep(2)

    upload_queue.start()

    # Connect userbot
    await userbot_client.connect()
    if not await userbot_client.is_user_authorized():
        logger.error("Userbot session expired! Re-generate TELEGRAM_SESSION on Colab.")
        return

    logger.info("Userbot connected and authorized.")

    # Start bot
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    logger.info("All services running.")

    # Run both keepalive and userbot together
    await asyncio.gather(
        userbot_client.run_until_disconnected(),
        keepalive_userbot(),
    )

    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
