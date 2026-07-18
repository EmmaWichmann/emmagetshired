"""
app.py
------
Flask app. Each route corresponds to one thing you can do in the UI:
log a category, claim a reward, edit settings, etc. Every route that
touches the database calls a function from database.py — the routes
themselves don't contain raw SQL, so it's easy to see the separation
between "web stuff" (this file) and "database stuff" (database.py).

Run it with:  python app.py
Then open:    http://127.0.0.1:5000
"""

import os
import random
import logging
from functools import wraps
from datetime import date

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, send_file, jsonify,
)

import database as db
import card_generator as cards

app = Flask(__name__)
app.secret_key = os.environ.get("BLOOM_SECRET_KEY", "dev-key-change-this")

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
logger = logging.getLogger("bloom")

# ---------------------------------------------------------------------------
# AUTH — simple password gate. Not enterprise-grade, but it demonstrates
# the pattern: a login route, a session cookie, and a decorator that
# protects every other route.
# ---------------------------------------------------------------------------
APP_PASSWORD = os.environ.get("BLOOM_PASSWORD", "bloom2026")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["logged_in"] = True
            logger.info("Successful login")
            return redirect(url_for("tracker"))
        error = "wrong password, try again"
        logger.warning("Failed login attempt")
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# THEMES — a small set of alt color palettes, stored in the session so
# they persist across pages without needing a database column.
# ---------------------------------------------------------------------------
THEMES = ["earth", "cottagecore", "dark-academia", "y2k"]


@app.route("/theme/<name>", methods=["POST"])
@login_required
def set_theme(name):
    if name in THEMES:
        session["theme"] = name
    return redirect(request.referrer or url_for("settings"))


AFFIRMATIONS = [
    "I am safe, calm, and confident when I speak.",
    "I choose to nurture my mind, body, and soul with kindness and compassion.",
    "I embrace each day as an opportunity for growth and healing.",
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
         "a": "Pick one — bloom, Outfit Archive, or Coding Learning Hub — and describe it in one sentence."},
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
    return {
        "theme": session.get("theme", "earth"),
        "themes": THEMES,
        "today_mood": db.get_today_mood(),
        "affirmation": random.choice(AFFIRMATIONS),
    }


@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f"Unhandled error: {e}")
    return render_template("error.html", error=str(e)), 500


@app.route("/")
@login_required
def tracker():
    categories = db.get_categories()
    counts = db.get_counts_by_category()
    total = db.get_total_points()
    streak = db.get_streak()
    rewards = db.get_rewards()
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
@login_required
def log_category(cat_id):
    categories = {c["id"]: c for c in db.get_categories()}
    if cat_id in categories:
        db.add_log(cat_id, categories[cat_id]["pts"])
        logger.info(f"Logged category: {cat_id}")
    return redirect(url_for("tracker"))


@app.route("/mood/<mood>", methods=["POST"])
@login_required
def set_mood(mood):
    allowed = {"😩", "😐", "🙂", "✨"}
    if mood in allowed:
        db.set_today_mood(mood)
    return redirect(request.referrer or url_for("tracker"))


@app.route("/reward/add", methods=["POST"])
@login_required
def add_reward():
    pts = request.form.get("pts", type=int)
    text = request.form.get("text", "").strip()
    if pts and text:
        db.add_reward(pts, text)
    return redirect(url_for("tracker"))


@app.route("/reward/claim/<int:reward_id>", methods=["POST"])
@login_required
def claim_reward(reward_id):
    db.claim_reward(reward_id)
    return redirect(url_for("tracker"))


@app.route("/reward/delete/<int:reward_id>", methods=["POST"])
@login_required
def delete_reward(reward_id):
    db.delete_reward(reward_id)
    return redirect(url_for("tracker"))


@app.route("/stats")
@login_required
def stats():
    weekly = db.get_weekly_totals()
    breakdown = db.get_category_breakdown()
    max_weekly = max([d["total"] for d in weekly], default=0) or 1
    total_breakdown = sum(row["total"] for row in breakdown) or 1

    return render_template(
        "index.html",
        active_tab="stats",
        weekly=weekly,
        max_weekly=max_weekly,
        breakdown=breakdown,
        total_breakdown=total_breakdown,
        streak=db.get_streak(),
        total_logs=db.get_total_logs(),
        active_days=db.get_active_days(),
        categories=db.get_categories(),
        rewards=db.get_rewards(),
        total=db.get_total_points(),
    )


@app.route("/settings")
@login_required
def settings():
    return render_template(
        "index.html",
        active_tab="settings",
        categories=db.get_categories(),
        rewards=db.get_rewards(),
        total=db.get_total_points(),
    )


@app.route("/settings/category/<cat_id>", methods=["POST"])
@login_required
def update_category(cat_id):
    name = request.form.get("name", "").strip()
    pts = request.form.get("pts", type=int)
    if name and pts:
        db.update_category(cat_id, name, pts)
    return redirect(url_for("settings"))


@app.route("/settings/reset", methods=["POST"])
@login_required
def reset():
    db.reset_all()
    logger.info("Data reset by user")
    return redirect(url_for("tracker"))


@app.route("/speech")
@login_required
def speech():
    category = random.choice(list(SPEECH_SETS.keys()))
    question = random.choice(SPEECH_SETS[category])
    return render_template("speech.html", category=category, question=question)


@app.route("/speech/done", methods=["POST"])
@login_required
def speech_done():
    categories = {c["id"]: c for c in db.get_categories()}
    if "speech" in categories:
        db.add_log("speech", categories["speech"]["pts"])
    return redirect(url_for("tracker"))


# ---------------------------------------------------------------------------
# SHAREABLE CARDS — "bloom wrapped" monthly recap + streak flex card.
# Both return a real PNG image, generated on the fly with Pillow.
# ---------------------------------------------------------------------------

@app.route("/card/wrapped")
@login_required
def wrapped_card():
    summary = db.get_monthly_summary()
    month_name = date.today().strftime("%B")
    buf = cards.make_wrapped_card(
        total_logs=summary["total_logs"],
        total_pts=summary["total_pts"],
        top_category=summary["top_category"],
        month_name=month_name,
    )
    return send_file(buf, mimetype="image/png", download_name="bloom-wrapped.png")


@app.route("/card/streak")
@login_required
def streak_card():
    buf = cards.make_streak_card(db.get_streak())
    return send_file(buf, mimetype="image/png", download_name="bloom-streak.png")


# ---------------------------------------------------------------------------
# JSON API — same data the web pages use, but as JSON. This is the kind of
# endpoint a future mobile app (or another script) could call directly
# instead of scraping HTML.
# ---------------------------------------------------------------------------

@app.route("/api/stats")
@login_required
def api_stats():
    breakdown = [dict(row) for row in db.get_category_breakdown()]
    return jsonify({
        "total_points": db.get_total_points(),
        "streak": db.get_streak(),
        "total_logs": db.get_total_logs(),
        "active_days": db.get_active_days(),
        "weekly": db.get_weekly_totals(),
        "breakdown": breakdown,
        "monthly_summary": db.get_monthly_summary(),
    })


@app.route("/api/log/<cat_id>", methods=["POST"])
@login_required
def api_log(cat_id):
    categories = {c["id"]: c for c in db.get_categories()}
    if cat_id not in categories:
        return jsonify({"error": "unknown category"}), 404
    db.add_log(cat_id, categories[cat_id]["pts"])
    return jsonify({"ok": True, "total_points": db.get_total_points()})


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True)
