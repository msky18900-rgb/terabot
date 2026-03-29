import os
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH,
    TELEGRAM_PHONE, TELEGRAM_SESSION, BOT_USERNAME, DOWNLOAD_DIR
)

logger = logging.getLogger(__name__)

# Use StringSession so no file is needed on Railway
client = TelegramClient(
    StringSession(TELEGRAM_SESSION),
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH
)


async def generate_session():
    """Run this locally once to generate your session string."""
    await client.start(phone=TELEGRAM_PHONE)
    session_str = client.session.save()
    print("\n✅ Your session string (add to Railway env as TELEGRAM_SESSION):\n")
    print(session_str)
    await client.disconnect()


@client.on(events.NewMessage(incoming=True))
async def handle_incoming(event):
    """Forward any video sent to you → to your bot."""
    msg = event.message

    # Only process if it's a video
    if not msg.video and not (msg.document and msg.document.mime_type.startswith("video/")):
        return

    logger.info(f"Userbot detected video, forwarding to bot @{BOT_USERNAME}")
    try:
        await client.forward_messages(BOT_USERNAME, msg)
        logger.info("Forwarded to bot successfully.")
    except Exception as e:
        logger.error(f"Failed to forward: {e}")


async def start_userbot():
    await client.start(phone=TELEGRAM_PHONE)
    logger.info("Userbot started.")
    await client.run_until_disconnected()
