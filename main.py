import asyncio
import logging
import httpx
from bot import get_bot_app
from userbot import client as userbot_client
from queue_manager import upload_queue
from config import BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def clear_old_webhook():
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            await http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook",
                json={"drop_pending_updates": True}
            )
        logger.info("✅ Cleared old webhook and pending updates.")
    except Exception as e:
        logger.warning(f"Failed to clear webhook: {e}")

async def start_userbot_with_retry(max_retries=5):
    """Start Pyrogram userbot with reconnection logic"""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Starting userbot... (Attempt {attempt}/{max_retries})")
            await userbot_client.start()
            me = await userbot_client.get_me()
            logger.info(f"✅ Userbot logged in as: {me.first_name} (@{me.username})")
            return True
        except Exception as e:
            logger.error(f"Userbot start failed attempt {attempt}: {e}")
            if attempt == max_retries:
                raise
            await asyncio.sleep(5 * attempt)  # backoff

async def run_all():
    await clear_old_webhook()
    await asyncio.sleep(2)

    # Start queue processor
    upload_queue.start()
    logger.info("✅ Upload queue started.")

    # Start userbot with retry
    await start_userbot_with_retry()

    # Start the main Telegram bot (python-telegram-bot)
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    
    # Use updater polling without blocking issues
    updater = bot_app.updater
    await updater.start_polling(drop_pending_updates=True)
    
    logger.info("🚀 All services running successfully!")

    # Keep the program alive
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        logger.info("Shutting down...")

if __name__ == "__main__":
    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Critical error: {e}", exc_info=True)
