import os
import uuid
import logging
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from queue_manager import upload_queue, UploadJob
from config import (
    TELEGRAM_API_ID, TELEGRAM_API_HASH,
    TELEGRAM_SESSION, DOWNLOAD_DIR, ALLOWED_USER_ID,
    BOT_TOKEN
)
import httpx

logger = logging.getLogger(__name__)

client = Client(
    "userbot",
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    session_string=TELEGRAM_SESSION,
    in_memory=True,         # no session file needed on Railway
)


async def send_status(chat_id: int, text: str) -> int:
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        )
        return r.json()["result"]["message_id"]


async def edit_status(chat_id: int, message_id: int, text: str):
    try:
        async with httpx.AsyncClient(timeout=30) as http:
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


@client.on_message(filters.video | filters.document)
async def handle_incoming(app: Client, msg: Message):
    # Only allowed user
    if ALLOWED_USER_ID and msg.from_user and msg.from_user.id != ALLOWED_USER_ID:
        return
    # Also allow saved messages (user forwards to themselves)
    if msg.chat.id != ALLOWED_USER_ID and msg.from_user and msg.from_user.id != ALLOWED_USER_ID:
        return

    # Check mime type
    is_video = False
    if msg.video:
        is_video = True
    elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/"):
        is_video = True

    if not is_video:
        return

    # Get filename
    if msg.video:
        filename = f"{msg.id}.mp4"
        size_bytes = msg.video.file_size or 0
    else:
        filename = msg.document.file_name or f"{msg.id}.mp4"
        size_bytes = msg.document.file_size or 0

    if "." not in filename:
        filename += ".mp4"

    safe_filename = "".join(
        c for c in filename if c.isalnum() or c in "._- "
    ).strip()

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

        def dl_progress(received, total):
            pct = int((received / total) * 100) if total else 0
            if pct != last_pct[0] and pct % 10 == 0:
                last_pct[0] = pct
                mb_done  = round(received / 1024 / 1024, 1)
                mb_total = round(total / 1024 / 1024, 1)
                asyncio.create_task(edit_status(
                    chat_id, msg_id,
                    f"📥 Downloading `{filename}`\n"
                    f"{pct}% — {mb_done}/{mb_total} MB"
                ))

        logger.info(f"Starting download: {filename}")

        downloaded_path = await asyncio.wait_for(
            app.download_media(msg, file_name=local_path, progress=dl_progress),
            timeout=7200
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
