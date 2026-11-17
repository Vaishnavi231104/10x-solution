"""Caching, PDF reporting and the scheduled job."""
import datetime

import pytest

import cache
import models
import weekly
from conftest import register


def make_week(client, headers, titles=("Write report", "Gym", "Study")):
    for title in titles:
        task_id = client.post("/tasks", json={"title": title, "category": "Work"}, headers=headers).json()["id"]
        client.patch(f"/tasks/{task_id}", headers=headers)  # complete it


# --- caching ----------------------------------------------------------------------------------


def test_weekly_insight_is_cached_then_recomputed_when_data_changes(client, auth_headers, fake_llm):
    make_week(client, auth_headers)
    fake_llm.reply = "You work best in the morning."

    first = client.get("/checkin/weekly", headers=auth_headers).json()
    assert first == {"weekly_insight": "You work best in the morning.", "cached": False, "source": "llm"}
    assert fake_llm.calls == 1

    second = client.get("/checkin/weekly", headers=auth_headers).json()
    assert second["cached"] is True and second["weekly_insight"] == first["weekly_insight"]
    assert fake_llm.calls == 1  # no second LLM call: that is the point of the cache

    client.post("/tasks", json={"title": "New task this week"}, headers=auth_headers)  # data changed
    third = client.get("/checkin/weekly", headers=auth_headers).json()
    assert third["cached"] is False
    assert fake_llm.calls == 2


def test_cache_entries_expire(db):
    key = cache.make_key("t", "a")
    cache.put(db, key, "value", ttl_seconds=-1)  # already expired
    assert cache.get(db, key) is None
    cache.put(db, key, "value", ttl_seconds=60)
    assert cache.get(db, key) == "value"


def test_cache_keys_do_not_collide_across_namespaces_or_inputs():
    assert cache.make_key("a", "x") != cache.make_key("b", "x")
    assert cache.make_key("a", "x", "y") != cache.make_key("a", "xy")


def test_weekly_insight_falls_back_when_llm_is_down_and_is_not_cached(client, auth_headers, fake_llm):
    make_week(client, auth_headers)
    fake_llm.reply = RuntimeError("down")
    body = client.get("/checkin/weekly", headers=auth_headers).json()
    assert body["source"] == "fallback" and body["cached"] is False
    assert "3 of 3 tasks" in body["weekly_insight"]

    fake_llm.reply = "Back online."
    assert client.get("/checkin/weekly", headers=auth_headers).json()["weekly_insight"] == "Back online."


def test_weekly_with_no_data_makes_no_llm_call(client, auth_headers, fake_llm):
    body = client.get("/checkin/weekly", headers=auth_headers).json()
    assert body["source"] == "none"
    assert fake_llm.calls == 0


# --- reports / PDF ----------------------------------------------------------------------------


def test_report_run_get_and_no_duplicates(client, auth_headers, fake_llm, db):
    assert client.get("/reports/weekly", headers=auth_headers).status_code == 404
    make_week(client, auth_headers)
    fake_llm.reply = "Insight text."

    run = client.post("/reports/weekly/run", headers=auth_headers)
    assert run.status_code == 200 and run.json()["insight"] == "Insight text."
    client.post("/reports/weekly/run", headers=auth_headers)  # run again

    assert db.query(models.WeeklyReport).count() == 1  # one row per user per week
    latest = client.get("/reports/weekly", headers=auth_headers).json()
    assert latest["stats"]["completed"] == 3 and latest["stats"]["completion_rate"] == 100


def test_pdf_report_is_a_real_pdf(client, auth_headers, fake_llm):
    make_week(client, auth_headers)
    fake_llm.reply = "A short insight."
    r = client.get("/reports/weekly/pdf", headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert "weekly-report-" in r.headers["content-disposition"]
    assert r.content.startswith(b"%PDF") and len(r.content) > 500


def test_pdf_text_cleanup_strips_markdown_and_keeps_typographic_punctuation():
    from pdf_report import _t

    assert _t("**Concrete suggestion:** block 9‑11am “daily”") == 'Concrete suggestion: block 9-11am "daily"'
    assert _t("café") == "café"  # real Latin-1 letters are kept


def test_pdf_survives_non_latin_text(client, auth_headers, fake_llm):
    make_week(client, auth_headers, titles=("✓ naïve café — 日本語 🚀",))
    fake_llm.reply = "Great week ✓ 日本語"
    assert client.get("/reports/weekly/pdf", headers=auth_headers).status_code == 200


# --- scheduled job ----------------------------------------------------------------------------


def test_job_body_creates_one_report_per_user_and_is_idempotent(client, fake_llm, db):
    for email in ("a@example.com", "b@example.com"):
        make_week(client, register(client, email))
    fake_llm.reply = "Insight."

    assert weekly.generate_all_reports() == 2
    assert weekly.generate_all_reports() == 2  # run again: refreshes, does not duplicate
    assert db.query(models.WeeklyReport).count() == 2
    assert fake_llm.calls == 2  # second run reused the cache: unchanged data costs no LLM call


def test_job_continues_when_one_users_report_fails(client, fake_llm, db, monkeypatch):
    for email in ("a@example.com", "b@example.com"):
        make_week(client, register(client, email))
    real = weekly.generate_report

    def flaky(session, user_id, force=False):
        if user_id == 1:
            raise RuntimeError("boom")
        return real(session, user_id, force)

    monkeypatch.setattr(weekly, "generate_report", flaky)
    fake_llm.reply = "Insight."
    assert weekly.generate_all_reports() == 1  # user 2 still got a report
    assert db.query(models.WeeklyReport).count() == 1


def test_scheduler_registers_a_sunday_cron_job(monkeypatch):
    from scheduler import start_scheduler

    monkeypatch.delenv("DISABLE_SCHEDULER", raising=False)
    monkeypatch.delenv("WEEKLY_REPORT_CRON", raising=False)
    scheduler = start_scheduler()
    try:
        job = scheduler.get_job("weekly_reports")
        assert job is not None
        assert job.next_run_time.weekday() == 6  # Sunday
        assert job.next_run_time.hour == 18
        assert job.max_instances == 1
    finally:
        scheduler.shutdown(wait=False)


def test_scheduler_can_be_disabled(monkeypatch):
    from scheduler import start_scheduler

    monkeypatch.setenv("DISABLE_SCHEDULER", "1")
    assert start_scheduler() is None


def test_week_start_is_monday():
    assert weekly.week_start(datetime.date(2026, 11, 18)).weekday() == 0  # a Wednesday -> its Monday
    assert weekly.week_start(datetime.date(2026, 11, 16)) == datetime.date(2026, 11, 16)
