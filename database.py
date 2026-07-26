"""
database.py
-----------
Every SQL query the app uses lives in this one file, written out in plain
SQL (no ORM) on purpose — the whole point of this rebuild is to practice SQL.
Each function below is a small, readable example of a real SQL pattern.

Multi-user note: every table has a user_id column, and every query that
reads or writes app data is filtered/scoped by user_id. There's no login —
each visitor's user_id comes from a browser cookie (see app.py), and every
function here just takes that user_id as its first argument.
"""

import sqlite3
from datetime import date, timedelta

DB_PATH = "onemoretime.db"

# Palette used to auto-color custom categories a visitor creates, so they
# fit the earth-tone design system without asking the visitor to pick one.
CUSTOM_COLORS = ["#8B5A3A", "#6B7C5A", "#C4847A", "#C9A84C", "#5C3D2E", "#7A6A8C", "#5C7A8A"]


def get_db():
    """Open a connection. row_factory lets us access columns by name,
    e.g. row['name'] instead of row[2] — much easier to read."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Creates the tables this app needs, if they don't already exist. This
    only sets up the shared schema — no data is seeded here, because there
    are no "the" categories/rewards anymore, only each user's own. Each
    visitor gets seeded individually the first time they show up, via
    ensure_user() below.

    user_settings -> one row per visitor: their theme choice
    categories    -> the things a visitor can log (defaults + their own)
    logs          -> one row per time a visitor logs something
    rewards       -> the real-life treats a visitor unlocks with points
    moods         -> one row per visitor per day they checked in
    """
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id   TEXT PRIMARY KEY,
        theme     TEXT NOT NULL DEFAULT 'earth',
        custom_bg TEXT
    );

    CREATE TABLE IF NOT EXISTS categories (
        user_id TEXT NOT NULL,
        id      TEXT NOT NULL,
        emoji   TEXT NOT NULL,
        name    TEXT NOT NULL,
        sub     TEXT,
        pts     INTEGER NOT NULL DEFAULT 1,
        color   TEXT,
        custom  INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, id)
    );

    CREATE TABLE IF NOT EXISTS logs (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id  TEXT NOT NULL,
        cat_id   TEXT NOT NULL,
        pts      INTEGER NOT NULL,
        log_date TEXT NOT NULL,
        FOREIGN KEY (user_id, cat_id) REFERENCES categories(user_id, id)
    );

    CREATE TABLE IF NOT EXISTS rewards (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        pts     INTEGER NOT NULL,
        text    TEXT NOT NULL,
        claimed INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS moods (
        user_id  TEXT NOT NULL,
        log_date TEXT NOT NULL,
        mood     TEXT NOT NULL,
        PRIMARY KEY (user_id, log_date)
    );

    CREATE TABLE IF NOT EXISTS career_actions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    TEXT NOT NULL,
        action_type TEXT NOT NULL,
        title      TEXT NOT NULL,
        log_date   TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS event_preferences (
        user_id   TEXT PRIMARY KEY,
        location  TEXT NOT NULL DEFAULT 'San Diego, California',
        interests TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS linkedin_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     TEXT NOT NULL,
        purpose     TEXT NOT NULL,
        person_name TEXT,
        company     TEXT,
        detail      TEXT,
        message     TEXT NOT NULL,
        log_date    TEXT NOT NULL
    );
    """)
    conn.commit()
    conn.close()


DEFAULT_CATEGORIES = [
    ("job",         "💼", "Job search",        "1 application",           1, "#8B5A3A"),
    ("speech",      "🗣️", "Speech practice",   "1 min counts",            1, "#C4847A"),
    ("code",        "💻", "Coding practice",   "Coding Hub / certs",      1, "#6B7C5A"),
    ("up",          "🌤️", "Got up & moving",   "out of bed, outside",     1, "#C9A84C"),
    ("care",        "🧴", "Self-care",         "skincare, shower, etc",   1, "#5C3D2E"),
    ("water",       "💧", "Water",             "glasses of water today",  1, "#5C7A8A"),
    ("reading",     "📖", "Reading",           "even 10 minutes",         1, "#7A6A8C"),
    ("mindfulness", "🧘", "Mindfulness",       "meditation, breathing, journaling", 1, "#7C8F5E"),
    ("movement",    "🚶", "Movement",          "walk, stretch, workout",  1, "#B5793A"),
]

DEFAULT_REWARDS = [
    (5,  "☕ coffee treat"),
    (10, "📺 episode of a comfort show, guilt-free"),
    (15, "🛁 bath night + face mask"),
    (20, "💅 something small for yourself"),
    (30, "🛍️ a real treat-yourself purchase"),
    (50, "🌴 a full day off, no guilt, no catching up"),
]


def ensure_user(user_id):
    """Called the first time a user_id is seen (new cookie). Seeds their
    private categories, rewards, and settings — but only if they don't
    already have any, so this is safe to call repeatedly."""
    conn = get_db()

    conn.execute(
        "INSERT OR IGNORE INTO user_settings (user_id, theme) VALUES (?, 'earth')",
        (user_id,),
    )

    count = conn.execute(
        "SELECT COUNT(*) AS n FROM categories WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    if count == 0:
        conn.executemany(
            "INSERT INTO categories (user_id, id, emoji, name, sub, pts, color) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(user_id, *c) for c in DEFAULT_CATEGORIES],
        )

    reward_count = conn.execute(
        "SELECT COUNT(*) AS n FROM rewards WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    if reward_count == 0:
        conn.executemany(
            "INSERT INTO rewards (user_id, pts, text) VALUES (?, ?, ?)",
            [(user_id, *r) for r in DEFAULT_REWARDS],
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

def get_categories(user_id):
    """SELECT * — grab this user's categories, in the order they were created."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM categories WHERE user_id = ? ORDER BY rowid", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def update_category(user_id, cat_id, name, pts):
    """UPDATE with a WHERE clause — without WHERE this would update EVERY row.
    Filtering by user_id too means one visitor can never edit another's data."""
    conn = get_db()
    conn.execute(
        "UPDATE categories SET name = ?, pts = ? WHERE user_id = ? AND id = ?",
        (name, pts, user_id, cat_id),
    )
    conn.commit()
    conn.close()


def add_custom_category(user_id, emoji, name, pts):
    """Notion-style flexibility: any visitor can add their own category,
    not just edit the defaults. Auto-picks a color and a unique id."""
    import uuid
    cat_id = f"custom-{uuid.uuid4().hex[:8]}"
    conn = get_db()
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM categories WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    color = CUSTOM_COLORS[existing % len(CUSTOM_COLORS)]
    conn.execute(
        "INSERT INTO categories (user_id, id, emoji, name, sub, pts, color, custom) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
        (user_id, cat_id, emoji, name, "your own category", pts, color),
    )
    conn.commit()
    conn.close()
    return cat_id


def delete_category(user_id, cat_id):
    """Only custom categories can be deleted — the defaults always stay
    available. Also clears any logs against it so stats don't reference
    a category that no longer exists."""
    conn = get_db()
    conn.execute("DELETE FROM logs WHERE user_id = ? AND cat_id = ?", (user_id, cat_id))
    conn.execute(
        "DELETE FROM categories WHERE user_id = ? AND id = ? AND custom = 1",
        (user_id, cat_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# LOGS
# ---------------------------------------------------------------------------

def add_log(user_id, cat_id, pts):
    """INSERT a new row — this is how every 'log' button click gets saved."""
    conn = get_db()
    conn.execute(
        "INSERT INTO logs (user_id, cat_id, pts, log_date) VALUES (?, ?, ?, ?)",
        (user_id, cat_id, pts, date.today().isoformat()),
    )
    conn.commit()
    conn.close()


def get_total_points(user_id):
    """SUM() is an aggregate function — it collapses many rows into one number.
    COALESCE handles the case where there are zero logs (SUM would return NULL)."""
    conn = get_db()
    row = conn.execute(
        "SELECT COALESCE(SUM(pts), 0) AS total FROM logs WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row["total"]


def get_counts_by_category(user_id):
    """GROUP BY groups rows that share a value (here: cat_id) so aggregate
    functions run per-group instead of over the whole table."""
    conn = get_db()
    rows = conn.execute(
        "SELECT cat_id, COUNT(*) AS n FROM logs WHERE user_id = ? GROUP BY cat_id",
        (user_id,),
    ).fetchall()
    conn.close()
    return {row["cat_id"]: row["n"] for row in rows}


def get_streak(user_id):
    """
    Finds how many days in a row (ending today) have at least one log.
    SELECT DISTINCT removes duplicate dates — if you logged 5 things on
    Tuesday, DISTINCT collapses that to a single 'Tuesday' row.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT log_date FROM logs WHERE user_id = ? ORDER BY log_date DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    logged_days = {row["log_date"] for row in rows}

    streak = 0
    cursor_day = date.today()
    while cursor_day.isoformat() in logged_days:
        streak += 1
        cursor_day -= timedelta(days=1)
    return streak


def get_weekly_totals(user_id):
    """
    WHERE filters rows before grouping — here we only look at the last 7 days.
    date('now', '-6 days') is SQLite's date-math syntax.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT log_date, SUM(pts) AS total
        FROM logs
        WHERE user_id = ? AND log_date >= date('now', '-6 days')
        GROUP BY log_date
        ORDER BY log_date ASC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    totals_by_date = {row["log_date"]: row["total"] for row in rows}

    # Build all 7 days (including zero-log days) so the chart has no gaps
    days = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        days.append({"date": d, "total": totals_by_date.get(d, 0)})
    return days


def get_category_breakdown(user_id):
    """
    JOIN combines rows from two tables that share a key — here, logs.cat_id
    matches categories.id (both scoped to the same user_id), so we can pull
    the category's name/emoji/color without storing them redundantly in logs.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.emoji, c.color, COALESCE(SUM(l.pts), 0) AS total
        FROM categories c
        LEFT JOIN logs l ON l.cat_id = c.id AND l.user_id = c.user_id
        WHERE c.user_id = ?
        GROUP BY c.id
        ORDER BY total DESC
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_active_days(user_id):
    """COUNT(DISTINCT ...) counts unique values, not total rows."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(DISTINCT log_date) AS n FROM logs WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row["n"]


def get_total_logs(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM logs WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    return row["n"]


# ---------------------------------------------------------------------------
# REWARDS
# ---------------------------------------------------------------------------

def get_rewards(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM rewards WHERE user_id = ? ORDER BY pts ASC", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def add_reward(user_id, pts, text):
    conn = get_db()
    conn.execute(
        "INSERT INTO rewards (user_id, pts, text, claimed) VALUES (?, ?, ?, 0)",
        (user_id, pts, text),
    )
    conn.commit()
    conn.close()


def claim_reward(user_id, reward_id):
    conn = get_db()
    conn.execute(
        "UPDATE rewards SET claimed = 1 WHERE id = ? AND user_id = ?",
        (reward_id, user_id),
    )
    conn.commit()
    conn.close()


def delete_reward(user_id, reward_id):
    """DELETE also needs a WHERE, same rule as UPDATE — no WHERE, no survivors.
    Scoping by user_id also means you can only ever delete your own reward,
    even if you guessed someone else's reward id."""
    conn = get_db()
    conn.execute(
        "DELETE FROM rewards WHERE id = ? AND user_id = ?", (reward_id, user_id)
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MOOD CHECK-IN
# ---------------------------------------------------------------------------

def set_today_mood(user_id, mood):
    """INSERT OR REPLACE — if today already has a mood for this user,
    overwrite it instead of erroring on the duplicate primary key."""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO moods (user_id, log_date, mood) VALUES (?, ?, ?)",
        (user_id, date.today().isoformat(), mood),
    )
    conn.commit()
    conn.close()


def get_today_mood(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT mood FROM moods WHERE user_id = ? AND log_date = ?",
        (user_id, date.today().isoformat()),
    ).fetchone()
    conn.close()
    return row["mood"] if row else None


# ---------------------------------------------------------------------------
# SETTINGS (theme + custom background)
# ---------------------------------------------------------------------------

def get_user_settings(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT theme, custom_bg FROM user_settings WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return {"theme": "earth", "custom_bg": None}
    return {"theme": row["theme"], "custom_bg": row["custom_bg"]}


def set_theme(user_id, theme):
    conn = get_db()
    conn.execute(
        "INSERT INTO user_settings (user_id, theme) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET theme = excluded.theme",
        (user_id, theme),
    )
    conn.commit()
    conn.close()


def set_custom_theme(user_id, hex_color):
    conn = get_db()
    conn.execute(
        "INSERT INTO user_settings (user_id, theme, custom_bg) VALUES (?, 'custom', ?) "
        "ON CONFLICT(user_id) DO UPDATE SET theme = 'custom', custom_bg = excluded.custom_bg",
        (user_id, hex_color),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CAREER ACTIONS — one row per completed career move (Today card, Walk and
# Speak, LinkedIn Message Creator, Career Event Finder). This is the single
# source of truth the Progress page reads from.
# ---------------------------------------------------------------------------

def log_career_action(user_id, action_type, title):
    conn = get_db()
    conn.execute(
        "INSERT INTO career_actions (user_id, action_type, title, log_date) VALUES (?, ?, ?, ?)",
        (user_id, action_type, title, date.today().isoformat()),
    )
    conn.commit()
    conn.close()


def has_completed_action_today(user_id, title):
    """Used by the Today page to know whether to show the recommended
    action or a 'done for today' state."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM career_actions WHERE user_id = ? AND title = ? AND log_date = ?",
        (user_id, title, date.today().isoformat()),
    ).fetchone()
    conn.close()
    return row["n"] > 0


def get_career_action_count_this_week(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM career_actions WHERE user_id = ? AND log_date >= date('now', '-6 days')",
        (user_id,),
    ).fetchone()
    conn.close()
    return row["n"]


def get_career_action_counts_by_type(user_id):
    """GROUP BY action_type -> all-time count per type, e.g. {'speech': 4, 'linkedin': 2}."""
    conn = get_db()
    rows = conn.execute(
        "SELECT action_type, COUNT(*) AS n FROM career_actions WHERE user_id = ? GROUP BY action_type",
        (user_id,),
    ).fetchall()
    conn.close()
    return {row["action_type"]: row["n"] for row in rows}


def get_most_consistent_action_type(user_id):
    """The action_type this user has logged most often, or None if they
    haven't logged anything yet."""
    counts = get_career_action_counts_by_type(user_id)
    if not counts:
        return None
    return max(counts, key=counts.get)


# ---------------------------------------------------------------------------
# EVENT PREFERENCES — saved location + career interests for the Career
# Event Finder's outbound search links.
# ---------------------------------------------------------------------------

DEFAULT_EVENT_LOCATION = "San Diego, California"


def get_event_preferences(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT location, interests FROM event_preferences WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return {"location": DEFAULT_EVENT_LOCATION, "interests": []}
    interests = [i for i in row["interests"].split(",") if i] if row["interests"] else []
    return {"location": row["location"], "interests": interests}


def save_event_preferences(user_id, location, interests):
    """interests: a list of strings, stored comma-separated."""
    conn = get_db()
    conn.execute(
        "INSERT INTO event_preferences (user_id, location, interests) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET location = excluded.location, interests = excluded.interests",
        (user_id, location or DEFAULT_EVENT_LOCATION, ",".join(interests)),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# LINKEDIN MESSAGES — a record of every message the LinkedIn Message
# Creator has generated for this user.
# ---------------------------------------------------------------------------

def save_linkedin_message(user_id, purpose, person_name, company, detail, message):
    conn = get_db()
    conn.execute(
        "INSERT INTO linkedin_messages (user_id, purpose, person_name, company, detail, message, log_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, purpose, person_name, company, detail, message, date.today().isoformat()),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# "WRAPPED" / SHAREABLE CARD DATA
# ---------------------------------------------------------------------------

def get_monthly_summary(user_id):
    """
    Pulls everything needed for the 'wrapped' card in one place: total logs
    this calendar month, and the top category by points. strftime('%Y-%m', ...)
    formats a date down to just year+month so we can match 'this month'
    regardless of which day it is.
    """
    conn = get_db()
    this_month = date.today().strftime("%Y-%m")

    total_row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(pts),0) AS pts FROM logs "
        "WHERE user_id = ? AND strftime('%Y-%m', log_date) = ?",
        (user_id, this_month),
    ).fetchone()

    top_row = conn.execute(
        """
        SELECT c.name, c.emoji, COUNT(*) AS n
        FROM logs l JOIN categories c ON c.id = l.cat_id AND c.user_id = l.user_id
        WHERE l.user_id = ? AND strftime('%Y-%m', l.log_date) = ?
        GROUP BY c.id
        ORDER BY n DESC
        LIMIT 1
        """,
        (user_id, this_month),
    ).fetchone()

    conn.close()
    return {
        "total_logs": total_row["n"],
        "total_pts": total_row["pts"],
        "top_category": dict(top_row) if top_row else None,
    }


# ---------------------------------------------------------------------------
# RESET
# ---------------------------------------------------------------------------

def reset_all(user_id):
    """Wipes this user's logs and rewards, re-seeds their default rewards.
    Categories stay (their custom names/points survive a reset). Only ever
    touches rows matching this user_id."""
    conn = get_db()
    conn.execute("DELETE FROM logs WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM rewards WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    ensure_user(user_id)  # re-seeds default rewards since this user has none now
