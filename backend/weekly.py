"""Weekly review: gather the week's data, ask the LLM for patterns (cached), store a report.

Used by three callers: the GET /checkin/weekly endpoint, the report endpoints,
and the scheduled job (scheduler.py). Concepts: caching + LLM + background job.
"""
import datetime
import json
import logging
import os
from collections import Counter
from typing import Dict, Tuple

from sqlalchemy.orm import Session

import cache
import llm
import models
from database import SessionLocal

log = logging.getLogger("auraflow.weekly")

PROMPT_VERSION = "v1"  # bump to invalidate cached insights when the prompt changes
CACHE_TTL_SECONDS = int(os.getenv("WEEKLY_CACHE_TTL_SECONDS", str(6 * 3600)))


def week_start(today: datetime.date = None) -> datetime.date:
    """Monday of the current (UTC) week. One report is stored per user per week."""
    today = today or datetime.datetime.utcnow().date()
    return today - datetime.timedelta(days=today.weekday())


def collect_week_data(db: Session, user_id: int) -> Dict:
    since = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    tasks = (
        db.query(models.Task)
        .filter(models.Task.user_id == user_id, models.Task.created_at >= since)
        .all()
    )
    logs = (
        db.query(models.EodSummary)
        .filter(models.EodSummary.user_id == user_id, models.EodSummary.created_at >= since)
        .order_by(models.EodSummary.created_at)
        .all()
    )
    total = len(tasks)
    done = sum(1 for t in tasks if t.is_completed)
    by_category = Counter((t.category or "General") for t in tasks)
    done_by_category = Counter((t.category or "General") for t in tasks if t.is_completed)
    return {
        "total": total,
        "completed": done,
        "completion_rate": round(done * 100 / total) if total else 0,
        "by_category": dict(by_category),
        "completed_by_category": dict(done_by_category),
        "open_titles": [t.title for t in tasks if not t.is_completed][:10],
        "daily_summaries": [
            {"date": str(log_row.created_at.date()), "text": log_row.summary_text} for log_row in logs
        ],
    }


def fallback_insight(stats: Dict) -> str:
    """Deterministic summary used when the LLM is unavailable. Not AI, and labelled as such."""
    if not stats["total"]:
        return "No tasks were recorded in the last 7 days."
    top = max(stats["by_category"], key=stats["by_category"].get)
    return (
        f"You completed {stats['completed']} of {stats['total']} tasks ({stats['completion_rate']}%). "
        f"Most of your work was in '{top}'. {len(stats['open_titles'])} task(s) are still open."
    )


def _build_prompt(stats: Dict) -> str:
    history = "\n".join(f"{d['date']}: {d['text']}" for d in stats["daily_summaries"]) or "(none)"
    return (
        "You are a concise productivity coach. Using ONLY the data below, write 3 short sentences about "
        "recurring patterns (which categories dominate, what keeps getting left open) and one concrete "
        "suggestion for next week. Do not invent facts.\n\n"
        f"Tasks this week: {stats['total']}, completed: {stats['completed']} ({stats['completion_rate']}%)\n"
        f"Tasks by category: {json.dumps(stats['by_category'])}\n"
        f"Completed by category: {json.dumps(stats['completed_by_category'])}\n"
        f"Still open: {json.dumps(stats['open_titles'])}\n"
        f"Daily reflections:\n{history}"
    )


def weekly_insight(db: Session, user_id: int, stats: Dict) -> Tuple[str, bool, str]:
    """Return (text, served_from_cache, source). Source is "llm" or "fallback"."""
    if not stats["total"] and not stats["daily_summaries"]:
        return fallback_insight(stats), False, "fallback"

    def ask() -> str:
        text = llm.chat(
            purpose="weekly_insight",
            model=llm.DEFAULT_MODEL,
            prompt=_build_prompt(stats),
            user_id=user_id,
            temperature=0.4,
        )
        if not text:
            raise llm.LLMError("empty reply")
        return text

    try:
        text, hit = cache.get_or_compute(
            db, "weekly_insight", (str(user_id), PROMPT_VERSION, json.dumps(stats, sort_keys=True)), CACHE_TTL_SECONDS, ask
        )
        return text, hit, "llm"
    except llm.LLMError as exc:
        log.warning("weekly insight fell back (LLM unavailable): %s", exc)
        return fallback_insight(stats), False, "fallback"


def generate_report(db: Session, user_id: int, force: bool = False) -> models.WeeklyReport:
    """Create or refresh this week's report. A unique (user, week) key prevents duplicates."""
    ws = week_start()
    report = (
        db.query(models.WeeklyReport)
        .filter(models.WeeklyReport.user_id == user_id, models.WeeklyReport.week_start == ws)
        .first()
    )
    if report and not force:
        return report

    stats = collect_week_data(db, user_id)
    insight, _cached, source = weekly_insight(db, user_id, stats)
    if report is None:
        report = models.WeeklyReport(user_id=user_id, week_start=ws)
        db.add(report)
    report.insight = insight
    report.insight_source = source
    report.stats_json = json.dumps(stats)
    report.created_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(report)
    return report


def generate_all_reports() -> int:
    """Scheduled job body: refresh this week's report for every user. Returns how many succeeded."""
    db = SessionLocal()
    ok = 0
    try:
        for (user_id,) in db.query(models.User.id).all():
            try:
                # force=True so the Sunday run reflects the week's final data. Unchanged data is a
                # cache hit, so re-running costs no LLM call.
                generate_report(db, user_id, force=True)
                ok += 1
            except Exception:
                log.exception("weekly report failed for user %s", user_id)
                db.rollback()
    finally:
        db.close()
    log.info("weekly report job finished: %s report(s)", ok)
    return ok
