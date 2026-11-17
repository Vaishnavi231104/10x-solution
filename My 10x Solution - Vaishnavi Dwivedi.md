# My 10x Solution - Vaishnavi Dwivedi

**Project:** AuraFlow AI | **Repository:** this repo | **Track:** FlyRank Internship, Backend

## 1. What is the problem I am solving?

Most people who try to plan their day give up on it, because maintaining a to-do list takes almost as much effort
as doing the tasks. You have to write each task down, decide how important it is, remember what slipped from
yesterday, and later work out where your week actually went. After a few days the list is out of date, and a week
later you cannot say what you finished or which task you keep avoiding.

This affects anyone juggling work, study and personal tasks, such as students, freelancers and early-career
developers, who need a lightweight planning habit more than a heavy project-management tool.

**My 10x claim:** capturing and prioritising a day's tasks takes one typed sentence instead of manual sorting, and
the weekly review (which normally means scrolling back through notes for 20 minutes) is produced automatically as a
one-page PDF. For reference, the AI steps are quick: classifying a three-task brain-dump took about 0.7 seconds of
model time and the weekly pattern analysis about 1.8 seconds in my own run. *(I have not timed a manual baseline, so
I do not claim an exact multiple.)*

**Non-goal:** no teams, calendar sync or push notifications. It is one person with one list.

## 2. How did I implement it?

AuraFlow is a FastAPI backend with a Streamlit front end.

- **Morning:** you type your tasks in one box, separated by commas. The backend sends them to a language model
  (Llama/GPT-class models on Groq's free tier), which assigns each a category and a priority. The reply is
  **validated**: it must contain exactly one entry per task, your own wording is always kept, and priority must be
  High, Medium or Low. If the model fails or answers with junk, the tasks are still saved with safe defaults. The
  app also surfaces anything overdue from earlier days.
- **Evening:** you tick off what you finished. The model writes a short recap and suggests tomorrow's tasks.
- **Weekly:** a background job runs every Sunday at 18:00 UTC. For every user it gathers the week's tasks and
  reflections, asks the model for recurring patterns, stores a report, and the user can download it as a PDF. The
  pattern analysis is **cached**: if nothing changed, it is reused instead of paying for another model call.
- **Cost log:** every model call is written to a table with its purpose, tokens, latency, success and an estimated
  cost. On the free tier the cost is zero, but the token count is real.
- **Safety basics:** passwords are bcrypt-hashed, logins use signed JWT tokens, every query is limited to the
  logged-in user, secrets live only in environment variables, and inputs have size limits.

### The concepts I implemented (7 of 7, no swaps)

| Concept | Where |
|---|---|
| API endpoints (validation, correct status codes) | `backend/main.py` |
| Database (SQLAlchemy, survives restarts) | `backend/models.py`, `backend/database.py` |
| Authentication (bcrypt + JWT, protected routes) | `backend/auth.py` |
| Background / cron job (weekly reports, APScheduler) | `backend/scheduler.py`, `backend/weekly.py` |
| Reporting, PDF (weekly report) | `backend/pdf_report.py` |
| Caching (weekly insight stored and reused) | `backend/cache.py` |
| LLM integration (validated output, cost log) | `backend/llm.py`, `backend/agent/nodes.py` |

No swaps were used, so no swap justification is needed. I also wrote a test suite (40 offline tests) as a stretch item.

### How to run it

```bash
# one-time setup
cd backend
python -m venv .venv                 # then activate it (Windows: .venv\Scripts\activate)
pip install -r requirements.txt
cp .env.example .env                 # set SECRET_KEY and GROQ_API_KEY (free key from console.groq.com)
python seed.py                       # demo user: demo@example.com / demo12345, plus a week of demo data

# start (two terminals)
uvicorn main:app --port 8000         # from backend/
streamlit run app.py                 # from frontend/ (after: pip install -r requirements.txt)
```

Open http://localhost:8501 and log in with the demo account. The README has a 5-minute demo path. Run the tests
with `pytest` inside `backend/`.

### What I would do next

Email the PDF as well as downloading it, move the scheduler to its own worker, and deploy on a free tier.
