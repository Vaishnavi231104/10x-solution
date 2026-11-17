"""Render the weekly report as a PDF (concept: reporting)."""
import datetime
from typing import Dict

from fpdf import FPDF


# Typographic characters models like to emit, mapped to plain ASCII so they don't become "?".
_PUNCTUATION = str.maketrans(
    {
        "‐": "-", "‑": "-", "–": "-", "—": "-",
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "…": "...", " ": " ", " ": " ",
    }
)


def _t(value) -> str:
    # The model often replies in markdown; the PDF is plain text, so drop the bold markers.
    text = str(value).replace("**", "").translate(_PUNCTUATION)
    # fpdf2's built-in fonts are Latin-1 only; replace anything else instead of crashing.
    return text.encode("latin-1", "replace").decode("latin-1")


def _heading(pdf: FPDF, text: str) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _t(text), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)


def _line(pdf: FPDF, text: str) -> None:
    pdf.multi_cell(0, 6, _t(text), new_x="LMARGIN", new_y="NEXT")


def build_weekly_pdf(*, email: str, week_start: datetime.date, stats: Dict, insight: str, source: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "AuraFlow Weekly Report", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    week_end = week_start + datetime.timedelta(days=6)
    _line(pdf, f"{email}  |  week of {week_start.isoformat()} to {week_end.isoformat()}")

    _heading(pdf, "At a glance")
    _line(pdf, f"Tasks created: {stats['total']}")
    _line(pdf, f"Tasks completed: {stats['completed']} ({stats['completion_rate']}%)")

    if stats["by_category"]:
        _heading(pdf, "By category (completed / total)")
        for cat, total in sorted(stats["by_category"].items(), key=lambda kv: -kv[1]):
            done = stats["completed_by_category"].get(cat, 0)
            _line(pdf, f"- {cat}: {done} / {total}")

    _heading(pdf, "Insight" + (" (AI-generated)" if source == "llm" else " (automatic summary, AI unavailable)"))
    _line(pdf, insight)

    if stats["daily_summaries"]:
        _heading(pdf, "Daily reflections")
        for day in stats["daily_summaries"]:
            _line(pdf, f"{day['date']}: {day['text']}")

    if stats["open_titles"]:
        _heading(pdf, "Still open")
        for title in stats["open_titles"]:
            _line(pdf, f"- {title}")

    return bytes(pdf.output())
