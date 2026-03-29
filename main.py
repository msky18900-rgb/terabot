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


async def run_all():
    await clear_old_sessions()
    await asyncio.sleep(2)

    upload_queue.start()

    # Start Pyrogram userbot
    await userbot_client.start()
    me = await userbot_client.get_me()
    logger.info(f"Userbot logged in as: {me.first_name} (@{me.username})")

    # Start bot
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)

    logger.info("All services running.")

    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(run_all())
