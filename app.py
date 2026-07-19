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

from flask import (
    Flask, render_template, request, redirect, url_for,
    g, send_file, jsonify,
)

import database as db
import card_generator as cards

app = Flask(__name__)
app.secret_key = os.environ.get("ONEMORETIME_SECRET_KEY", "dev-key-change-this")

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
    "I choose to nurture my mind, body, and soul with kindness and compassion.",
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
    db.init_db()
    app.run(debug=True)
