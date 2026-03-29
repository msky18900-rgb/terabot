import os
import uuid
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
from queue_manager import upload_queue, UploadJob
from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH,
    TELEGRAM_SESSION, DOWNLOAD_DIR, ALLOWED_USER_ID,
    BOT_TOKEN
)
import httpx

logger = logging.getLogger(__name__)

client = TelegramClient(
    StringSession(TELEGRAM_SESSION),
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH,
    connection_retries=15,
    retry_delay=5,
    auto_reconnect=True,
)


async def send_status(chat_id: int, text: str) -> int:
    async with httpx.AsyncClient() as http:
        r = await http.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )
        return r.json()["result"]["message_id"]


async def edit_status(chat_id: int, message_id: int, text: str):
    try:
        async with httpx.AsyncClient() as http:
            await http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                json={
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": text,
                    "parse_mode": "Markdown"
                }
            )
    except Exception as e:
        logger.warning(f"edit_status failed: {e}")


@client.on(events.NewMessage(incoming=True))
async def handle_incoming(event):
    msg = event.message

    # Use sender_id directly — no network call needed
    sender_id = event.sender_id
    if ALLOWED_USER_ID and sender_id != ALLOWED_USER_ID:
        return

    # Check if video
    is_video = False
    if msg.video:
        is_video = True
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/"):
        is_video = True

    if not is_video:
        return

    # Get filename from attributes
    filename = None
    if msg.document:
        for attr in msg.document.attributes:
            if isinstance(attr, DocumentAttributeFilename):
                filename = attr.file_name
                break

    if not filename:
        filename = f"{msg.id}.mp4"
    if "." not in filename:
        filename += ".mp4"

    # Sanitize filename
    safe_filename = "".join(
        c for c in filename if c.isalnum() or c in "._- "
    ).strip()

    size_bytes = msg.document.size if msg.document else 0
    size_mb = round(size_bytes / 1024 / 1024, 1)
    local_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4()}_{safe_filename}")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    chat_id = ALLOWED_USER_ID
    queue_pos = upload_queue.queue_size() + (1 if upload_queue.current_job() else 0)

    msg_id = await send_status(
        chat_id,
        f"📥 *Received:* `{filename}` ({size_mb} MB)\n⏳ Downloading..."
    )

    try:
        last_pct = [-1]

        async def dl_progress(received, total):
            pct = int((received / total) * 100) if total else 0
            if pct != last_pct[0] and pct % 10 == 0:
                last_pct[0] = pct
                mb_done  = round(received / 1024 / 1024, 1)
                mb_total = round(total / 1024 / 1024, 1)
                await edit_status(
                    chat_id, msg_id,
                    f"📥 Downloading `{filename}`\n"
                    f"{pct}% — {mb_done}/{mb_total} MB"
                )

        logger.info(f"Downloading: {filename} -> {local_path}")

        downloaded_path = await asyncio.wait_for(
            client.download_media(
                msg,
                file=local_path,
                progress_callback=dl_progress
            ),
            timeout=7200  # 2 hours for 2GB files
        )

        logger.info(f"Downloaded to: {downloaded_path}")

        if not downloaded_path or not os.path.exists(downloaded_path):
            await edit_status(chat_id, msg_id, "❌ Download failed — file missing.")
            return

        local_path = downloaded_path

        await edit_status(
            chat_id, msg_id,
            f"✅ Downloaded `{filename}`\n"
            f"📦 Added to upload queue (position {queue_pos + 1})"
        )

        last_up_pct = [-1]

        async def on_upload_progress(pct, chunk, total):
            if pct != last_up_pct[0] and pct % 10 == 0:
                last_up_pct[0] = pct
                await edit_status(
                    chat_id, msg_id,
                    f"⬆️ Uploading to Terabox\n"
                    f"`{filename}`\n"
                    f"Progress: {pct}% ({chunk}/{total} chunks)"
                )

        class SimpleMsg:
            async def edit_text(self, text, parse_mode=None):
                await edit_status(chat_id, msg_id, text)

        job = UploadJob(
            job_id=str(uuid.uuid4()),
            filename=filename,
            size_mb=size_mb,
            local_path=local_path,
            status_msg=SimpleMsg(),
            on_progress=on_upload_progress,
        )
        await upload_queue.add_job(job)

    except asyncio.TimeoutError:
        logger.error(f"Timeout: {filename}")
        await edit_status(chat_id, msg_id, f"❌ Download timed out for `{filename}`")
        if os.path.exists(local_path):
            os.remove(local_path)

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await edit_status(chat_id, msg_id, f"❌ Error: `{e}`")
        if os.path.exists(local_path):
            os.remove(local_path)
