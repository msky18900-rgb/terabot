import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger(__name__)

def format_size(mb: float) -> str:
    if mb >= 1024:
        return f"{mb/1024:.1f} GB"
    return f"{mb:.1f} MB"

@dataclass
class UploadJob:
    job_id: str
    filename: str
    size_mb: float
    local_path: str
    status_msg: object
    on_progress: Callable
    retries: int = 0
    max_retries: int = 3
    status: str = "queued"

class UploadQueue:
    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._jobs: dict[str, UploadJob] = {}
        self._current: Optional[str] = None
        self._processor_task: Optional[asyncio.Task] = None

    def start(self):
        self._processor_task = asyncio.create_task(self._process_loop())

    def queue_size(self) -> int:
        return self._queue.qsize()

    def current_job(self) -> Optional[UploadJob]:
        if self._current:
            return self._jobs.get(self._current)
        return None

    def all_jobs(self) -> list[UploadJob]:
        return list(self._jobs.values())

    async def add_job(self, job: UploadJob):
        self._jobs[job.job_id] = job
        await self._queue.put(job.job_id)
        logger.info(f"📋 Queued job {job.job_id[:8]}: {job.filename} ({format_size(job.size_mb)})")

    async def _process_loop(self):
        while True:
            job_id = await self._queue.get()
            job = self._jobs.get(job_id)
            if not job:
                continue
            self._current = job_id
            await self._run_job(job)
            self._current = None
            self._queue.task_done()

    async def _run_job(self, job: UploadJob):
        from terabox import upload_to_terabox
        import os

        for attempt in range(1, job.max_retries + 1):
            try:
                job.status = "uploading"
                if attempt > 1:
                    await job.status_msg.edit_text(
                        f"🔄 Retry {attempt}/{job.max_retries}\n⬆️ Uploading `{job.filename}`...",
                        parse_mode="Markdown"
                    )

                await upload_to_terabox(job.local_path, job.on_progress)

                job.status = "done"
                await job.status_msg.edit_text(
                    f"✅ *Upload Complete!*\n"
                    f"📁 `{job.filename}` ({format_size(job.size_mb)})\n"
                    f"☁️ Saved in Terabox → 我的资源",
                    parse_mode="Markdown"
                )
                break

            except Exception as e:
                logger.error(f"Job {job.filename} attempt {attempt} failed: {e}")
                job.retries = attempt
                if attempt == job.max_retries:
                    job.status = "failed"
                    await job.status_msg.edit_text(
                        f"❌ *Upload Failed* after {job.max_retries} attempts\n"
                        f"📁 `{job.filename}`\nError: `{str(e)[:200]}`",
                        parse_mode="Markdown"
                    )
                else:
                    wait = 15 * attempt
                    logger.info(f"Retrying in {wait}s...")
                    await asyncio.sleep(wait)
            finally:
                if job.status in ("done", "failed") and os.path.exists(job.local_path):
                    try:
                        os.remove(job.local_path)
                    except Exception:
                        pass

upload_queue = UploadQueue()
