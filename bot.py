import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from queue_manager import upload_queue
from config import BOT_TOKEN, ALLOWED_USER_ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Terabox Upload Bot*\n\n"
        "Forward or send any video and I'll upload it to Terabox in original quality.\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/status - Show queue and current upload\n",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ALLOWED_USER_ID and user_id != ALLOWED_USER_ID:
        return

    current = upload_queue.current_job()
    all_jobs = upload_queue.all_jobs()

    queued = [j for j in all_jobs if j.status == "queued"]
    done = [j for j in all_jobs if j.status == "done"]
    failed = [j for j in all_jobs if j.status == "failed"]

    lines = ["📊 *Upload Queue Status*\n"]

    if current:
        icon = "⬆️" if current.status == "uploading" else "📥"
        retry_info = f" | Retry {current.retries}/{current.max_retries}" if current.retries > 0 else ""
        lines.append(
            f"{icon} *Now Processing:*\n"
            f"`{current.filename}` ({current.size_mb:.1f} MB)\n"
            f"Status: `{current.status}`{retry_info}\n"
        )
    else:
        lines.append("💤 *No active job*\n")

    if queued:
        lines.append(f"⏳ *Queued ({len(queued)}):*")
        for i, j in enumerate(queued, 1):
            lines.append(f" {i}. `{j.filename}` ({j.size_mb:.1f} MB)")
        lines.append("")

    lines.append(
        f"✅ Completed: {len(done)} | "
        f"❌ Failed: {len(failed)} | "
        f"📦 In queue: {len(queued)}"
    )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


def get_bot_app():
    """Return the python-telegram-bot application (no Telethon, no session stuff)"""
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    return app
