import datetime
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, List, Literal, Optional

from dotenv import load_dotenv

load_dotenv()  # load .env before any module reads configuration

from fastapi import Body, Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

import auth
import models
import weekly
from agent.graph import run_productivity_agent
from database import Base, engine, get_db
from pdf_report import build_weekly_pdf
from scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("auraflow.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)  # creates any missing tables (incl. cache, usage, reports)
    app.state.scheduler = start_scheduler()
    yield
    if app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)


app = FastAPI(title="AuraFlow AI API", lifespan=lifespan)

# Origins are configurable. Default allows any origin but without cookies/credentials.
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request / response schemas (validation happens here, before any logic runs) ---

class UserSignUp(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:  # bcrypt silently/loudly breaks past 72 bytes
            raise ValueError("password must be at most 72 bytes")
        return value


class Token(BaseModel):
    access_token: str
    token_type: str


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = Field(default="General", max_length=30)
    priority: Literal["High", "Medium", "Low"] = "Medium"
    due_date: Optional[datetime.datetime] = None


class TaskResponse(BaseModel):
    id: int
    user_id: int
    title: str
    category: str
    priority: str
    due_date: Optional[datetime.datetime]
    is_completed: bool
    completed_at: Optional[datetime.datetime]
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# --- System ---

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow(),
        "scheduler_running": bool(getattr(app.state, "scheduler", None)),
    }


# --- 1. Authentication ---

@app.post("/auth/signup", status_code=status.HTTP_201_CREATED, tags=["Auth"])
def signup(user_data: UserSignUp, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(email=user_data.email, hashed_password=auth.hash_password(user_data.password))
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully", "user_id": new_user.id}


@app.post("/auth/login", response_model=Token, tags=["Auth"])
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": auth.create_access_token(data={"sub": user.email}), "token_type": "bearer"}


# --- 2. Tasks (every query is scoped to the logged-in user) ---

@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["Tasks"])
def create_task(
    task: TaskCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    new_task = models.Task(
        user_id=current_user.id,
        title=task.title,
        category=task.category,
        priority=task.priority,
        due_date=task.due_date,
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task


@app.get("/tasks", response_model=List[TaskResponse], tags=["Tasks"])
def get_tasks(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Task).filter(models.Task.user_id == current_user.id).all()


@app.patch("/tasks/{task_id}", response_model=TaskResponse, tags=["Tasks"])
def complete_task(
    task_id: int,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == current_user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_completed = True
    task.completed_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(task)
    return task


@app.get("/tasks/overdue", response_model=List[TaskResponse], tags=["Tasks"])
def get_overdue_tasks(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Task).filter(
        models.Task.user_id == current_user.id,
        models.Task.is_completed == False,  # noqa: E712
        models.Task.due_date < datetime.datetime.utcnow(),
    ).all()


# --- 3. Agent check-ins ---

RawTask = Annotated[str, StringConstraints(max_length=300)]


@app.post("/checkin/morning", tags=["Agent"])
def morning_checkin(
    tasks_raw: Annotated[List[RawTask], Body(max_length=50)],
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    formatted_tasks = [
        {"title": task.strip(), "due_date": datetime.datetime.utcnow().isoformat()}
        for task in tasks_raw
        if task.strip()
    ]
    agent_results = run_productivity_agent(user_id=current_user.id, trigger="morning", tasks_raw=formatted_tasks)

    for item in agent_results.get("classified_tasks", []):
        db.add(
            models.Task(
                user_id=current_user.id,
                title=item.get("title"),
                category=item.get("category", "General"),
                priority=item.get("priority", "Medium"),
            )
        )
    db.commit()

    return {
        "status": "Morning checkin complete",
        "classified_tasks": agent_results.get("classified_tasks"),
        "overdue_tasks": agent_results.get("overdue_tasks"),
    }


@app.post("/checkin/evening", tags=["Agent"])
def evening_checkin(
    completed_ids: Annotated[List[int], Body(max_length=200)],
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    # Only the caller's own tasks can be completed (the query is user-scoped).
    for task_id in completed_ids:
        task = db.query(models.Task).filter(models.Task.id == task_id, models.Task.user_id == current_user.id).first()
        if task:
            task.is_completed = True
            task.completed_at = datetime.datetime.utcnow()
    db.commit()

    try:
        agent_results = run_productivity_agent(
            user_id=current_user.id, trigger="evening", completed_task_ids=completed_ids
        )
        summary_text = agent_results.get("eod_summary") or "Great work finishing your objectives today!"
        tomorrow_plan_json = json.dumps(agent_results.get("tomorrow_plan", []))
    except Exception:
        log.exception("evening agent run failed")
        summary_text = "Progress saved. The AI summary is temporarily unavailable."
        tomorrow_plan_json = json.dumps([])

    today = datetime.date.today()
    db_summary = db.query(models.EodSummary).filter(
        models.EodSummary.user_id == current_user.id,
        func.date(models.EodSummary.created_at) == today,
    ).first()
    if not db_summary:
        db.add(models.EodSummary(user_id=current_user.id, summary_text=summary_text, tomorrow_plan=tomorrow_plan_json))
    else:
        db_summary.summary_text = summary_text
        db_summary.tomorrow_plan = tomorrow_plan_json
    db.commit()

    return {
        "status": "Evening checkin complete",
        "eod_summary": summary_text,
        "tomorrow_plan": json.loads(tomorrow_plan_json),
    }


@app.get("/checkin/weekly", tags=["Agent"])
def get_weekly_summary(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Pattern insight for the last 7 days. LLM result is cached; `cached` says whether it was reused."""
    stats = weekly.collect_week_data(db, current_user.id)
    if not stats["total"] and not stats["daily_summaries"]:
        return {
            "weekly_insight": "No daily reflections recorded in the past 7 days to evaluate habits. Keep checking in daily!",
            "cached": False,
            "source": "none",
        }
    insight, cached, source = weekly.weekly_insight(db, current_user.id, stats)
    return {"weekly_insight": insight, "cached": cached, "source": source}


@app.get("/checkin/weekly_history", tags=["Agent"])
def get_weekly_history_timeline(
    current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)
):
    """The last 7 days of tasks, so the frontend can render completed and open work side by side."""
    since = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    tasks = (
        db.query(models.Task)
        .filter(models.Task.user_id == current_user.id, models.Task.created_at >= since)
        .order_by(models.Task.created_at.desc())
        .all()
    )
    return [
        {
            "id": t.id,
            "title": t.title,
            "category": t.category,
            "priority": t.priority,
            "is_completed": t.is_completed,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


# --- 4. Reports (stored by the weekly cron job; also generated on demand) ---

def _report_dict(report: models.WeeklyReport) -> dict:
    return {
        "week_start": report.week_start.isoformat(),
        "insight": report.insight,
        "insight_source": report.insight_source,
        "stats": json.loads(report.stats_json),
        "generated_at": report.created_at.isoformat(),
    }


@app.post("/reports/weekly/run", tags=["Reports"])
def run_weekly_report(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Generate or refresh this week's report now. The cron job does the same for every user on Sundays."""
    return _report_dict(weekly.generate_report(db, current_user.id, force=True))


@app.get("/reports/weekly", tags=["Reports"])
def get_latest_weekly_report(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    report = (
        db.query(models.WeeklyReport)
        .filter(models.WeeklyReport.user_id == current_user.id)
        .order_by(desc(models.WeeklyReport.week_start))
        .first()
    )
    if not report:
        raise HTTPException(status_code=404, detail="No weekly report yet. POST /reports/weekly/run to create one.")
    return _report_dict(report)


@app.get("/reports/weekly/pdf", tags=["Reports"])
def get_weekly_report_pdf(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    report = weekly.generate_report(db, current_user.id)  # reuses this week's stored report if present
    pdf_bytes = build_weekly_pdf(
        email=current_user.email,
        week_start=report.week_start,
        stats=json.loads(report.stats_json),
        insight=report.insight,
        source=report.insight_source,
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="weekly-report-{report.week_start}.pdf"'},
    )


# --- 5. LLM cost log ---

@app.get("/usage/llm", tags=["Usage"])
def llm_usage(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    """Your LLM calls: tokens, estimated cost (0 on the free tier), latency, failures."""
    mine = models.LlmUsage.user_id == current_user.id
    calls, prompt_tokens, completion_tokens, cost = db.query(
        func.count(models.LlmUsage.id),
        func.coalesce(func.sum(models.LlmUsage.prompt_tokens), 0),
        func.coalesce(func.sum(models.LlmUsage.completion_tokens), 0),
        func.coalesce(func.sum(models.LlmUsage.cost_usd), 0.0),
    ).filter(mine).one()
    failed = db.query(func.count(models.LlmUsage.id)).filter(mine, models.LlmUsage.success == False).scalar()  # noqa: E712
    recent = db.query(models.LlmUsage).filter(mine).order_by(desc(models.LlmUsage.created_at)).limit(20).all()
    return {
        "calls": calls,
        "failed_calls": failed,
        "prompt_tokens": int(prompt_tokens),
        "completion_tokens": int(completion_tokens),
        "total_tokens": int(prompt_tokens) + int(completion_tokens),
        "estimated_cost_usd": round(float(cost), 6),
        "recent": [
            {
                "purpose": r.purpose,
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "latency_ms": r.latency_ms,
                "success": r.success,
                "error": r.error,
                "at": r.created_at.isoformat(),
            }
            for r in recent
        ],
    }
