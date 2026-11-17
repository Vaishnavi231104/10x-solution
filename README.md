# AuraFlow AI: turn a messy morning brain-dump into a plan, and a week of check-ins into a report

AuraFlow is a small productivity backend (FastAPI) with a Streamlit front end. You type your tasks the way they
come out of your head; an LLM sorts them into categories and priorities. In the evening it writes a short recap
and plans tomorrow. Every week it spots your recurring patterns and produces a one-page PDF report, on a schedule,
without you doing anything.

**Problem:** keeping a to-do list is more work than the tasks themselves, so people stop, and then have no idea
where their week went.
**10x claim:** capturing and prioritising a day's tasks takes one sentence instead of manual sorting, and the
weekly review writes itself instead of taking 20 minutes of scrolling back.
**Non-goal:** no team features, calendars or notifications. One person, one list.

> Submission document: [`My 10x Solution - Vaishnavi Dwivedi.md`](./My%2010x%20Solution%20-%20Vaishnavi%20Dwivedi.md)

## The 7 concepts and where they live

All seven concepts from the brief are implemented, with no swaps.

| # | Concept | What it does here | Where in the code |
|---|---|---|---|
| 1 | API endpoints | REST API with validation and correct status codes (201, 400, 401, 404, 422) | [`backend/main.py`](backend/main.py) |
| 2 | Database | SQLAlchemy models; data survives restarts (SQLite by default, Postgres via `DATABASE_URL`) | [`backend/models.py`](backend/models.py), [`backend/database.py`](backend/database.py) |
| 3 | Authentication | Sign-up/login, bcrypt password hashes, JWT; every task query is scoped to the logged-in user | [`backend/auth.py`](backend/auth.py) |
| 4 | Cron / background job | APScheduler job refreshes every user's weekly report every Sunday 18:00 UTC | [`backend/scheduler.py`](backend/scheduler.py), [`backend/weekly.py`](backend/weekly.py) (`generate_all_reports`) |
| 5 | Reporting (PDF) | One-page weekly PDF: totals, categories, reflections, AI insight | [`backend/pdf_report.py`](backend/pdf_report.py), `GET /reports/weekly/pdf` |
| 6 | Caching | Weekly insight (an LLM call) is stored in the DB keyed by a hash of the week's data and reused until it changes or expires | [`backend/cache.py`](backend/cache.py), used in [`backend/weekly.py`](backend/weekly.py) |
| 7 | LLM integration | Groq-hosted model behind the check-in endpoints; replies are validated; every call is written to a cost log | [`backend/llm.py`](backend/llm.py), [`backend/agent/nodes.py`](backend/agent/nodes.py), `GET /usage/llm` |

Stretch item also done: a test suite ([`backend/tests/`](backend/tests)), 40 deterministic tests that run offline.

## Run it (clean machine, Python 3.10+)

One-time setup:

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate        macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then edit .env: set SECRET_KEY and GROQ_API_KEY (free key, see below)
python seed.py              # demo user + a week of demo data (no AI key needed for this step)
```

Then two commands, in two terminals:

```bash
# terminal 1, from backend/
uvicorn main:app --port 8000

# terminal 2, from frontend/
pip install -r requirements.txt
streamlit run app.py
```

API docs: <http://localhost:8000/docs>. App: <http://localhost:8501>.

- **SECRET_KEY:** `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **GROQ_API_KEY:** free at <https://console.groq.com/keys> (no credit card). Without it the app still runs; AI steps
  fall back to plain defaults.
- **Model:** set in `GROQ_MODEL`. Groq retires models, so if you get a "model not found" error, list the models your
  key can use (command in `.env.example`) and update it.
- The front end talks to `http://localhost:8000` unless you set `API_BASE_URL` (env var or Streamlit secret).

## 5-minute demo path

1. Run the setup and the two commands above. Open <http://localhost:8501>.
2. **Log in** as `demo@example.com` / `demo12345` (created by `seed.py`; a fake account).
3. **Start my day:** in the planning box type tasks separated by commas, e.g.
   `Email the client about the invoice, Go for a 5k run, Revise chapter 4 for the exam`, then click *Start my day*.
   The new tasks appear under **Today** with an AI-chosen category and priority, next to any overdue items.
4. **Evening check-in:** tick a couple of tasks in the **Today** list, open the *Evening check-in* expander and click
   *Run my EOD*. You get a short recap and a suggested plan for tomorrow.
5. **This week:** a day-by-day view of the seeded week.
6. **Pattern surfacer:** click *Pull weekly pattern analysis*. Click it again: it says it was served from cache
   (no second AI call).
7. **Weekly report:** click *Prepare weekly PDF report*, then *Download PDF*.
8. **Cost log:** open <http://localhost:8000/docs>, authorise with the demo login, run `GET /usage/llm` to see every
   AI call with tokens, latency and (estimated) cost.

The cron job runs by itself on Sundays. To see its work now, call `POST /reports/weekly/run` in the API docs; it runs
the same code for the logged-in user. Run `GET /health` to confirm `scheduler_running: true`.

## API at a glance

| Method and path | Purpose | Auth |
|---|---|---|
| `POST /auth/signup`, `POST /auth/login` | create account, get JWT | no |
| `GET/POST /tasks`, `PATCH /tasks/{id}`, `GET /tasks/overdue` | tasks (your own only) | yes |
| `POST /checkin/morning` | LLM sorts raw tasks into category and priority | yes |
| `POST /checkin/evening` | complete tasks, LLM recap and next-day plan | yes |
| `GET /checkin/weekly`, `GET /checkin/weekly_history` | weekly insight (cached), 7-day timeline | yes |
| `POST /reports/weekly/run`, `GET /reports/weekly`, `GET /reports/weekly/pdf` | build, read, download the weekly report | yes |
| `GET /usage/llm` | your LLM cost log | yes |
| `GET /health` | liveness + scheduler status | no |

## How the AI part is kept safe

- **Output is validated, not trusted.** The classifier must return one entry per task; titles always come from the
  user's own input, priority must be High/Medium/Low, category is length-capped. Anything else triggers a fallback.
- **Failures degrade instead of crashing.** If the model is down or replies with junk, tasks are saved as
  `General/Medium`, the recap becomes a plain count, and the weekly insight becomes a labelled automatic summary.
  Failed calls are logged too.
- **Cost log.** Every call records model, tokens, latency, success and an estimated cost. Prompts and keys are never
  stored. The free tier costs $0, so the estimate is 0 unless you set `LLM_PRICE_IN_PER_1M` / `LLM_PRICE_OUT_PER_1M`.
- **Input limits.** At most 50 tasks per check-in, 300 characters each.

## Tests

```bash
cd backend
pytest
```

40 tests, offline and deterministic (temporary database, fake LLM, no scheduler thread). They cover login and
protected routes, one user not seeing another's data, input validation, messy or failing AI output, the cost log,
cache hit/miss/expiry, PDF output (including non-Latin text), and the cron job (schedule, idempotency, one user's
failure not stopping the others).

## Honest limitations

- **One scheduler per API process.** Run a single API worker, or move the job to its own cron/worker service when
  scaling out.
- **Tables are created on startup** (`create_all`). `backend/alembic/` holds the original schema migrations; the
  cache, usage and report tables were added after and are not in a migration yet.
- **Token auth is basic:** 60-minute JWTs, no refresh tokens, no password reset.
- **The "weekly pattern" quality depends on the model** and on how much data you have; with no data it says so.
- **Not deployed from this repo.** It runs locally. (A deployment on a free tier is the next stretch item.)

## Future ideas

- Email the weekly PDF as well as downloading it.
- Move the scheduler to a separate worker; add an Alembic migration for the newer tables.
- Deploy API and UI on a free tier and record a short demo video.
