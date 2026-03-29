import asyncio
import logging
from bot import get_bot_app, tele_client
from userbot import start_userbot, client as userbot_client
from queue_manager import upload_queue
from config import TELEGRAM_PHONE

logging.basicConfig(level=logging.INFO)


async def run_all():
    # Start upload queue processor
    upload_queue.start()

    # Start Telethon downloader client
    await tele_client.start(phone=TELEGRAM_PHONE)

    # Start userbot (forwards videos to bot)
    await userbot_client.start(phone=TELEGRAM_PHONE)

    # Start bot
    bot_app = get_bot_app()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

    logging.info("✅ All services running.")

    # Keep running
    await userbot_client.run_until_disconnected()

    # Graceful shutdown
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_all())
```

---

## What's new

| Feature | Detail |
|---|---|
| `/start` | Welcome message with command list |
| `/status` | Shows current upload, queue position, done/failed counts |
| **Queue** | Multiple forwarded videos process one at a time in order |
| **Auto-retry** | Failed uploads retry up to 3× with exponential backoff (10s, 20s, 30s) |
| **Download first** | Files download immediately, then wait in queue for upload |
| **Unique filenames** | UUID prefix prevents collisions if same file is sent twice |

---

## Deploy checklist
```
1. Generate TELEGRAM_SESSION string locally (see previous message)
2. Push to GitHub
3. Railway → New Project → GitHub repo
4. Add all .env variables in Railway dashboard
5. Deploy — Railway builds Docker image and starts everything
