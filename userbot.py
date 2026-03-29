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

# Initialize Pyrogram Userbot (in-memory session for Railway)
client = Client(
    "terabot_userbot",
    api_id=TELEGRAM_API_ID,
    api_hash=TELEGRAM_API_HASH,
    session_string=TELEGRAM_SESSION,
    in_memory=True,
)

def is_allowed(msg: Message) -> bool:
    """Centralized permission check"""
    if not ALLOWED_USER_ID:
        return True  # Allow everyone if no restriction set

    user_id = msg.from_user.id if msg.from_user else None
    chat_id = msg.chat.id if msg.chat else None

    # Allow if message is from allowed user OR sent to saved messages (chat == user)
    return (user_id == ALLOWED_USER_ID) or (chat_id == ALLOWED_USER_ID)

async def send_status(chat_id: int, text: str) -> int:
    """Send status message using Bot API"""
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "Markdown"
                }
            )
            r.raise_for_status()
            return r.json()["result"]["message_id"]
    except Exception as e:
        logger.error(f"Failed to send status message: {e}")
        return 0

async def edit_status(chat_id: int, message_id: int, text: str):
    """Edit status message using Bot API"""
    if not message_id:
        return
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
        logger.warning(f"Failed to edit status message: {e}")


@client.on_message(filters.video | filters.document)
async def handle_incoming(app: Client, msg: Message):
    if not is_allowed(msg):
        return

    # Determine if it's a video
    is_video = bool(msg.video) or (
        msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/")
    )
    if not is_video:
        return

    # Get filename and size
    if msg.video:
        filename = f"{msg.id}.mp4"
        size_bytes = msg.video.file_size or 0
    else:
        filename = msg.document.file_name or f"{msg.id}.mp4"
        size_bytes = msg.document.file_size or 0

    # Ensure filename has extension
    if "." not in filename:
        filename += ".mp4"

    # Sanitize filename
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ").strip()
    if not safe_filename:
        safe_filename = f"video_{msg.id}.mp4"

    size_mb = round(size_bytes / (1024 * 1024), 1)

    # Local save path
    local_path = os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4()}_{safe_filename}")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    chat_id = ALLOWED_USER_ID  # All status messages go to the allowed user

    # Initial status
    msg_id = await send_status(
        chat_id,
        f"📥 *Received Video*\n"
        f"`{filename}` ({size_mb} MB)\n"
        f"⏳ Starting download..."
    )

    if not msg_id:
        logger.error("Failed to send initial status message")
        return

    try:
        last_dl_pct = [-1]

        def download_progress(current: int, total: int):
            if total == 0:
                return
            pct = int((current / total) * 100)
            if pct != last_dl_pct[0] and pct % 10 == 0:
                last_dl_pct[0] = pct
                mb_done = round(current / (1024 * 1024), 1)
                mb_total = round(total / (1024 * 1024), 1)
                asyncio.create_task(
                    edit_status(
                        chat_id, msg_id,
                        f"📥 *Downloading...*\n"
                        f"`{filename}`\n"
                        f"{pct}% — {mb_done}/{mb_total} MB"
                    )
                )

        logger.info(f"⬇️ Starting download: {filename} ({size_mb} MB)")

        # Download from Telegram
        downloaded_path = await asyncio.wait_for(
            app.download_media(
                msg,
                file_name=local_path,
                progress=download_progress
            ),
            timeout=7200  # 2 hours max download time
        )

        if not downloaded_path or not os.path.exists(downloaded_path):
            await edit_status(chat_id, msg_id, f"❌ Download failed — file not found for `{filename}`")
            return

        local_path = downloaded_path  # Update path in case Pyrogram changed it
        logger.info(f"✅ Downloaded successfully: {local_path}")

        # Update status before queuing
        await edit_status(
            chat_id, msg_id,
            f"✅ *Download Complete*\n"
            f"`{filename}` ({size_mb} MB)\n"
            f"📦 Adding to Terabox upload queue..."
        )

        # Upload progress callback
        last_up_pct = [-1]

        async def on_upload_progress(pct: int, chunk: int, total_chunks: int):
            if pct != last_up_pct[0] and pct % 10 == 0:
                last_up_pct[0] = pct
                await edit_status(
                    chat_id, msg_id,
                    f"⬆️ *Uploading to Terabox*\n"
                    f"`{filename}`\n"
                    f"Progress: {pct}% ({chunk}/{total_chunks} chunks)"
                )

        # Create dummy message object for queue compatibility
        class SimpleStatusMsg:
            async def edit_text(self, text: str, parse_mode=None):
                await edit_status(chat_id, msg_id, text)

        # Create upload job
        job = UploadJob(
            job_id=str(uuid.uuid4()),
            filename=filename,
            size_mb=size_mb,
            local_path=local_path,
            status_msg=SimpleStatusMsg(),
            on_progress=on_upload_progress,
        )

        await upload_queue.add_job(job)

    except asyncio.TimeoutError:
        logger.error(f"Download timeout for {filename}")
        await edit_status(chat_id, msg_id, f"❌ Download timed out for `{filename}`")
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error processing {filename}: {e}", exc_info=True)
        await edit_status(
            chat_id, msg_id,
            f"❌ *Error Processing File*\n"
            f"`{filename}`\n"
            f"Error: `{str(e)[:300]}`"
        )
        if os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


# Optional: Add a simple health command for userbot (useful for debugging)
@client.on_message(filters.command("ping") & filters.private)
async def ping_handler(app: Client, msg: Message):
    if not is_allowed(msg):
        return
    await msg.reply_text("✅ Userbot is alive and running!")
