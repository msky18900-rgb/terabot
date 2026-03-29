import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telethon import TelegramClient
from telethon.sessions import StringSession
from terabox import upload_to_terabox
from config import (
    BOT_TOKEN, DOWNLOAD_DIR, ALLOWED_USER_ID,
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Telethon client for downloading large files (bypasses 20MB bot API limit)
tele_client = TelegramClient(
    StringSession(TELEGRAM_SESSION),
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH
)


async def download_with_telethon(message_id: int, chat_id: int, dest: str, status_msg, filename: str):
    """Use Telethon MTProto to download up to 2GB without limits."""
    last_pct = [-1]

    async def progress(received, total):
        pct = int((received / total) * 100) if total else 0
        if pct != last_pct[0] and pct % 10 == 0:
            last_pct[0] = pct
            mb_done = round(received / 1024 / 1024, 1)
            mb_total = round(total / 1024 / 1024, 1)
            try:
                await status_msg.edit_text(
                    f"📥 Downloading via MTProto\n`{filename}`\n{pct}% ({mb_done}/{mb_total} MB)",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    msg = await tele_client.get_messages(chat_id, ids=message_id)
    await tele_client.download_media(msg, file=dest, progress_callback=progress)


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user_id = update.effective_user.id

    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        await message.reply_text("⛔ Unauthorized.")
        return

    video = message.video or message.document
    if not video:
        await message.reply_text("❌ Send or forward a video.")
        return

    mime = getattr(video, "mime_type", "") or ""
    if not mime.startswith("video/"):
        await message.reply_text("❌ Only video files accepted.")
        return

    filename = getattr(video, "file_name", None) or f"{video.file_unique_id}.mp4"
    size_mb = round(video.file_size / 1024 / 1024, 1)
    local_path = os.path.join(DOWNLOAD_DIR, filename)

    status = await message.reply_text(
        f"📥 *Received:* `{filename}` ({size_mb} MB)\n⏳ Starting download...",
        parse_mode="Markdown"
    )

    try:
        # Use Telethon for all downloads (handles 2GB seamlessly)
        await download_with_telethon(
            message_id=message.message_id,
            chat_id=message.chat_id,
            dest=local_path,
            status_msg=status,
            filename=filename
        )

        await status.edit_text(
            f"✅ Downloaded!\n⬆️ Uploading `{filename}` to Terabox...",
            parse_mode="Markdown"
        )

        last_pct = [-1]

        async def on_upload_progress(pct, chunk, total):
            if pct != last_pct[0] and pct % 10 == 0:
                last_pct[0] = pct
                try:
                    await status.edit_text(
                        f"⬆️ Uploading to Terabox\n`{filename}`\nProgress: {pct}% ({chunk}/{total} chunks)",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        await upload_to_terabox(local_path, on_upload_progress)

        await status.edit_text(
            f"✅ *Upload Complete!*\n📁 `{filename}` ({size_mb} MB)\n☁️ Saved in Terabox → My Resources",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Error: {e}")
        await status.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")

    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


def get_bot_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    return app
