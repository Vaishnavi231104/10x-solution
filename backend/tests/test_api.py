"""API, auth and validation tests: the failure cases a reviewer would try first."""
import pytest

from conftest import register

# --- authentication ---------------------------------------------------------------------------


def test_signup_rejects_short_password_and_bad_email(client):
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert client.post("/auth/signup", json={"email": "not-an-email", "password": "password123"}).status_code == 422


def test_signup_rejects_password_over_bcrypt_limit(client):
    too_long = "x" * 73
    assert client.post("/auth/signup", json={"email": "a@example.com", "password": too_long}).status_code == 422


def test_duplicate_signup_is_rejected(client):
    register(client)
    r = client.post("/auth/signup", json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 400


def test_wrong_password_is_401(client):
    register(client)
    r = client.post("/auth/login", data={"username": "a@example.com", "password": "wrong-password"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", ["/tasks", "/tasks/overdue", "/checkin/weekly", "/reports/weekly", "/reports/weekly/pdf", "/usage/llm"])
def test_protected_routes_require_a_token(client, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_secret_key_is_required_in_production(monkeypatch):
    import auth

    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError):
        auth._load_secret_key()


# --- tasks ------------------------------------------------------------------------------------


def test_create_task_validates_input(client, auth_headers):
    ok = client.post("/tasks", json={"title": "Write tests", "priority": "High"}, headers=auth_headers)
    assert ok.status_code == 201 and ok.json()["priority"] == "High"
    assert client.post("/tasks", json={"title": "", "priority": "High"}, headers=auth_headers).status_code == 422
    assert client.post("/tasks", json={"title": "x", "priority": "Urgent!!"}, headers=auth_headers).status_code == 422


def test_users_cannot_see_or_change_each_others_tasks(client):
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    task_id = client.post("/tasks", json={"title": "Alice secret"}, headers=alice).json()["id"]

    assert client.patch(f"/tasks/{task_id}", headers=bob).status_code == 404
    assert client.get("/tasks", headers=bob).json() == []
    # ...and the evening check-in silently ignores ids that are not yours.
    assert client.patch(f"/tasks/{task_id}", headers=alice).json()["is_completed"] is True


def test_data_survives_a_restart(client, auth_headers):
    from database import SessionLocal, engine
    import models

    client.post("/tasks", json={"title": "Persist me"}, headers=auth_headers)
    engine.dispose()  # drop every pooled connection, like a process restart
    session = SessionLocal()
    try:
        assert session.query(models.Task).filter_by(title="Persist me").count() == 1
    finally:
        session.close()


# --- morning / evening check-ins (LLM output is validated, never trusted) ---------------------


def test_morning_checkin_saves_validated_classification(client, auth_headers, fake_llm):
    fake_llm.reply = (
        '[{"title":"IGNORED","category":"Work","priority":"high"},'
        '{"title":"x","category":"Health","priority":"whatever"}]'
    )
    r = client.post("/checkin/morning", json=["Write report", "Gym"], headers=auth_headers)
    assert r.status_code == 200
    tasks = client.get("/tasks", headers=auth_headers).json()
    by_title = {t["title"]: t for t in tasks}
    assert set(by_title) == {"Write report", "Gym"}  # the user's own titles are kept
    assert by_title["Write report"]["priority"] == "High"  # "high" normalised
    assert by_title["Gym"]["priority"] == "Medium"  # nonsense priority -> safe default
    assert by_title["Gym"]["category"] == "Health"


@pytest.mark.parametrize("bad_reply", ["this is not json at all", "[]", '{"not": "a list"}', '[{"title":"a"}]'])
def test_morning_checkin_falls_back_when_model_output_is_unusable(client, auth_headers, fake_llm, bad_reply):
    fake_llm.reply = bad_reply
    r = client.post("/checkin/morning", json=["Task one", "Task two"], headers=auth_headers)
    assert r.status_code == 200
    tasks = client.get("/tasks", headers=auth_headers).json()
    assert sorted(t["title"] for t in tasks) == ["Task one", "Task two"]
    assert all(t["category"] == "General" and t["priority"] == "Medium" for t in tasks)


def test_morning_checkin_survives_llm_outage(client, auth_headers, fake_llm):
    fake_llm.reply = RuntimeError("groq is down")
    r = client.post("/checkin/morning", json=["Only task"], headers=auth_headers)
    assert r.status_code == 200
    assert client.get("/tasks", headers=auth_headers).json()[0]["title"] == "Only task"


def test_morning_checkin_input_limits(client, auth_headers, fake_llm):
    assert client.post("/checkin/morning", json=["t"] * 51, headers=auth_headers).status_code == 422
    assert client.post("/checkin/morning", json=["x" * 301], headers=auth_headers).status_code == 422


def test_evening_checkin_returns_summary_and_plan(client, auth_headers, fake_llm):
    task_id = client.post("/tasks", json={"title": "Ship it"}, headers=auth_headers).json()["id"]
    fake_llm.reply = lambda prompt: '["Step A", "Step B"]' if "JSON array of strings" in prompt else "Nice day."
    r = client.post("/checkin/evening", json=[task_id], headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["eod_summary"] == "Nice day."
    assert r.json()["tomorrow_plan"] == ["Step A", "Step B"]


# --- LLM cost log -----------------------------------------------------------------------------


def test_every_llm_call_is_logged_with_tokens(client, auth_headers, fake_llm):
    fake_llm.reply = '[{"title":"a","category":"Work","priority":"High"}]'
    client.post("/checkin/morning", json=["a"], headers=auth_headers)
    usage = client.get("/usage/llm", headers=auth_headers).json()
    assert usage["calls"] == 1 and usage["failed_calls"] == 0
    assert usage["prompt_tokens"] == 11 and usage["completion_tokens"] == 7 and usage["total_tokens"] == 18
    assert usage["estimated_cost_usd"] == 0  # free tier
    assert usage["recent"][0]["purpose"] == "classify_tasks"


def test_failed_llm_calls_are_logged_too(client, auth_headers, fake_llm):
    fake_llm.reply = RuntimeError("boom")
    client.post("/checkin/morning", json=["a"], headers=auth_headers)
    usage = client.get("/usage/llm", headers=auth_headers).json()
    assert usage["calls"] == 1 and usage["failed_calls"] == 1
    assert "boom" in usage["recent"][0]["error"]


def test_cost_estimate_uses_configured_prices(client, auth_headers, fake_llm, monkeypatch):
    monkeypatch.setenv("LLM_PRICE_IN_PER_1M", "1000000")  # $1 per token, to make the maths obvious
    monkeypatch.setenv("LLM_PRICE_OUT_PER_1M", "2000000")
    fake_llm.reply = '[{"title":"a","category":"Work","priority":"High"}]'
    client.post("/checkin/morning", json=["a"], headers=auth_headers)
    assert client.get("/usage/llm", headers=auth_headers).json()["estimated_cost_usd"] == 11 * 1 + 7 * 2


def test_usage_is_private_to_each_user(client, fake_llm):
    alice = register(client, "alice@example.com")
    bob = register(client, "bob@example.com")
    fake_llm.reply = '[{"title":"a","category":"Work","priority":"High"}]'
    client.post("/checkin/morning", json=["a"], headers=alice)
    assert client.get("/usage/llm", headers=bob).json()["calls"] == 0
