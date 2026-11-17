import os
import streamlit as st
import datetime
import requests
import json


def _api_base_url() -> str:
    """Backend URL: Streamlit secret, else the API_BASE_URL env var, else a local server."""
    try:
        return st.secrets["API_BASE_URL"]
    except Exception:
        return os.getenv("API_BASE_URL", "http://localhost:8000")


# Backend API Configuration URL
BASE_URL = _api_base_url().rstrip("/")

# Set global page configurations
st.set_page_config(
    page_title="Maven AI Workspace",
    page_icon="🌸",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 🌸 MAVEN BLOOM MARK (inline SVG — four-petal bloom, no lettering, no sparkle/star) ---
LOGO_SVG = """
<svg width="{size}" height="{size}" viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="mavenGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop class="mg-a" offset="0%" stop-color="#9b5de5"/>
      <stop class="mg-b" offset="50%" stop-color="#f15bb5"/>
      <stop class="mg-c" offset="100%" stop-color="#2ec4b6"/>
    </linearGradient>
    <style>
      @keyframes mgShiftA {{ 0%,100% {{ stop-color:#9b5de5; }} 50% {{ stop-color:#2ec4b6; }} }}
      @keyframes mgShiftB {{ 0%,100% {{ stop-color:#f15bb5; }} 50% {{ stop-color:#9b5de5; }} }}
      @keyframes mgShiftC {{ 0%,100% {{ stop-color:#2ec4b6; }} 50% {{ stop-color:#f15bb5; }} }}
      .mg-a {{ animation: mgShiftA 6s ease-in-out infinite; }}
      .mg-b {{ animation: mgShiftB 6s ease-in-out infinite; }}
      .mg-c {{ animation: mgShiftC 6s ease-in-out infinite; }}
    </style>
  </defs>
  <g fill="url(#mavenGrad)">
    <path d="M20 4 C24.5 10 24.5 14 20 20 C15.5 14 15.5 10 20 4 Z"/>
    <path d="M36 20 C30 24.5 26 24.5 20 20 C26 15.5 30 15.5 36 20 Z"/>
    <path d="M20 36 C15.5 30 15.5 26 20 20 C24.5 26 24.5 30 20 36 Z"/>
    <path d="M4 20 C9.5 15.5 13.5 15.5 20 20 C13.5 24.5 9.5 24.5 4 20 Z"/>
  </g>
</svg>
"""

def logo(size=40):
    return LOGO_SVG.format(size=size)

# --- 🌿 GLOBAL FAIRY-GARDEN DESIGN SYSTEM ---
# Fonts, palette, and reusable component classes that apply everywhere
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,600;1,9..144,500;1,9..144,600&family=Quicksand:wght@400;500;600;700&display=swap');

    :root {
        --fae-pink: #ffc9de;
        --fae-blush: #ffd6e8;
        --fae-lilac: #d9c2f0;
        --fae-violet: #b083e0;
        --fae-mint: #b8e8d4;
        --fae-sage: #9fd8b8;
        --fae-gold: #ffe4a3;
        --fae-plum: #3d2a52;
        --fae-ink: #4a3763;
    }

    html, body, [class*="css"] { font-family: 'Quicksand', sans-serif; }

    h1, h2, h3, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Fraunces', serif !important;
        font-style: italic;
        font-weight: 600 !important;
        background: linear-gradient(120deg, var(--fae-violet), #e08fc0, var(--fae-sage));
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        letter-spacing: 0.3px;
    }

    /* Drifting bokeh blooms in the background, for a gentle sense of motion */
    [data-testid="stAppViewContainer"]::before {
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        z-index: 0;
        background:
            radial-gradient(38rem 30rem at 8% 12%, rgba(255, 201, 222, 0.35), transparent 60%),
            radial-gradient(32rem 28rem at 92% 20%, rgba(184, 232, 212, 0.30), transparent 60%),
            radial-gradient(40rem 34rem at 50% 95%, rgba(217, 194, 240, 0.30), transparent 60%);
        animation: faeDrift 22s ease-in-out infinite alternate;
    }
    @keyframes faeDrift {
        0%   { transform: translate3d(0, 0, 0) scale(1); }
        100% { transform: translate3d(1.5%, -1.5%, 0) scale(1.05); }
    }

    /* Slim gradient scrollbar for a lively, "dynamic scrolling" feel */
    ::-webkit-scrollbar { width: 10px; height: 10px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, var(--fae-pink), var(--fae-violet));
        border-radius: 999px;
    }
    ::-webkit-scrollbar-thumb:hover { background: linear-gradient(180deg, #ffb3d3, #9a5fd1); }

    section[data-testid="stSidebar"] {
        background: linear-gradient(165deg, #fbeaf3 0%, #efe3fa 55%, #e6f4ec 100%) !important;
        border-right: 1px solid rgba(176, 131, 224, 0.25);
    }
    section[data-testid="stSidebar"] * { color: var(--fae-plum) !important; }

    .stButton>button, .stFormSubmitButton>button {
        border-radius: 999px !important;
        border: none !important;
        font-family: 'Quicksand', sans-serif;
        font-weight: 700 !important;
        letter-spacing: 0.2px;
        padding: 0.55rem 1.4rem !important;
    }

    div[data-testid="stProgress"] > div > div > div {
        background: linear-gradient(90deg, var(--fae-pink), var(--fae-violet), var(--fae-sage)) !important;
        border-radius: 999px;
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 20px !important;
        backdrop-filter: blur(6px);
        border: 1px solid var(--card-border, rgba(176, 131, 224, 0.25)) !important;
        background: var(--card-bg, rgba(255,255,255,0.55)) !important;
    }

    [data-testid="stExpander"] {
        border-radius: 16px !important;
        border: 1px solid var(--card-border, rgba(176, 131, 224, 0.25)) !important;
        background: var(--card-bg, rgba(255,255,255,0.45)) !important;
        overflow: hidden;
    }

    /* --- Reusable dashboard components --- */
    .card-eyebrow {
        font-size: 0.72rem; font-weight: 700; letter-spacing: 1.2px;
        text-transform: uppercase; color: var(--fae-violet); margin-bottom: 6px;
    }

    .hero-card {
        border-radius: 26px; padding: 34px 36px; margin: 6px 0 18px 0;
        background: var(--hero-bg); position: relative; overflow: hidden;
        box-shadow: 0 10px 30px rgba(90, 50, 110, 0.15);
    }
    .hero-eyebrow { font-size: 0.75rem; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; color: var(--hero-eyebrow); }
    .hero-title {
        font-family: 'Fraunces', serif; font-style: italic; font-weight: 600;
        font-size: 2.4rem; color: var(--hero-title); margin: 6px 0 4px 0; line-height: 1.15;
    }
    .hero-subtitle { color: var(--hero-subtitle); font-size: 1.05rem; }

    .streak-badge {
        display: inline-flex; align-items: center; gap: 10px;
        background: var(--card-bg); border: 1px solid var(--card-border);
        border-radius: 999px; padding: 10px 20px 10px 10px;
        margin: -20px 0 22px 26px; position: relative; z-index: 1;
        box-shadow: 0 6px 18px rgba(90, 50, 110, 0.12);
    }
    .streak-icon {
        display: inline-flex; align-items: center; justify-content: center;
        width: 30px; height: 30px; border-radius: 50%;
        background: linear-gradient(135deg, var(--fae-gold), #f7b95c);
        color: #7a4a00; font-size: 0.95rem;
    }
    .streak-num { font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.2rem; color: var(--text-color); }
    .streak-label { color: var(--text-color); opacity: 0.75; }

    .task-card {
        display: flex; align-items: center; justify-content: space-between; gap: 14px;
        background: var(--task-bg); border-radius: 16px; padding: 14px 18px;
        margin-bottom: 10px; min-height: 30px; border: 1px solid transparent;
    }
    .task-card.task-overdue { background: var(--task-overdue-bg); border-color: rgba(214, 140, 40, 0.25); }
    .task-card.task-done { background: var(--task-done-bg); }
    .task-title { font-weight: 700; color: var(--text-color); }
    .task-sub { font-size: 0.82rem; margin-top: 2px; color: var(--text-color); opacity: 0.65; }
    .task-card.task-overdue .task-sub { color: #b5711a; opacity: 1; font-weight: 600; }

    .cat-pill {
        font-size: 0.68rem; font-weight: 700; letter-spacing: 0.4px;
        padding: 5px 11px; border-radius: 999px; white-space: nowrap;
    }

    div[data-testid="column"]:has(> div > div[data-testid="stCheckbox"]) {
        display: flex; align-items: center; justify-content: center; padding-top: 4px;
    }

    .glass-card {
        background: var(--card-bg); border: 1px solid var(--card-border);
        border-radius: 20px; padding: 22px 24px; margin-bottom: 18px;
        box-shadow: 0 6px 20px rgba(80, 40, 90, 0.08); backdrop-filter: blur(8px);
    }
    .eod-title { font-family: 'Fraunces', serif; font-style: italic; font-weight: 600; font-size: 1.5rem; color: var(--text-color); margin-bottom: 6px; }
    .eod-text { color: var(--text-color); opacity: 0.85; font-style: italic; line-height: 1.6; }

    .stat-tile {
        border-radius: 18px; padding: 20px 22px; text-align: left;
        box-shadow: 0 6px 18px rgba(90, 50, 110, 0.08);
    }
    .stat-label { font-size: 0.82rem; color: var(--text-color); opacity: 0.75; margin-bottom: 4px; }
    .stat-value { font-family: 'Fraunces', serif; font-weight: 600; font-size: 2rem; color: var(--text-color); }

    .week-card {
        border-radius: 18px; padding: 18px 22px; margin-bottom: 12px;
        box-shadow: 0 6px 16px rgba(90, 50, 110, 0.08);
    }
    .week-title { font-family: 'Fraunces', serif; font-weight: 600; font-size: 1.3rem; color: var(--text-color); margin: 2px 0; }
    .week-caption { color: var(--text-color); opacity: 0.65; font-size: 0.85rem; }
    </style>
""", unsafe_allow_html=True)

# --- Small formatting / data helpers ---
def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None

def _fmt_time(s):
    dt = _parse_dt(s)
    if not dt:
        return ""
    return dt.strftime("%I:%M %p").lstrip("0").lower()

def _fmt_date(s):
    dt = _parse_dt(s)
    return dt.strftime("%b %d") if dt else ""

def _is_overdue(due_str):
    dt = _parse_dt(due_str)
    return dt is not None and dt.date() < datetime.date.today()

def compute_streak(tasks):
    done_dates = set()
    for t in tasks:
        if t.get("is_completed") and t.get("completed_at"):
            dt = _parse_dt(t["completed_at"])
            if dt:
                done_dates.add(dt.date())
    streak = 0
    day = datetime.date.today()
    if day not in done_dates:
        day -= datetime.timedelta(days=1)
    while day in done_dates:
        streak += 1
        day -= datetime.timedelta(days=1)
    return streak

CATEGORY_STYLES = {
    "work": ("#e9dcfb", "#6b3fa0"),
    "personal": ("#ffd9ea", "#a83e73"),
    "health": ("#d3f3df", "#2f7a4f"),
    "learning": ("#fdecc2", "#8a6414"),
    "study": ("#fdecc2", "#8a6414"),
    "urgent": ("#ffd6d6", "#b23b3b"),
    "general": ("#e7e7f5", "#5a5a7a"),
    "task": ("#e7e7f5", "#5a5a7a"),
}

def category_pill(cat):
    label = (cat or "Task").strip()
    bg, fg = CATEGORY_STYLES.get(label.lower(), CATEGORY_STYLES["general"])
    return f'<span class="cat-pill" style="background:{bg};color:{fg};">▪ {label.upper()}</span>'

def render_task_card(task):
    title = task["title"]
    is_done = task.get("is_completed", False)
    due = task.get("due_date")
    status_class = ""
    if is_done:
        time_str = _fmt_time(task.get("completed_at"))
        subtitle = f"Done at {time_str}" if time_str else "Done"
        status_class = "task-done"
    elif _is_overdue(due):
        subtitle = f"Overdue · was due {_fmt_date(due)}"
        status_class = "task-overdue"
    else:
        subtitle = "Due today"
    title_html = f'<span style="text-decoration:line-through;opacity:0.55;">{title}</span>' if is_done else title
    return f"""
    <div class="task-card {status_class}">
        <div class="task-main">
            <div class="task-title">{title_html}</div>
            <div class="task-sub">{subtitle}</div>
        </div>
        {category_pill(task.get('category'))}
    </div>
    """

# --- 🔒 PART 1: PERSISTENT STATE TRACKING ---
# Keeping these declared globally stops the page from kicking you back to login on state change
if "token" not in st.session_state:
    st.session_state.token = None
if "user_email" not in st.session_state:
    st.session_state.user_email = None
if "last_eod_summary" not in st.session_state:
    st.session_state.last_eod_summary = None
if "last_tomorrow_plan" not in st.session_state:
    st.session_state.last_tomorrow_plan = None
if "moonlit_mode" not in st.session_state:
    _hr = datetime.datetime.now().hour
    st.session_state.moonlit_mode = _hr >= 17 or _hr < 6


# --- PART 2: AUTHENTICATION INTERFACE MASK ---
if st.session_state.token is None:
    # Moonlit-grove backdrop for the entry gate — plain diagonal, no shifting animation
    st.html("""
        <style>
        [data-testid="stAppViewContainer"] {
            background: linear-gradient(135deg, #241a38 0%, #34274d 50%, #1c3529 100%) !important;
        }
        div[data-testid="stRadio"] label, div[data-testid="stRadio"] p,
        div[data-testid="stTextInput"] label { color: #f3ecfb !important; font-weight: 600; }
        .stButton>button {
            background: linear-gradient(135deg, #e0a8f0 0%, #7a5fd1 100%) !important;
            color: white !important;
            box-shadow: 0 4px 16px rgba(155, 93, 229, 0.4);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(155, 93, 229, 0.55);
        }
        .maven-gate-title {
            font-family: 'Fraunces', serif !important; font-style: italic; font-weight: 600 !important;
            font-size: 2.6rem; text-align: center; margin-bottom: 0;
            background: none !important;
            color: #ffffff !important; -webkit-text-fill-color: #ffffff !important;
            text-shadow: 0 2px 6px rgba(45, 15, 60, 0.45), 0 10px 26px rgba(45, 15, 60, 0.3);
            animation: mavenTitleGlow 3.2s ease-in-out infinite;
        }
        @keyframes mavenTitleGlow {
            0%, 100% { filter: brightness(1); }
            50% { filter: brightness(1.2); }
        }
        .maven-gate-subtitle {
            text-align: center; font-style: italic; color: rgba(255,255,255,0.92) !important;
            text-shadow: 0 1px 10px rgba(60, 20, 70, 0.35); font-weight: 500;
        }
        </style>
    """)

    left, mid, right = st.columns([1, 1.3, 1])
    with mid:
        st.markdown(
            f'<div style="text-align:center;margin-top:2.5rem;">{logo(60)}</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            '<h1 class="maven-gate-title">Welcome to Maven</h1>'
            '<p class="maven-gate-subtitle">Your Intelligent Productivity Agent</p>',
            unsafe_allow_html=True
        )
        st.write("")

        with st.container(border=True):
            auth_mode = st.radio("Choose Access Route", ["Log In", "Sign Up"], horizontal=True)
            email = st.text_input("Email Address")
            password = st.text_input("Password", type="password")

            if auth_mode == "Log In":
                if st.button("Log In", use_container_width=True):
                    if email and password:
                        login_payload = {"username": email, "password": password}
                        res = requests.post(f"{BASE_URL}/auth/login", data=login_payload)

                        if res.status_code == 200:
                            st.session_state.token = res.json()["access_token"]
                            st.session_state.user_email = email
                            st.success("🎉 Session verified successfully!")
                            import time
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("Access denied. Invalid credentials mapped.")
                    else:
                        st.warning("Please input complete login details.")

            else:  # Sign Up Pipeline
                if st.button("Provision New Account Profile", use_container_width=True):
                    if email and password:
                        with st.spinner("Registering database account profile records..."):
                            res = requests.post(f"{BASE_URL}/auth/signup", json={"email": email, "password": password})

                            if res.status_code in [200, 201]:
                                st.success("✨ Profile generated! Switch to Log In mode to authorize.")
                            else:
                                st.error("Registration rejected. User profile might already exist.")
                    else:
                        st.warning("Please fill out registration text parameters.")

else:
    # --- PART 3: DYNAMIC WORKSPACE INTERFACE ---
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    display_name = st.session_state.user_email.split("@")[0].replace(".", " ").replace("_", " ").title()

    # --- Sidebar: logo, moonlit toggle, profile, logout ---
    with st.sidebar:
        st.markdown(
            f'<div style="text-align:center;padding:4px 0 10px;">{logo(38)}'
            f'<div style="font-family:\'Fraunces\',serif;font-style:italic;font-weight:600;'
            f'font-size:1.25rem;margin-top:4px;background:linear-gradient(120deg,#b083e0,#e08fc0,#9fd8b8);'
            f'-webkit-background-clip:text;-webkit-text-fill-color:transparent;">Maven</div></div>',
            unsafe_allow_html=True
        )
        st.toggle("Moonlit mode", key="moonlit_mode")
        st.divider()
        st.markdown(f"**{display_name}**")
        st.caption(st.session_state.user_email)
        st.divider()
        if st.button("Log out", use_container_width=True):
            st.session_state.token = None
            st.session_state.user_email = None
            st.session_state.last_eod_summary = None
            st.session_state.last_tomorrow_plan = None
            st.rerun()

    moonlit = st.session_state.moonlit_mode

    # --- Theme variables: moonlit (dark garden) vs day (dewy meadow) ---
    if moonlit:
        bg_gradient = "linear-gradient(150deg, #241a38 0%, #34274d 45%, #1c3529 100%)"
        text_color = "#f3ecfb"
        card_bg = "rgba(255, 255, 255, 0.07)"
        card_border = "rgba(255, 255, 255, 0.14)"
        hero_bg = "linear-gradient(135deg, #3a2a55 0%, #4a3468 55%, #24402f 100%)"
        hero_eyebrow, hero_title, hero_subtitle = "#c9a6e8", "#f7eefe", "#e3a8d6"
        task_bg, task_overdue_bg, task_done_bg = "rgba(255,255,255,0.06)", "rgba(214,140,40,0.18)", "rgba(159,216,184,0.10)"
        button_gradient = "linear-gradient(135deg, #e0a8f0 0%, #7a5fd1 100%)"
        button_shadow = "rgba(224, 168, 240, 0.35)"
        stat_bg_1, stat_bg_2 = "rgba(247,169,198,0.16)", "rgba(159,216,184,0.16)"
        week_palette = ["rgba(240,169,198,0.14)", "rgba(159,216,184,0.14)", "rgba(255,228,163,0.14)", "rgba(217,194,240,0.14)"]
    else:
        bg_gradient = "linear-gradient(150deg, #ffe3ee 0%, #efe1fb 45%, #dff5ea 100%)"
        text_color = "#3d2a52"
        card_bg = "rgba(255, 255, 255, 0.6)"
        card_border = "rgba(176, 131, 224, 0.25)"
        hero_bg = "linear-gradient(135deg, rgba(199,164,232,0.9) 0%, rgba(232,163,201,0.85) 55%, rgba(170,224,196,0.85) 100%)"
        hero_eyebrow, hero_title, hero_subtitle = "#7c4fa8", "#3d2a52", "#a24d7c"
        task_bg, task_overdue_bg, task_done_bg = "rgba(255,255,255,0.55)", "rgba(255,196,120,0.28)", "rgba(159,216,184,0.22)"
        button_gradient = "linear-gradient(135deg, #f7a8c6 0%, #b083e0 100%)"
        button_shadow = "rgba(176, 131, 224, 0.35)"
        stat_bg_1, stat_bg_2 = "rgba(255,196,222,0.55)", "rgba(184,232,212,0.55)"
        week_palette = ["rgba(255,196,222,0.5)", "rgba(184,232,212,0.5)", "rgba(255,228,163,0.5)", "rgba(217,194,240,0.5)"]

    st.markdown(f"""
        <style>
            :root {{
                --card-bg: {card_bg}; --card-border: {card_border}; --text-color: {text_color};
                --hero-bg: {hero_bg}; --hero-eyebrow: {hero_eyebrow}; --hero-title: {hero_title}; --hero-subtitle: {hero_subtitle};
                --task-bg: {task_bg}; --task-overdue-bg: {task_overdue_bg}; --task-done-bg: {task_done_bg};
            }}
            [data-testid="stAppViewContainer"] {{ background: {bg_gradient} !important; transition: background 1s ease-in-out; }}
            [data-testid="stAppViewContainer"]::before {{ opacity: 0.6; }}
            .stMarkdown, p, label {{ color: {text_color} !important; }}
            .stButton>button {{
                background: {button_gradient}; color: white !important; border: none !important;
                font-weight: 700; transition: all 0.2s ease; box-shadow: 0 4px 14px {button_shadow};
            }}
            .stButton>button:hover {{ transform: translateY(-2px); box-shadow: 0 6px 18px {button_shadow}; }}
        </style>
    """, unsafe_allow_html=True)

    # --- Fetch tasks once, reused across the whole page ---
    response = requests.get(f"{BASE_URL}/tasks", headers=headers)
    all_tasks = response.json() if response.status_code == 200 else []
    active_tasks = [t for t in all_tasks if not t.get("is_completed", False)]
    completed_count = len(all_tasks) - len(active_tasks)
    streak = compute_streak(all_tasks)

    # --- Hero greeting card ---
    now = datetime.datetime.now()
    if now.hour < 12:
        eyebrow, greeting, subtitle = "MORNING CHECK-IN", "Good morning", "let's make today lovely"
    elif now.hour < 17:
        eyebrow, greeting, subtitle = "AFTERNOON CHECK-IN", "Good afternoon", "let's keep the momentum going"
    else:
        eyebrow, greeting, subtitle = "EVENING CHECK-IN", "Good evening", "let's see how today went, gently"

    st.markdown(f"""
        <div class="hero-card">
            <div class="hero-eyebrow">{eyebrow}</div>
            <div class="hero-title">{greeting}, {display_name}</div>
            <div class="hero-subtitle">{subtitle}</div>
        </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
        <div class="streak-badge">
            <span class="streak-icon">✦</span>
            <span class="streak-num">{streak}</span>
            <span class="streak-label">days in bloom</span>
        </div>
    """, unsafe_allow_html=True)

    # --- Morning planning card ---
    with st.container(border=True):
        st.markdown('<div class="card-eyebrow">WHAT ARE YOU PLANNING TODAY?</div>', unsafe_allow_html=True)
        raw_input = st.text_area(
            "What are you planning today",
            placeholder="e.g., video lectures, final report, read chapter...",
            height=110,
            label_visibility="collapsed",
        )
        if st.button("✦ Start my day", use_container_width=False):
            if raw_input:
                tasks_list = [line.strip() for line in raw_input.split(",") if line.strip()]
                with st.spinner("LangGraph engine mapping today's workflows..."):
                    try:
                        res = requests.post(
                            f"{BASE_URL}/checkin/morning",
                            json=tasks_list,
                            headers=headers,
                            timeout=60,
                        )
                        if res.ok:
                            st.success("Your intentions are planted for today!")
                            st.rerun()
                        else:
                            try:
                                detail = res.json().get("detail", res.text)
                            except ValueError:
                                detail = res.text
                            st.error(f"Morning pipeline failed (HTTP {res.status_code}): {detail}")
                    except requests.RequestException as exc:
                        st.error(f"Could not reach the backend API at {BASE_URL}: {exc}")
            else:
                st.warning("Tell me at least one thing you're planning today!")

    # --- Today task list ---
    st.markdown("## Today")
    today_str = datetime.date.today().isoformat()
    today_tasks = [
        t for t in all_tasks
        if not t.get("is_completed") or (t.get("completed_at") and t["completed_at"][:10] == today_str)
    ]
    today_tasks.sort(key=lambda t: (
        0 if (not t.get("is_completed") and _is_overdue(t.get("due_date"))) else
        1 if not t.get("is_completed") else 2,
        t["id"]
    ))

    completed_ids = []
    if not today_tasks:
        st.markdown(
            '<div class="glass-card">🎉 All clear! No outstanding tasks for today — run your morning check-in to add some.</div>',
            unsafe_allow_html=True
        )
    else:
        for task in today_tasks:
            box_col, card_col = st.columns([0.06, 0.94])
            with box_col:
                is_done = task.get("is_completed", False)
                checked = st.checkbox(
                    "mark done", key=f"chk_{task['id']}", value=is_done,
                    disabled=is_done, label_visibility="collapsed"
                )
            with card_col:
                st.markdown(render_task_card(task), unsafe_allow_html=True)
            if checked and not is_done:
                completed_ids.append(task["id"])

    with st.expander("Evening check-in — mark what you finished"):
        st.caption("Tick off what you completed above, then run your evening summary.")
        if st.button("✦ Run my EOD"):
            if not completed_ids:
                st.warning("Please tick at least one completed task first!")
            else:
                with st.spinner("Reflecting on today's flow..."):
                    res = requests.post(f"{BASE_URL}/checkin/evening", json=completed_ids, headers=headers)
                    if res.status_code == 200:
                        data = res.json()
                        st.session_state.last_eod_summary = data.get("eod_summary")
                        st.session_state.last_tomorrow_plan = data.get("tomorrow_plan")
                        st.rerun()
                    else:
                        st.error("Could not process the evening check-in.")

    # --- EOD summary card ---
    if st.session_state.last_eod_summary:
        weekday_name = datetime.date.today().strftime("%A")
        st.markdown(f"""
            <div class="glass-card">
                <div class="card-eyebrow">YOUR EOD SUMMARY</div>
                <div class="eod-title">A gentle {weekday_name}</div>
                <div class="eod-text">{st.session_state.last_eod_summary}</div>
            </div>
        """, unsafe_allow_html=True)

        today_total = len([t for t in all_tasks if t.get("created_at", "")[:10] == today_str])
        today_done = len([t for t in all_tasks if t.get("completed_at", "")[:10] == today_str])
        s1, s2 = st.columns(2)
        with s1:
            st.markdown(f"""
                <div class="stat-tile" style="background:{stat_bg_1};">
                    <div class="stat-label">Done today</div>
                    <div class="stat-value">{today_done} / {today_total}</div>
                </div>
            """, unsafe_allow_html=True)
        with s2:
            st.markdown(f"""
                <div class="stat-tile" style="background:{stat_bg_2};">
                    <div class="stat-label">Streak</div>
                    <div class="stat-value">{streak} days</div>
                </div>
            """, unsafe_allow_html=True)

        if st.session_state.last_tomorrow_plan:
            with st.expander("Tomorrow's strategy roadmap"):
                st.json(st.session_state.last_tomorrow_plan)

    # --- This week ---
    st.markdown("## This week")
    if not all_tasks:
        st.markdown('<div class="glass-card">No recorded milestones yet this week.</div>', unsafe_allow_html=True)
    else:
        grouped_days = {}
        for t in all_tasks:
            date_str = t.get("created_at", "")[:10] if t.get("created_at") else today_str
            grouped_days.setdefault(date_str, []).append(t)

        sorted_days = sorted(grouped_days.keys(), reverse=True)[:5]
        for idx, day_key in enumerate(sorted_days):
            day_tasks = grouped_days[day_key]
            done_n = sum(1 for t in day_tasks if t.get("is_completed"))
            try:
                weekday_label = datetime.date.fromisoformat(day_key).strftime("%A").upper()
            except ValueError:
                weekday_label = day_key
            grad = week_palette[idx % len(week_palette)]
            st.markdown(f"""
                <div class="week-card" style="background:{grad};">
                    <div class="card-eyebrow">{weekday_label}</div>
                    <div class="week-title">{done_n} task{'s' if done_n != 1 else ''} done</div>
                    <div class="week-caption">Your day, gently summarised.</div>
                </div>
            """, unsafe_allow_html=True)

    # --- Pattern surfacer ---
    st.markdown("## Pattern surfacer")
    with st.container(border=True):
        st.caption("Surfaces recurring habits from your last 7 days of check-ins.")
        if st.button("🔍 Pull weekly pattern analysis"):
            with st.spinner("Reading through the last week of reflections..."):
                res = requests.get(f"{BASE_URL}/checkin/weekly", headers=headers)
                if res.status_code == 200:
                    review_data = res.json()
                    st.info(review_data.get("weekly_insight", "No recurring patterns recorded this cycle."))
                    if review_data.get("source") == "fallback":
                        st.caption("The AI was unavailable, so this is an automatic summary of your numbers.")
                    elif review_data.get("cached"):
                        st.caption("Served from cache: nothing changed since the last analysis.")
                else:
                    st.error("Could not complete the weekly reflection pull.")

    # --- Weekly PDF report ---
    st.markdown("## Weekly report")
    with st.container(border=True):
        st.caption("A one-page PDF of this week: totals, categories, reflections and the insight above.")
        if st.button("📄 Prepare weekly PDF report"):
            with st.spinner("Building your report..."):
                pdf_res = requests.get(f"{BASE_URL}/reports/weekly/pdf", headers=headers)
                if pdf_res.status_code == 200:
                    st.session_state["weekly_pdf"] = pdf_res.content
                else:
                    st.error("Could not build the weekly PDF report.")
        if st.session_state.get("weekly_pdf"):
            st.download_button(
                "⬇️ Download PDF",
                data=st.session_state["weekly_pdf"],
                file_name="weekly-report.pdf",
                mime="application/pdf",
            )
