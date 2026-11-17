"""Create demo data so a stranger can see the app working without typing anything.

    python seed.py            # create the demo user + a week of tasks and reflections
    python seed.py --reset    # delete the demo user's data first, then re-create it

Demo login:  demo@example.com / demo12345   (a fake account, safe to publish)
No AI key is needed: the data is inserted directly.
"""
import argparse
import datetime
import json

from dotenv import load_dotenv

load_dotenv()

import auth  # noqa: E402
import models  # noqa: E402
from database import Base, SessionLocal, engine  # noqa: E402

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "demo12345"

# (title, category, priority, days_ago, completed)
TASKS = [
    ("Finish API documentation", "Work", "High", 6, True),
    ("Review pull request", "Work", "Medium", 6, True),
    ("Gym: leg day", "Health", "Medium", 5, True),
    ("Study for database exam", "Study", "High", 5, False),
    ("Prepare sprint demo", "Work", "High", 4, True),
    ("Call dentist", "Personal", "Low", 4, False),
    ("Meal prep for the week", "Health", "Low", 3, True),
    ("Write unit tests", "Work", "High", 3, True),
    ("Study for database exam", "Study", "High", 2, False),
    ("Fix login bug", "Work", "High", 2, True),
    ("Pay electricity bill", "Personal", "Medium", 1, True),
    ("Study for database exam", "Study", "High", 1, False),
    ("Plan next sprint", "Work", "Medium", 0, False),
    ("Evening walk", "Health", "Low", 0, True),
]

REFLECTIONS = [
    (5, "Solid start: documentation and review done. Studying slipped, so give it a fixed slot tomorrow."),
    (3, "Strong work day with tests and the sprint demo wrapped up. Keep protecting your mornings."),
    (1, "Bills and the login bug are done. The exam prep is the one thing that keeps being pushed back."),
]


def seed(reset: bool = False) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == DEMO_EMAIL).first()
        if user and reset:
            db.delete(user)  # cascades to tasks and summaries
            db.commit()
            user = None
        if user:
            print(f"Demo user already exists ({DEMO_EMAIL}). Use --reset to recreate.")
            return

        user = models.User(email=DEMO_EMAIL, hashed_password=auth.hash_password(DEMO_PASSWORD))
        db.add(user)
        db.commit()
        db.refresh(user)

        now = datetime.datetime.utcnow()
        for title, category, priority, days_ago, completed in TASKS:
            created = now - datetime.timedelta(days=days_ago, hours=1)
            db.add(
                models.Task(
                    user_id=user.id,
                    title=title,
                    category=category,
                    priority=priority,
                    created_at=created,
                    due_date=created + datetime.timedelta(hours=8),
                    is_completed=completed,
                    completed_at=created + datetime.timedelta(hours=4) if completed else None,
                )
            )
        for days_ago, text in REFLECTIONS:
            db.add(
                models.EodSummary(
                    user_id=user.id,
                    summary_text=text,
                    tomorrow_plan=json.dumps(["Finish the open exam prep", "Plan the next sprint"]),
                    created_at=now - datetime.timedelta(days=days_ago),
                )
            )
        db.commit()
        print(f"Seeded {len(TASKS)} tasks and {len(REFLECTIONS)} reflections.")
        print(f"Log in with  {DEMO_EMAIL} / {DEMO_PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the demo user's data and re-create it")
    seed(parser.parse_args().reset)
