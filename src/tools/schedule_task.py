"""Tool for agents to create scheduled tasks via natural language.

The LLM receives this tool and can call it when a user requests a recurring task.
The tool parses the cron schedule and registers the job with the scheduler.
"""
from __future__ import annotations

import logging
import re

from tools.registry import Tool

log = logging.getLogger(__name__)

# Module-level reference set by bot.py at startup
_scheduler = None
_current_context: dict = {}  # set per-call by the agent loop


def set_scheduler(scheduler):
    global _scheduler
    _scheduler = scheduler


def set_call_context(user_id: int, agent_id: str, chat_id: int):
    """Set the context for the current tool invocation."""
    global _current_context
    _current_context = {
        "user_id": user_id,
        "agent_id": agent_id,
        "chat_id": chat_id,
    }


# ── Common natural-language → cron mappings ──────────────────────────

PRESETS = {
    "daily": "0 {hour} * * *",
    "every day": "0 {hour} * * *",
    "weekdays": "0 {hour} * * 1-5",
    "every weekday": "0 {hour} * * 1-5",
    "weekends": "0 {hour} * * 0,6",
    "every weekend": "0 {hour} * * 0,6",
    "weekly": "0 {hour} * * 1",
    "every week": "0 {hour} * * 1",
    "every monday": "0 {hour} * * 1",
    "every tuesday": "0 {hour} * * 2",
    "every wednesday": "0 {hour} * * 3",
    "every thursday": "0 {hour} * * 4",
    "every friday": "0 {hour} * * 5",
    "every saturday": "0 {hour} * * 6",
    "every sunday": "0 {hour} * * 0",
    "monthly": "0 {hour} 1 * *",
    "every month": "0 {hour} 1 * *",
}


def _schedule_task(cron_expression: str, task_description: str) -> str:
    """Create a scheduled recurring task."""
    if not _scheduler:
        return "Error: Scheduler is not available."

    ctx = _current_context
    if not ctx.get("user_id"):
        return "Error: Could not determine user context for scheduling."

    # Validate cron expression
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(cron_expression)
    except Exception as e:
        return f"Invalid cron expression '{cron_expression}': {e}"

    job_id = _scheduler.add_job(
        user_id=ctx["user_id"],
        agent_id=ctx["agent_id"],
        chat_id=ctx["chat_id"],
        cron_expression=cron_expression,
        task_description=task_description,
    )

    return (
        f"✅ Scheduled job #{job_id} created!\n"
        f"Schedule: {cron_expression}\n"
        f"Task: {task_description}\n"
        f"I'll run this automatically and send you the results."
    )


SCHEDULE_TASK_TOOL = Tool(
    name="schedule_task",
    description=(
        "Create a recurring scheduled task. The task will run automatically "
        "at the specified schedule and send the results to the user. "
        "Use standard 5-field cron syntax for the schedule: "
        "'minute hour day-of-month month day-of-week'. "
        "Examples: '0 7 * * *' = every day at 7 AM, "
        "'0 7 * * 1-5' = weekdays at 7 AM, "
        "'0 9 * * 1' = every Monday at 9 AM, "
        "'30 18 1 * *' = 1st of every month at 6:30 PM. "
        "The task_description should be the full prompt/question to execute "
        "each time the job runs, as if the user typed it."
    ),
    parameters={
        "type": "object",
        "properties": {
            "cron_expression": {
                "type": "string",
                "description": (
                    "Standard 5-field cron expression: 'minute hour day-of-month month day-of-week'. "
                    "Example: '0 7 * * *' for every day at 7:00 AM."
                ),
            },
            "task_description": {
                "type": "string",
                "description": (
                    "The full task/prompt to execute on each run. Write it as if "
                    "the user is asking the question. Example: 'Find me 5 software "
                    "engineer job postings in Austin, TX with salary info.'"
                ),
            },
        },
        "required": ["cron_expression", "task_description"],
    },
    function=_schedule_task,
)
