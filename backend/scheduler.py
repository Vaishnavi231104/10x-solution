"""Cron job wiring (concept: background / cron jobs).

APScheduler runs inside the API process. Default schedule: every Sunday 18:00 UTC.
Override with WEEKLY_REPORT_CRON (standard 5-field crontab, day names recommended),
or set DISABLE_SCHEDULER=1 (the test suite does).

Limitation: one scheduler per API process. Run a single worker, or move this to
a dedicated worker/cron service if you scale out.
"""
import logging
import os
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from weekly import generate_all_reports

log = logging.getLogger("auraflow.scheduler")

DEFAULT_CRON = "0 18 * * sun"


def start_scheduler() -> Optional[BackgroundScheduler]:
    if os.getenv("DISABLE_SCHEDULER") == "1":
        log.info("scheduler disabled by DISABLE_SCHEDULER=1")
        return None

    cron = os.getenv("WEEKLY_REPORT_CRON", DEFAULT_CRON)
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        generate_all_reports,
        CronTrigger.from_crontab(cron, timezone="UTC"),
        id="weekly_reports",
        max_instances=1,  # never overlap two runs
        coalesce=True,    # if the server was down at the trigger time, run once, not many times
        misfire_grace_time=3600,
        replace_existing=True,
    )
    scheduler.start()
    log.info("scheduler started; weekly reports cron = %r", cron)
    return scheduler
