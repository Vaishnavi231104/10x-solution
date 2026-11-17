import datetime
import logging
from typing import Any, Dict, List

from sqlalchemy.orm import Session

import llm
import models
from agent.state import AgentState
from database import SessionLocal

log = logging.getLogger("auraflow.agent")

PRIORITIES = {"high": "High", "medium": "Medium", "low": "Low"}
MAX_CATEGORY_LEN = 30


def _title_of(task: Any) -> str:
    return (task.get("title", "") if isinstance(task, dict) else str(task)).strip()


def _fallback_tasks(tasks_raw: List[Any]) -> List[Dict[str, str]]:
    return [
        {"title": _title_of(t), "category": "General", "priority": "Medium"}
        for t in tasks_raw
        if _title_of(t)
    ]


def validate_classification(parsed: Any, tasks_raw: List[Any]) -> List[Dict[str, str]]:
    """Never trust model output. Keep the user's own titles; accept only a sane category and priority.

    Raises ValueError when the reply does not line up with the input, so the caller falls back.
    """
    originals = [t for t in tasks_raw if _title_of(t)]
    if not isinstance(parsed, list) or len(parsed) != len(originals):
        raise ValueError("classification does not match the input tasks")

    result = []
    for original, item in zip(originals, parsed):
        if not isinstance(item, dict):
            raise ValueError("classification item is not an object")
        category = str(item.get("category", "")).strip()[:MAX_CATEGORY_LEN] or "General"
        priority = PRIORITIES.get(str(item.get("priority", "")).strip().lower(), "Medium")
        result.append({"title": _title_of(original), "category": category, "priority": priority})
    return result


def classifier_node(state: AgentState) -> dict:
    """Uses the LLM to categorise raw task strings. Output is validated; failures fall back safely."""
    tasks_raw = state.get("tasks_raw", [])
    if not tasks_raw:
        return {"classified_tasks": []}

    titles = [_title_of(t) for t in tasks_raw if _title_of(t)]
    prompt = f"""
    You are a personal productivity assistant. For each task below decide:
    1. category (e.g. Work, Personal, Study, Health, Urgent)
    2. priority (High, Medium or Low)

    Tasks, in order: {titles}

    Reply with ONLY a JSON array with one object per task, in the same order and with the same count,
    like: [{{"title": "...", "category": "Work", "priority": "High"}}]
    No markdown, no commentary.
    """
    try:
        reply = llm.chat(
            purpose="classify_tasks",
            model=llm.DEFAULT_MODEL,
            prompt=prompt,
            user_id=state.get("user_id"),
            temperature=0.1,
        )
        return {"classified_tasks": validate_classification(llm.parse_json_reply(reply), tasks_raw)}
    except (llm.LLMError, ValueError) as exc:  # ValueError covers bad JSON and failed validation
        log.warning("classifier fell back to defaults: %s", exc)
        return {"classified_tasks": _fallback_tasks(tasks_raw)}


def overdue_surfacer_node(state: AgentState) -> dict:
    """Queries the database for this user's uncompleted, overdue tasks."""
    user_id = state.get("user_id")
    now = datetime.datetime.utcnow()

    db: Session = SessionLocal()
    try:
        overdue_db_tasks = db.query(models.Task).filter(
            models.Task.user_id == user_id,
            models.Task.is_completed == False,  # noqa: E712 (SQLAlchemy needs ==)
            models.Task.due_date < now,
        ).all()
        return {
            "overdue_tasks": [
                {"id": t.id, "title": t.title, "category": t.category, "priority": t.priority}
                for t in overdue_db_tasks
            ]
        }
    finally:
        db.close()


def eod_summarizer_node(state: AgentState) -> dict:
    """A short, encouraging end-of-day summary. Falls back to plain counts if the LLM is down."""
    user_id = state.get("user_id")

    db: Session = SessionLocal()
    try:
        today_start = datetime.datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tasks = db.query(models.Task).filter(
            models.Task.user_id == user_id,
            models.Task.created_at >= today_start,
        ).all()
        completed = [t.title for t in tasks if t.is_completed]
        pending = [t.title for t in tasks if not t.is_completed]

        prompt = f"""
        Review this user's day:
        Completed: {completed}
        Remaining: {pending}

        Write a concise, encouraging 2-sentence summary addressed directly to them. Use only the data above.
        """
        try:
            summary = llm.chat(
                purpose="eod_summary",
                model=llm.DEFAULT_MODEL,
                prompt=prompt,
                user_id=user_id,
                temperature=0.7,
            )
            if not summary:
                raise llm.LLMError("empty reply")
        except llm.LLMError as exc:
            log.warning("eod summary fell back: %s", exc)
            summary = f"You completed {len(completed)} task(s) today and have {len(pending)} remaining."
        return {"eod_summary": summary}
    finally:
        db.close()


def next_day_planner_node(state: AgentState) -> dict:
    """Suggests 2-3 concrete next steps for tomorrow from the user's open tasks."""
    user_id = state.get("user_id")

    db: Session = SessionLocal()
    try:
        pending_titles = [
            t.title
            for t in db.query(models.Task).filter(
                models.Task.user_id == user_id,
                models.Task.is_completed == False,  # noqa: E712
            ).all()
        ]
        prompt = f"""
        Based on these open tasks: {pending_titles}, propose 2-3 specific, actionable items for tomorrow.
        Reply with ONLY a JSON array of strings. No markdown.
        Example: ["Finish the project draft", "Review feedback on the PR"]
        """
        try:
            plan = llm.parse_json_reply(
                llm.chat(
                    purpose="next_day_plan",
                    model=llm.DEFAULT_MODEL,
                    prompt=prompt,
                    user_id=user_id,
                    temperature=0.3,
                )
            )
            if not isinstance(plan, list) or not all(isinstance(p, str) and p.strip() for p in plan):
                raise ValueError("plan is not a list of strings")
            return {"tomorrow_plan": [p.strip() for p in plan][:5]}
        except (llm.LLMError, ValueError) as exc:
            log.warning("planner fell back: %s", exc)
            return {"tomorrow_plan": ["Review incomplete tasks from today"]}
    finally:
        db.close()
