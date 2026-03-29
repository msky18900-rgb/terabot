import os
import uuid
import logging
import asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, MessageHandler,
    CommandHandler, filters, ContextTypes
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from queue_manager import upload_queue, UploadJob
from config import (
    BOT_TOKEN, DOWNLOAD_DIR, ALLOWED_USER_ID,
    TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_SESSION
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tele_client = TelegramClient(
    StringSession(TELEGRAM_SESSION),
    TELEGRAM_API_ID,
    TELEGRAM_API_HASH
)


# ── /start ─────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Terabox Upload Bot*\n\n"
        "Forward or send any video and I'll upload it to Terabox in original quality.\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/status - Show queue and current upload\n",
        parse_mode="Markdown"
    )


# ── /status ────────────────────────────────────────────────────────────────────
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        return

    current = upload_queue.current_job()
    all_jobs = upload_queue.all_jobs()
    queued  = [j for j in all_jobs if j.status == "queued"]
    done    = [j for j in all_jobs if j.status == "done"]
    failed  = [j for j in all_jobs if j.status == "failed"]

    lines = ["📊 *Upload Queue Status*\n"]

    if current:
        icon = "⬆️" if current.status == "uploading" else "📥"
        retry_info = f" | Retry {current.retries}/{current.max_retries}" if current.retries > 0 else ""
        lines.append(
            f"{icon} *Now Processing:*\n"
            f"  `{current.filename}` ({current.size_mb} MB)\n"
            f"  Status: `{current.status}`{retry_info}\n"
        )
    else:
        lines.append("💤 *No active job*\n")

    if queued:
        lines.append(f"⏳ *Queued ({len(queued)}):*")
        for i, j in enumerate(queued, 1):
            lines.append(f"  {i}. `{j.filename}` ({j.size_mb} MB)")
        lines.append("")

    lines.append(
        f"✅ Completed: {len(done)} | "
        f"❌ Failed: {len(failed)} | "
        f"📦 In queue: {len(queued)}"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ── Video handler ──────────────────────────────────────────────────────────────
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

    # Ensure filename has extension
    filename = getattr(video, "file_name", None) or f"{video.file_unique_id}.mp4"
    if "." not in filename:
        filename += ".mp4"

    # Sanitize filename to avoid path issues with special characters
    safe_filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    safe_filename = safe_filename.strip()

    size_mb = round(video.file_size / 1024 / 1024, 1)
    unique_name = f"{uuid.uuid4()}_{safe_filename}"
    local_path = os.path.join(DOWNLOAD_DIR, unique_name)

    # Ensure download directory exists
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    queue_pos = upload_queue.queue_size() + (1 if upload_queue.current_job() else 0)

    status = await message.reply_text(
        f"📥 *Received:* `{filename}` ({size_mb} MB)\n"
        f"⏳ Downloading...",
        parse_mode="Markdown"
    )

    try:
        # ── Download via Telethon MTProto (supports up to 2GB) ────────────────
        last_dl_pct = [-1]

        async def dl_progress(received, total):
            pct = int((received / total) * 100) if total else 0
            if pct != last_dl_pct[0] and pct % 10 == 0:
                last_dl_pct[0] = pct
                mb_done  = round(received / 1024 / 1024, 1)
                mb_total = round(total / 1024 / 1024, 1)
                try:
                    await status.edit_text(
                        f"📥 Downloading `{filename}`\n"
                        f"{pct}% — {mb_done}/{mb_total} MB",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        logger.info(f"Starting download: {filename} -> {local_path}")

        # Fetch message object via Telethon
        tg_msg = await tele_client.get_messages(message.chat_id, ids=message.message_id)

        if tg_msg is None or tg_msg.media is None:
            await status.edit_text(
                "❌ Could not access media via MTProto.\n"
                "Make sure the bot and userbot share the same chat.",
                parse_mode="Markdown"
            )
            return

        # Download — Telethon returns the actual path it saved to
        downloaded_path = await tele_client.download_media(
            tg_msg,
            file=local_path,
            progress_callback=dl_progress
        )

        logger.info(f"Telethon saved file to: {downloaded_path}")

        # Verify the file actually exists on disk
        if not downloaded_path or not os.path.exists(downloaded_path):
            await status.edit_text(
                f"❌ Download failed — file missing after download.\n"
                f"Expected path: `{local_path}`",
                parse_mode="Markdown"
            )
            return

        # Use exact path Telethon chose (it may adjust the extension)
        local_path = downloaded_path

        await status.edit_text(
            f"✅ Downloaded `{filename}`\n"
            f"📦 Added to upload queue (position {queue_pos + 1})",
            parse_mode="Markdown"
        )

        # ── Upload progress callback ───────────────────────────────────────────
        last_up_pct = [-1]

        async def on_upload_progress(pct, chunk, total):
            if pct != last_up_pct[0] and pct % 10 == 0:
                last_up_pct[0] = pct
                try:
                    await status.edit_text(
                        f"⬆️ Uploading to Terabox\n"
                        f"`{filename}`\n"
                        f"Progress: {pct}% ({chunk}/{total} chunks)",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

        # ── Add to upload queue ────────────────────────────────────────────────
        job = UploadJob(
            job_id=str(uuid.uuid4()),
            filename=filename,
            size_mb=size_mb,
            local_path=local_path,
            status_msg=status,
            on_progress=on_upload_progress,
        )
        await upload_queue.add_job(job)

    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        await status.edit_text(f"❌ Download error: `{e}`", parse_mode="Markdown")
        if os.path.exists(local_path):
            os.remove(local_path)


# ── App factory ────────────────────────────────────────────────────────────────
def get_bot_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    return app
