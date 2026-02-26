"""In-app scheduler backed by APScheduler + SQLite.

Each scheduled job:
  1. Runs the originating agent's handle_message() with the stored task description.
  2. Sends the agent's response to the user's Telegram chat.

Jobs survive restarts because they are stored in the DB and reloaded on boot.
"""
from __future__ import annotations

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

log = logging.getLogger(__name__)


class JobScheduler:
    """Manages recurring scheduled tasks for LifePilot."""

    def __init__(self, db, agents: dict, bot_app):
        self.db = db
        self.agents = agents
        self.bot_app = bot_app  # telegram Application (for sending messages)
        self.scheduler = AsyncIOScheduler()
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self):
        """Load all persisted jobs from the DB and start the scheduler."""
        jobs = self.db.get_all_scheduled_jobs()
        for job in jobs:
            self._add_to_scheduler(job)
        self.scheduler.start()
        self._running = True
        log.info("Scheduler started with %d persisted job(s).", len(jobs))

    def stop(self):
        if self._running:
            self.scheduler.shutdown(wait=False)
            self._running = False
            log.info("Scheduler stopped.")

    # ── Public API ────────────────────────────────────────────────────

    def add_job(self, user_id: int, agent_id: str, chat_id: int,
                cron_expression: str, task_description: str) -> int:
        """Create a new scheduled job and register it with APScheduler."""
        job_id = self.db.add_scheduled_job(
            user_id, agent_id, chat_id, cron_expression, task_description,
        )
        job_row = self.db.get_scheduled_job(job_id)
        self._add_to_scheduler(job_row)
        log.info("Scheduled job #%d for user %d: '%s' [%s]",
                 job_id, user_id, task_description[:60], cron_expression)
        return job_id

    def remove_job(self, job_id: int):
        """Remove a job from both APScheduler and the DB."""
        scheduler_id = f"lifepilot_job_{job_id}"
        try:
            self.scheduler.remove_job(scheduler_id)
        except Exception:
            pass  # might not be in scheduler if it was disabled
        self.db.delete_scheduled_job(job_id)
        log.info("Removed scheduled job #%d", job_id)

    def get_user_jobs(self, user_id: int) -> list[dict]:
        return self.db.get_scheduled_jobs(user_id)

    # ── Internal ──────────────────────────────────────────────────────

    def _add_to_scheduler(self, job_row: dict):
        """Register a single job with APScheduler from a DB row."""
        scheduler_id = f"lifepilot_job_{job_row['id']}"
        try:
            trigger = CronTrigger.from_crontab(job_row["cron_expression"])
        except ValueError as e:
            log.error("Invalid cron '%s' for job #%d: %s",
                      job_row["cron_expression"], job_row["id"], e)
            return

        self.scheduler.add_job(
            self._execute_job,
            trigger=trigger,
            id=scheduler_id,
            replace_existing=True,
            kwargs={"job_id": job_row["id"]},
        )

    async def _execute_job(self, job_id: int):
        """Run the agent for a scheduled job and send the response via Telegram."""
        job = self.db.get_scheduled_job(job_id)
        if not job:
            log.warning("Job #%d no longer exists, skipping.", job_id)
            return

        agent = self.agents.get(job["agent_id"])
        if not agent:
            log.warning("Agent '%s' not found for job #%d", job["agent_id"], job_id)
            return

        try:
            log.info("Executing scheduled job #%d: '%s'", job_id, job["task_description"][:60])
            response = await agent.handle_message(job["user_id"], job["task_description"])

            # Send via Telegram
            bot = self.bot_app.bot
            try:
                await bot.send_message(
                    chat_id=job["chat_id"],
                    text=f"⏰ *Scheduled Task*\n\n{response}",
                    parse_mode="Markdown",
                )
            except Exception:
                # Fallback without Markdown if parsing fails
                await bot.send_message(
                    chat_id=job["chat_id"],
                    text=f"⏰ Scheduled Task\n\n{response}",
                )
        except Exception as e:
            log.error("Scheduled job #%d failed: %s", job_id, e)
