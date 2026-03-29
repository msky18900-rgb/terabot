import asyncio
import logging
import httpx
from bot import get_bot_app
from userbot import client as userbot_client, ensure_connected
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


async def keepalive():
    """Ping Telegram every 60s to keep MTProto connection alive on Railway."""
    while True:
        try:
            await asyncio.sleep(60)
            await ensure_connected()
            logger.debug("Keepalive ping OK.")
        except Exception as e:
            logger.warning(f"Keepalive error: {e}")


async def run_all():
    await clear_old_sessions()
    await asyncio.sleep(2)

    upload_queue.start()

    await userbot_client.start()

    if not await userbot_client.is_user_authorized():
        logger.error("Session expired! Re-generate TELEGRAM_SESSION on Google Colab.")
        return

    me = await userbot_client.get_me()
    logger.info(f"Userbot logged in as: {me.first_name} (@{me.username})")

    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    logger.info("All services running.")

    # Run userbot + keepalive together
    await asyncio.gather(
        userbot_client.run_until_disconnected(),
        keepalive(),
    )

    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
