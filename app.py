"""
app.py
------
Flask app. Each route corresponds to one thing you can do in the UI:
log a category, claim a reward, edit settings, etc. Every route that
touches the database calls a function from database.py — the routes
themselves don't contain raw SQL, so it's easy to see the separation
between "web stuff" (this file) and "database stuff" (database.py).

There's no login. Every visitor gets a private space automatically, via
a "uid" cookie set on their first request — see load_user()/save_user_cookie()
below. Every database call is scoped to that user_id, so one visitor's
logs/rewards/categories/moods are invisible to every other visitor.

Run it with:  python app.py
Then open:    http://127.0.0.1:5000
"""

import os
import uuid
import random
import logging
from datetime import date
from urllib.parse import quote, quote_plus

from flask import (
    Flask, render_template, request, redirect, url_for,
    g, send_file, jsonify, flash,
)
from werkzeug.exceptions import HTTPException

import database as db
import card_generator as cards

app = Flask(__name__)
app.secret_key = os.environ.get("ONEMORETIME_SECRET_KEY", "dev-key-change-this")

# Runs at import time (not just under `python app.py`) so gunicorn/production
# deployments also get any new tables created safely — CREATE TABLE IF NOT
# EXISTS means this is a no-op for tables that already exist.
db.init_db()

# ---------------------------------------------------------------------------
# LOGGING — writes to app.log so you can see what happened if something
# breaks. This is the kind of thing that shows "production mindset" in
# an interview: you're not just hoping errors don't happen, you're
# capturing them.
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename="app.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("onemoretime")

# ---------------------------------------------------------------------------
# IDENTITY — no password, no signup. Every visitor gets a random UUID the
# first time they show up, stored in a long-lived cookie. Every route below
# uses g.user_id to scope its database calls, so this one cookie is the
# entire privacy boundary between visitors.
#
# OWNER_USER_ID + OWNER_KEY are a private way back into one specific
# person's data (the one who set OWNER_KEY) — visiting /me?key=<OWNER_KEY>
# logs the browser into that fixed user_id instead of getting a fresh
# random one. Nobody who doesn't know OWNER_KEY can reach it.
# ---------------------------------------------------------------------------
USER_COOKIE = "uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 400  # ~400 days (browsers cap cookie age around here anyway)

OWNER_USER_ID = os.environ.get("OWNER_USER_ID", "b5c49fda-0cfb-438e-9655-19b357762d93")
OWNER_KEY = os.environ.get("OWNER_KEY", "IkkZaCpK9Dx1DlvvVJx1zRrAK7zKzU08")


@app.before_request
def load_user():
    if request.path.startswith("/static") or request.path == "/me":
        return
    uid = request.cookies.get(USER_COOKIE)
    if uid:
        g.user_id = uid
        g.new_user = False
    else:
        g.user_id = str(uuid.uuid4())
        g.new_user = True
        db.ensure_user(g.user_id)


@app.after_request
def save_user_cookie(response):
    if getattr(g, "new_user", False):
        response.set_cookie(
            USER_COOKIE, g.user_id, max_age=COOKIE_MAX_AGE,
            httponly=True, samesite="Lax",
        )
    return response


@app.route("/me")
def me():
    """Emma's private door back into her own data, from any browser/device.
    Anyone else hitting this URL without the key just gets a 404."""
    if not OWNER_KEY or request.args.get("key") != OWNER_KEY:
        return render_template("error.html", error="not found"), 404
    db.ensure_user(OWNER_USER_ID)
    resp = redirect(url_for("tracker"))
    resp.set_cookie(
        USER_COOKIE, OWNER_USER_ID, max_age=COOKIE_MAX_AGE,
        httponly=True, samesite="Lax",
    )
    logger.info("Owner logged in via /me")
    return resp


# ---------------------------------------------------------------------------
# THEMES — 4 built-in packs plus a "custom" option where a visitor picks
# their own background color. Saved per-user in the database (not just a
# session cookie) so it's part of that visitor's private space.
# ---------------------------------------------------------------------------
THEMES = ["earth", "cottagecore", "dark-academia", "y2k"]


@app.route("/theme/<name>", methods=["POST"])
def set_theme(name):
    if name in THEMES:
        db.set_theme(g.user_id, name)
    return redirect(request.referrer or url_for("settings"))


@app.route("/theme/custom", methods=["POST"])
def set_custom_theme():
    hex_color = request.form.get("color", "").strip()
    if hex_color.startswith("#") and len(hex_color) in (4, 7):
        db.set_custom_theme(g.user_id, hex_color)
    return redirect(request.referrer or url_for("settings"))


AFFIRMATIONS = [
    "I am safe, calm, and confident when I speak.",
    "One thoughtful career move is enough for today.",
    "I embrace each day as an opportunity for growth and healing.",
    "You don't have to get it right. You just have to try one more time.",
]

STAGES = [
    (0, "Seedling", "🌱"),
    (20, "Sprouting", "🌿"),
    (45, "Budding", "🌷"),
    (75, "Blooming", "🌸"),
    (110, "Thriving", "🌳"),
]

SPEECH_SETS = {
    "Life + Family + School": [
        {"q": "How's everything going right now, if someone just asks casually?",
         "a": "Keep it short and true: 'Things are good — I'm job hunting and picking up coding, keeps me busy.'"},
        {"q": "Someone asks why you left the D.O. program.",
         "a": "'I realized partway through that my strengths and interests were pulling me toward tech, so I made the call to pivot while I still could.'"},
    ],
    "Career Direction": [
        {"q": "What are you looking for right now?",
         "a": "'I'm targeting frontend and product-adjacent roles — I like being the bridge between what users need and what gets built.'"},
        {"q": "Why the switch from healthcare to tech?",
         "a": "'My science background taught me precision and problem solving — I'm applying that to building things now instead of studying them.'"},
    ],
    "Networking + Conversation": [
        {"q": "You're at an event and don't know anyone. Opening line?",
         "a": "'Hi, I'm Emma — I just moved to San Diego. What brought you here tonight?'"},
        {"q": "Someone asks what you do.",
         "a": "'Right now I'm building my own apps and applying to frontend roles — self-taught, moving fast.'"},
    ],
    "Interviews": [
        {"q": "Tell me about yourself.",
         "a": "'I came from a life sciences background, taught myself to code, and now I build apps end to end.'"},
        {"q": "What's a challenge you've overcome recently?",
         "a": "'Relocating to San Diego and rebuilding my job search from scratch — I've applied structure and consistency to it.'"},
    ],
    "AI + Technical": [
        {"q": "How do you use AI tools in your work?",
         "a": "'I use Claude daily — for debugging, planning features, and pressure-testing my own code before I ship it.'"},
        {"q": "What's a project you've built?",
         "a": "Pick one — onemoretime, Outfit Archive, or Coding Learning Hub — and describe it in one sentence."},
    ],
    "Salary + Money + Loans": [
        {"q": "What are your salary expectations?",
         "a": "'Based on my research for this role and location, I'm targeting [your number].'"},
        {"q": "Are you open to relocating?",
         "a": "'Yes, I'm open to relocating for the right opportunity.'"},
    ],
    "Quick Recovery Phrases": [
        {"q": "You blank mid-sentence. What do you say?",
         "a": "'Let me back up for a second...' — then restate your last clear point and keep going."},
        {"q": "You stutter on a word. What now?",
         "a": "Nothing — just keep talking. A pause is okay. A stutter is okay. Communication is the goal."},
    ],
    "Confidence": [
        {"q": "Say one thing you're proud of this week, out loud, right now.",
         "a": "There's no sample for this one — just say it."},
        {"q": "Finish this out loud: 'I am safe, calm, and confident when I speak because...'",
         "a": "Whatever comes out is the right answer."},
    ],
}


# ---------------------------------------------------------------------------
# CAREER COPILOT — the new Today / Career Tools / Progress experience.
# Everything below this point is career-action specific; the tracker/stats/
# settings code above stays as-is so nothing breaks, it's just no longer
# linked from the main nav.
# ---------------------------------------------------------------------------

# One small career move at a time. Which one shows up on Today rotates by
# calendar day (deterministic, not random-per-refresh) so a visitor sees the
# same recommendation all day and a different one tomorrow.
TODAY_ACTIONS = [
    {
        "id": "intro-practice",
        "title": "Practice your 30-second introduction out loud",
        "description": "Say your intro like you're meeting someone new today. Out loud, not in your head — that's what makes it stick.",
        "action_type": "speech",
        "cta_label": "Start Walk and Speak",
        "cta_endpoint": "walk_and_speak",
    },
    {
        "id": "linkedin-message",
        "title": "Create one LinkedIn networking message",
        "description": "Pick one person you'd like to reach out to and let the message creator do the heavy lifting.",
        "action_type": "linkedin",
        "cta_label": "Open LinkedIn Message Creator",
        "cta_endpoint": "linkedin_tool",
    },
    {
        "id": "biotech-event",
        "title": "Search for one San Diego biotech event",
        "description": "Find one event worth showing up to. You don't have to go — just find it.",
        "action_type": "event",
        "cta_label": "Open Career Event Finder",
        "cta_endpoint": "events_tool",
    },
    {
        "id": "review-job",
        "title": "Review one job description",
        "description": "Read one posting closely. Notice what stands out, what's missing, what you'd want to tailor for.",
        "action_type": "job_review",
        "cta_label": "Open Career Tools",
        "cta_endpoint": "career_tools",
    },
    {
        "id": "explain-transition",
        "title": "Practice explaining your career transition",
        "description": "One clear, honest sentence about why you moved from medicine and science into tech.",
        "action_type": "speech",
        "cta_label": "Start Walk and Speak",
        "cta_endpoint": "walk_and_speak",
    },
    {
        "id": "follow-up-contact",
        "title": "Follow up with one professional contact",
        "description": "A short, low-pressure check-in message to someone already in your network.",
        "action_type": "networking",
        "cta_label": "Open LinkedIn Message Creator",
        "cta_endpoint": "linkedin_tool",
    },
]


def get_today_action():
    idx = date.today().toordinal() % len(TODAY_ACTIONS)
    return TODAY_ACTIONS[idx]


def get_tomorrow_action():
    idx = (date.today().toordinal() + 1) % len(TODAY_ACTIONS)
    return TODAY_ACTIONS[idx]


# Walk and Speak — the speech-practice feature, reused and repositioned
# with prompts focused on the career-transition story instead of general
# life/interview topics (that original set stays at SPEECH_SETS above).
WALK_AND_SPEAK_PROMPTS = [
    {"q": "Tell me about yourself.",
     "a": "‘I have a background in psychology and physiology, and I spent time in a cancer research program before starting a doctoral program. One semester in, I realized my strengths were pulling me toward building things, not studying them — so I taught myself to code and I've been building ever since.’"},
    {"q": "Explain your transition from medicine and science into technology.",
     "a": "‘I left a D.O./M.S. program after one semester because I recognized a pattern I needed to change, not push through. My science background gave me precision and patience with data — I'm applying that same rigor to building software now.’"},
    {"q": "Introduce yourself at a networking event.",
     "a": "‘Hi, I'm Emma — I'm in San Diego, transitioning from a science background into software. What brought you here tonight?’"},
    {"q": "Why are you interested in this company?",
     "a": "Pick one real reason — a product you use, a mission that matches your own, a problem you'd like to help solve — and say it in one sentence."},
    {"q": "Ask someone for career advice.",
     "a": "‘I'd love to hear how you got started in this field — do you have 15 minutes sometime for me to ask a few questions?’"},
    {"q": "Describe a project you built.",
     "a": "Pick one — onemoretime, Outfit Archive, or Coding Learning Hub — and describe what it does and why you built it, in two sentences."},
    {"q": "Recover confidently after a stutter.",
     "a": "Nothing dramatic — pause, breathe, and keep going. ‘Let me start that again’ is a complete, professional sentence."},
    {"q": "Explain a technical idea simply.",
     "a": "Pick something you understand well and explain it the way you'd explain it to a curious friend, not a computer science professor."},
]

WALK_AND_SPEAK_LOG_TITLE = "Practiced out loud with Walk and Speak"


# LinkedIn Message Creator — template-based, no external AI API.
LINKEDIN_PURPOSES = [
    "Met at an event",
    "Ask for career advice",
    "Recruiter outreach",
    "Follow up after connecting",
    "Thank someone",
    "Ask about an opportunity",
]


def generate_linkedin_message(purpose, name, company, detail):
    name = name.strip() or "there"
    company = company.strip()
    detail = detail.strip()
    company_part = f" at {company}" if company else ""

    if purpose == "Met at an event":
        met_part = f" at {detail}" if detail else ""
        return (f"Hi {name}, it was great meeting you{met_part}! "
                f"I'd love to stay connected here on LinkedIn — hope our paths cross again soon.")

    if purpose == "Ask for career advice":
        context = f"{detail} " if detail else ""
        return (f"Hi {name}, I've been following your work{company_part} and would really value your perspective. "
                f"{context}Would you be open to a quick 15-minute chat sometime? No pressure at all if you're busy.")

    if purpose == "Recruiter outreach":
        context = f"{detail} " if detail else ""
        return (f"Hi {name}, I saw you recruit for roles{company_part}. {context}"
                f"I'm currently exploring new opportunities and would love to learn more about what you're hiring for — "
                f"happy to share my background if that's helpful.")

    if purpose == "Follow up after connecting":
        context = f"{detail} " if detail else ""
        return (f"Hi {name}, thanks for connecting! {context}"
                f"Looking forward to staying in touch — let me know if there's ever a way I can be useful to you too.")

    if purpose == "Thank someone":
        for_part = f" for {detail}" if detail else ""
        return f"Hi {name}, I just wanted to say thank you{for_part}. It meant a lot, and I really appreciate you taking the time."

    if purpose == "Ask about an opportunity":
        role_part = f" for {detail}" if detail else ""
        return (f"Hi {name}, I noticed{company_part or ' your company'} might be hiring{role_part}. "
                f"I'm really interested and would love to learn more — is there someone I should connect with?")

    return f"Hi {name}, {detail}".strip()


# Career Event Finder — outbound search links only, no scraping, no paid API.
EVENT_INTEREST_OPTIONS = [
    "Biotechnology",
    "Life sciences",
    "Artificial intelligence",
    "Medical devices",
    "Product management",
    "Healthcare technology",
    "Women in technology",
]


def build_event_search_url(engine, query, location):
    combined = f"{query} events in {location}".strip()
    if engine == "google":
        return f"https://www.google.com/search?q={quote_plus(combined)}"
    if engine == "linkedin":
        return f"https://www.linkedin.com/search/results/events/?keywords={quote_plus(f'{query} {location}'.strip())}"
    if engine == "meetup":
        return f"https://www.meetup.com/find/?keywords={quote_plus(query)}&location={quote_plus(location)}"
    if engine == "eventbrite":
        # path segments, not a query string — "+" wouldn't decode as a space here, so use quote()
        return f"https://www.eventbrite.com/d/{quote(location)}/{quote(query)}/"
    return None


ACTION_TYPE_LABELS = {
    "speech": "Walk and Speak practice",
    "linkedin": "LinkedIn messages",
    "event": "Event searches",
    "job_review": "Job description reviews",
    "networking": "Networking follow-ups",
}

# Below this total, or whenever the top activity types are tied, there isn't
# enough of a lead to honestly call one "most consistent" — a tie between two
# single-action types shouldn't get named as if one clearly won.
MOMENTUM_MIN_ACTIONS = 3


def get_progress_insight(counts):
    total = sum(counts.values())
    if total == 0:
        return "Your first small career move will appear here."

    top_count = max(counts.values())
    leaders = [t for t, c in counts.items() if c == top_count]
    if total < MOMENTUM_MIN_ACTIONS or len(leaders) > 1:
        return "You are building momentum across multiple career activities."

    label = ACTION_TYPE_LABELS.get(leaders[0], leaders[0])
    return f"You've kept up with {label} the most. Keep it going."


def get_growth_stage(weekly_count):
    """Maps this week's career-action count to the small growth-stage
    graphic + label shown on Progress."""
    if weekly_count <= 0:
        return {"key": "seed", "label": "Your next step begins here."}
    if weekly_count == 1:
        return {"key": "sprout", "label": "Your first step is growing."}
    if weekly_count <= 3:
        return {"key": "leafy-stem", "label": "Your momentum is taking root."}
    if weekly_count <= 5:
        return {"key": "flower-bud", "label": "Your consistency is beginning to bloom."}
    return {"key": "open-flower", "label": "Your career garden is growing."}


def get_stage(total_pts):
    stage = STAGES[0]
    for min_pts, label, emoji in STAGES:
        if total_pts >= min_pts:
            stage = (min_pts, label, emoji)
    return stage


@app.context_processor
def inject_globals():
    """Runs before every template render — makes `theme`, `today_mood`,
    and `affirmation` available in every template automatically."""
    user_id = getattr(g, "user_id", None)
    if user_id is None:
        return {"theme": "earth", "custom_bg": None, "themes": THEMES,
                 "today_mood": None, "affirmation": random.choice(AFFIRMATIONS)}
    settings = db.get_user_settings(user_id)
    return {
        "theme": settings["theme"],
        "custom_bg": settings["custom_bg"],
        "themes": THEMES,
        "today_mood": db.get_today_mood(user_id),
        "affirmation": random.choice(AFFIRMATIONS),
    }


@app.errorhandler(HTTPException)
def handle_http_exception(e):
    """Werkzeug already built the correct response for this (404, 405,
    etc.) — HTTPException is itself a valid WSGI response, so returning it
    unchanged preserves its real status code instead of falling through
    to the catch-all 500 handler below."""
    return e


@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Unhandled error: {e}")
    return render_template("error.html", error=str(e)), 500


# ---------------------------------------------------------------------------
# COVER + ABOUT — the story pages a visitor sees before the tracker itself.
# ---------------------------------------------------------------------------

@app.route("/")
def cover():
    return render_template("cover.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/app")
def tracker():
    user_id = g.user_id
    categories = db.get_categories(user_id)
    counts = db.get_counts_by_category(user_id)
    total = db.get_total_points(user_id)
    streak = db.get_streak(user_id)
    rewards = db.get_rewards(user_id)
    _, stage_label, stage_emoji = get_stage(total)
    pct = min(100, round((min(total, 110) / 110) * 100))

    return render_template(
        "index.html",
        active_tab="tracker",
        categories=categories,
        counts=counts,
        total=total,
        streak=streak,
        rewards=rewards,
        stage_label=stage_label,
        stage_emoji=stage_emoji,
        pct=pct,
    )


@app.route("/log/<cat_id>", methods=["POST"])
def log_category(cat_id):
    categories = {c["id"]: c for c in db.get_categories(g.user_id)}
    if cat_id in categories:
        db.add_log(g.user_id, cat_id, categories[cat_id]["pts"])
        logger.info(f"Logged category: {cat_id}")
    return redirect(url_for("tracker"))


@app.route("/mood/<mood>", methods=["POST"])
def set_mood(mood):
    allowed = {"😩", "😐", "🙂", "✨"}
    if mood in allowed:
        db.set_today_mood(g.user_id, mood)
    return redirect(request.referrer or url_for("tracker"))


@app.route("/reward/add", methods=["POST"])
def add_reward():
    pts = request.form.get("pts", type=int)
    text = request.form.get("text", "").strip()
    if pts and text:
        db.add_reward(g.user_id, pts, text)
    return redirect(url_for("tracker"))


@app.route("/reward/claim/<int:reward_id>", methods=["POST"])
def claim_reward(reward_id):
    db.claim_reward(g.user_id, reward_id)
    return redirect(url_for("tracker"))


@app.route("/reward/delete/<int:reward_id>", methods=["POST"])
def delete_reward(reward_id):
    db.delete_reward(g.user_id, reward_id)
    return redirect(url_for("tracker"))


@app.route("/stats")
def stats():
    user_id = g.user_id
    weekly = db.get_weekly_totals(user_id)
    breakdown = db.get_category_breakdown(user_id)
    max_weekly = max([d["total"] for d in weekly], default=0) or 1
    total_breakdown = sum(row["total"] for row in breakdown) or 1

    return render_template(
        "index.html",
        active_tab="stats",
        weekly=weekly,
        max_weekly=max_weekly,
        breakdown=breakdown,
        total_breakdown=total_breakdown,
        streak=db.get_streak(user_id),
        total_logs=db.get_total_logs(user_id),
        active_days=db.get_active_days(user_id),
        categories=db.get_categories(user_id),
        rewards=db.get_rewards(user_id),
        total=db.get_total_points(user_id),
    )


@app.route("/settings")
def settings():
    user_id = g.user_id
    return render_template(
        "index.html",
        active_tab="settings",
        categories=db.get_categories(user_id),
        rewards=db.get_rewards(user_id),
        total=db.get_total_points(user_id),
    )


@app.route("/settings/category/<cat_id>", methods=["POST"])
def update_category(cat_id):
    name = request.form.get("name", "").strip()
    pts = request.form.get("pts", type=int)
    if name and pts:
        db.update_category(g.user_id, cat_id, name, pts)
    return redirect(url_for("settings"))


@app.route("/settings/category/add", methods=["POST"])
def add_category():
    emoji = request.form.get("emoji", "").strip() or "⭐"
    name = request.form.get("name", "").strip()
    pts = request.form.get("pts", type=int)
    if name and pts:
        db.add_custom_category(g.user_id, emoji, name, pts)
    return redirect(url_for("settings"))


@app.route("/settings/category/delete/<cat_id>", methods=["POST"])
def remove_category(cat_id):
    db.delete_category(g.user_id, cat_id)
    return redirect(url_for("settings"))


@app.route("/settings/reset", methods=["POST"])
def reset():
    db.reset_all(g.user_id)
    logger.info("Data reset by user")
    return redirect(url_for("tracker"))


@app.route("/speech")
def speech():
    category = random.choice(list(SPEECH_SETS.keys()))
    question = random.choice(SPEECH_SETS[category])
    return render_template("speech.html", category=category, question=question)


@app.route("/speech/done", methods=["POST"])
def speech_done():
    categories = {c["id"]: c for c in db.get_categories(g.user_id)}
    if "speech" in categories:
        db.add_log(g.user_id, "speech", categories["speech"]["pts"])
    return redirect(url_for("tracker"))


# ---------------------------------------------------------------------------
# TODAY — one recommended career action at a time, auto-logged on completion.
# ---------------------------------------------------------------------------

@app.route("/today")
def today():
    action = get_today_action()
    completed = db.has_completed_action_today(g.user_id, action["title"])
    return render_template("today.html", active_tab="today", action=action, completed=completed)


@app.route("/today/complete", methods=["POST"])
def today_complete():
    action = get_today_action()
    if not db.has_completed_action_today(g.user_id, action["title"]):
        db.log_career_action(g.user_id, action["action_type"], action["title"])
        logger.info(f"Career action completed: {action['title']}")
    return redirect(url_for("today"))


# ---------------------------------------------------------------------------
# CAREER TOOLS — the calm hub linking to each tool.
# ---------------------------------------------------------------------------

@app.route("/tools")
def career_tools():
    return render_template("tools.html", active_tab="tools")


# ---------------------------------------------------------------------------
# WALK AND SPEAK — speech practice, reused and repositioned with prompts
# focused on the career-transition story.
# ---------------------------------------------------------------------------

@app.route("/tools/speak")
def walk_and_speak():
    prompt = random.choice(WALK_AND_SPEAK_PROMPTS)
    return render_template("walk_and_speak.html", active_tab="tools", prompt=prompt)


@app.route("/tools/speak/done", methods=["POST"])
def walk_and_speak_done():
    db.log_career_action(g.user_id, "speech", WALK_AND_SPEAK_LOG_TITLE)
    flash("Logged — nice work saying that out loud.")
    return redirect(url_for("walk_and_speak"))


# ---------------------------------------------------------------------------
# LINKEDIN MESSAGE CREATOR — template-based, no external AI API.
# ---------------------------------------------------------------------------

@app.route("/tools/linkedin")
def linkedin_tool():
    return render_template("linkedin.html", active_tab="tools", purposes=LINKEDIN_PURPOSES, message=None, form={})


@app.route("/tools/linkedin/generate", methods=["POST"])
def linkedin_generate():
    purpose = request.form.get("purpose", "").strip()
    name = request.form.get("name", "").strip()
    company = request.form.get("company", "").strip()
    detail = request.form.get("detail", "").strip()
    form = {"purpose": purpose, "name": name, "company": company, "detail": detail}

    if purpose not in LINKEDIN_PURPOSES:
        return render_template("linkedin.html", active_tab="tools", purposes=LINKEDIN_PURPOSES, message=None, form=form)

    message = generate_linkedin_message(purpose, name, company, detail)
    db.save_linkedin_message(g.user_id, purpose, name, company, detail, message)
    db.log_career_action(g.user_id, "linkedin", f"LinkedIn message: {purpose}")
    return render_template("linkedin.html", active_tab="tools", purposes=LINKEDIN_PURPOSES, message=message, form=form)


# ---------------------------------------------------------------------------
# CAREER EVENT FINDER — saved location/interests + outbound search links.
# No scraping, no paid API: just building a search-engine URL.
# ---------------------------------------------------------------------------

@app.route("/tools/events")
def events_tool():
    prefs = db.get_event_preferences(g.user_id)
    return render_template("events.html", active_tab="tools", interest_options=EVENT_INTEREST_OPTIONS, prefs=prefs)


@app.route("/tools/events/save", methods=["POST"])
def events_save():
    location = request.form.get("location", "").strip() or db.DEFAULT_EVENT_LOCATION
    interests = request.form.getlist("interests")
    db.save_event_preferences(g.user_id, location, interests)
    flash("Saved your location and interests.")
    return redirect(url_for("events_tool"))


@app.route("/tools/events/go/<engine>")
def events_go(engine):
    prefs = db.get_event_preferences(g.user_id)
    location = prefs["location"] or db.DEFAULT_EVENT_LOCATION
    query = " ".join(prefs["interests"]) if prefs["interests"] else "career"
    url = build_event_search_url(engine, query, location)
    if url is None:
        return redirect(url_for("events_tool"))
    db.log_career_action(g.user_id, "event", f"Searched {engine.title()} for events")
    return redirect(url)


# ---------------------------------------------------------------------------
# PROGRESS — automatic career-action stats, no manual tracker entry.
# ---------------------------------------------------------------------------

@app.route("/progress")
def progress():
    user_id = g.user_id
    counts = db.get_career_action_counts_by_type(user_id)
    weekly_count = db.get_career_action_count_this_week(user_id)

    today_action = get_today_action()
    completed_today = db.has_completed_action_today(user_id, today_action["title"])
    next_action = get_tomorrow_action() if completed_today else today_action

    return render_template(
        "progress.html",
        active_tab="progress",
        weekly_count=weekly_count,
        speech_count=counts.get("speech", 0),
        linkedin_count=counts.get("linkedin", 0),
        event_count=counts.get("event", 0),
        progress_insight=get_progress_insight(counts),
        growth_stage=get_growth_stage(weekly_count),
        next_action=next_action,
        next_action_is_tomorrow=completed_today,
    )


# ---------------------------------------------------------------------------
# SHAREABLE CARDS — "wrapped" monthly recap + streak flex card.
# Both return a real PNG image, generated on the fly with Pillow.
# ---------------------------------------------------------------------------

@app.route("/card/wrapped")
def wrapped_card():
    summary = db.get_monthly_summary(g.user_id)
    month_name = date.today().strftime("%B")
    buf = cards.make_wrapped_card(
        total_logs=summary["total_logs"],
        total_pts=summary["total_pts"],
        top_category=summary["top_category"],
        month_name=month_name,
    )
    return send_file(buf, mimetype="image/png", download_name="onemoretime-wrapped.png")


@app.route("/card/streak")
def streak_card():
    buf = cards.make_streak_card(db.get_streak(g.user_id))
    return send_file(buf, mimetype="image/png", download_name="onemoretime-streak.png")


# ---------------------------------------------------------------------------
# JSON API — same data the web pages use, but as JSON. This is the kind of
# endpoint a future mobile app (or another script) could call directly
# instead of scraping HTML.
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def api_stats():
    user_id = g.user_id
    breakdown = [dict(row) for row in db.get_category_breakdown(user_id)]
    return jsonify({
        "total_points": db.get_total_points(user_id),
        "streak": db.get_streak(user_id),
        "total_logs": db.get_total_logs(user_id),
        "active_days": db.get_active_days(user_id),
        "weekly": db.get_weekly_totals(user_id),
        "breakdown": breakdown,
        "monthly_summary": db.get_monthly_summary(user_id),
    })


@app.route("/api/log/<cat_id>", methods=["POST"])
def api_log(cat_id):
    categories = {c["id"]: c for c in db.get_categories(g.user_id)}
    if cat_id not in categories:
        return jsonify({"error": "unknown category"}), 404
    db.add_log(g.user_id, cat_id, categories[cat_id]["pts"])
    return jsonify({"ok": True, "total_points": db.get_total_points(g.user_id)})


if __name__ == "__main__":
    app.run(debug=True)
