import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text, Date, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    # 🔗 FIX: Add the missing tasks link so the endpoints can filter by user scope securely!
    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")
    
    # Ensure your summaries relationship is also linked cleanly
    summaries = relationship("EodSummary", back_populates="owner", cascade="all, delete-orphan")




class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String, nullable=False)
    category = Column(String, default="Task")
    priority = Column(String, default="Normal")
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # 🔗 FIX: Add this missing date column property for the agent's overdue calculations
    due_date = Column(DateTime, default=datetime.datetime.utcnow, nullable=True)
    
    owner = relationship("User", back_populates="tasks")

class DailyLog(Base):
    __tablename__ = "daily_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    checkin_type = Column(String, nullable=False)  # "morning" or "evening"
    raw_payload = Column(String, nullable=False)   # JSON string of tasks
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class EodSummary(Base):
    __tablename__ = "eod_summaries"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    summary_text = Column(String, nullable=False)
    tomorrow_plan = Column(String, nullable=True)  
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="summaries")


class LlmUsage(Base):
    """One row per LLM call: the cost log. Never stores prompts or keys."""
    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    purpose = Column(String, nullable=False)       # e.g. "classify_tasks", "weekly_insight"
    model = Column(String, nullable=False)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    cost_usd = Column(Float, default=0.0)          # estimate; 0.0 on the free tier
    latency_ms = Column(Integer, default=0)
    success = Column(Boolean, default=True)
    error = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class LlmCache(Base):
    """Stored results of expensive LLM calls, reused until they expire."""
    __tablename__ = "llm_cache"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    hits = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class WeeklyReport(Base):
    """One stored weekly report per user per week (written by the scheduled job)."""
    __tablename__ = "weekly_reports"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_weekly_report_user_week"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start = Column(Date, nullable=False)
    insight = Column(Text, nullable=False)
    insight_source = Column(String, default="llm")  # "llm" or "fallback"
    stats_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# 🌌 Add these new schemas right at the bottom:
from pydantic import BaseModel
from typing import List, Optional

class TaskUpdate(BaseModel):
    id: int
    status: str  # Will accept "Pending", "Completed", "In Progress", "Blocked"
    notes: Optional[str] = None

class EveningCheckinRequest(BaseModel):
    tasks: List[TaskUpdate]