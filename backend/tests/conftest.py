"""Test setup. Everything is deterministic and offline: temp database, no scheduler, fake LLM."""
import os
import tempfile
from types import SimpleNamespace

# Configure the environment BEFORE the app modules are imported.
_tmp = tempfile.mkdtemp(prefix="auraflow-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_tmp, 'test.db')}"
os.environ["DISABLE_SCHEDULER"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["GROQ_API_KEY"] = "test-key-never-used"
os.environ.pop("LLM_PRICE_IN_PER_1M", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import llm  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402


class FakeLLM:
    """Stands in for the Groq client. Set `.reply` to a string, a callable(prompt), or an Exception."""

    def __init__(self):
        self.calls = 0
        self.reply = "ok"
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, temperature):
        self.calls += 1
        reply = self.reply
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(messages[0]["content"])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7),
        )


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def fake_llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(llm, "_get_client", lambda: fake)
    return fake


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def register(client: TestClient, email: str = "a@example.com", password: str = "password123") -> dict:
    """Sign up + log in, return auth headers."""
    assert client.post("/auth/signup", json={"email": email, "password": password}).status_code == 201
    token = client.post("/auth/login", data={"username": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers(client):
    return register(client)
