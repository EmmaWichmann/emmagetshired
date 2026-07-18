"""
database.py
-----------
Every SQL query the app uses lives in this one file, written out in plain
SQL (no ORM) on purpose — the whole point of this rebuild is to practice SQL.
Each function below is a small, readable example of a real SQL pattern.
"""

import sqlite3
from datetime import date, timedelta

DB_PATH = "bloom.db"


def get_db():
    """Open a connection. row_factory lets us access columns by name,
    e.g. row['name'] instead of row[2] — much easier to read."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """
    Creates the three tables this app needs, if they don't already exist.

    categories  -> the 5 things you can log (job search, speech, etc)
    logs        -> one row per time you log something (this is your history)
    rewards     -> the real-life treats you unlock with points
    """
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS categories (
        id    TEXT PRIMARY KEY,
        emoji TEXT NOT NULL,
        name  TEXT NOT NULL,
        sub   TEXT,
        pts   INTEGER NOT NULL DEFAULT 1,
        color TEXT
    );

    CREATE TABLE IF NOT EXISTS logs (
        id       INTEGER PRIMARY KEY AUTOINCREMENT,
        cat_id   TEXT NOT NULL,
        pts      INTEGER NOT NULL,
        log_date TEXT NOT NULL,
        FOREIGN KEY (cat_id) REFERENCES categories(id)
    );

    CREATE TABLE IF NOT EXISTS rewards (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        pts     INTEGER NOT NULL,
        text    TEXT NOT NULL,
        claimed INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS moods (
        log_date TEXT PRIMARY KEY,
        mood     TEXT NOT NULL
    );
    """)
    conn.commit()

    # Seed default categories only if the table is empty
    count = conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
    if count == 0:
        default_categories = [
            ("job",    "💼", "Job search",        "1 application",           1, "#8B5A3A"),
            ("speech", "🗣️", "Speech practice",   "1 min counts",            1, "#C4847A"),
            ("code",   "💻", "Coding practice",   "Coding Hub / certs",      1, "#6B7C5A"),
            ("up",     "🌤️", "Got up & moving",   "out of bed, outside",     1, "#C9A84C"),
            ("care",   "🧴", "Self-care",         "skincare, shower, etc",   1, "#5C3D2E"),
        ]
        conn.executemany(
            "INSERT INTO categories (id, emoji, name, sub, pts, color) VALUES (?, ?, ?, ?, ?, ?)",
            default_categories,
        )

    reward_count = conn.execute("SELECT COUNT(*) AS n FROM rewards").fetchone()["n"]
    if reward_count == 0:
        default_rewards = [
            (5,  "☕ coffee treat"),
            (10, "📺 episode of a comfort show, guilt-free"),
            (15, "🛁 bath night + face mask"),
            (20, "💅 something small for yourself"),
            (30, "🛍️ a real treat-yourself purchase"),
            (50, "🌴 a full day off, no guilt, no catching up"),
        ]
        conn.executemany(
            "INSERT INTO rewards (pts, text) VALUES (?, ?)", default_rewards
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

def get_categories():
    """SELECT * — grab every category, in the order they were created."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM categories ORDER BY rowid").fetchall()
    conn.close()
    return rows


def update_category(cat_id, name, pts):
    """UPDATE with a WHERE clause — without WHERE this would update EVERY row."""
    conn = get_db()
    conn.execute(
        "UPDATE categories SET name = ?, pts = ? WHERE id = ?",
        (name, pts, cat_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# LOGS
# ---------------------------------------------------------------------------

def add_log(cat_id, pts):
    """INSERT a new row — this is how every 'log' button click gets saved."""
    conn = get_db()
    conn.execute(
        "INSERT INTO logs (cat_id, pts, log_date) VALUES (?, ?, ?)",
        (cat_id, pts, date.today().isoformat()),
    )
    conn.commit()
    conn.close()


def get_total_points():
    """SUM() is an aggregate function — it collapses many rows into one number.
    COALESCE handles the case where there are zero logs (SUM would return NULL)."""
    conn = get_db()
    row = conn.execute("SELECT COALESCE(SUM(pts), 0) AS total FROM logs").fetchone()
    conn.close()
    return row["total"]


def get_counts_by_category():
    """GROUP BY groups rows that share a value (here: cat_id) so aggregate
    functions run per-group instead of over the whole table."""
    conn = get_db()
    rows = conn.execute(
        "SELECT cat_id, COUNT(*) AS n FROM logs GROUP BY cat_id"
    ).fetchall()
    conn.close()
    return {row["cat_id"]: row["n"] for row in rows}


def get_streak():
    """
    Finds how many days in a row (ending today) have at least one log.
    SELECT DISTINCT removes duplicate dates — if you logged 5 things on
    Tuesday, DISTINCT collapses that to a single 'Tuesday' row.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT DISTINCT log_date FROM logs ORDER BY log_date DESC"
    ).fetchall()
    conn.close()
    logged_days = {row["log_date"] for row in rows}

    streak = 0
    cursor_day = date.today()
    while cursor_day.isoformat() in logged_days:
        streak += 1
        cursor_day -= timedelta(days=1)
    return streak


def get_weekly_totals():
    """
    WHERE filters rows before grouping — here we only look at the last 7 days.
    date('now', '-6 days') is SQLite's date-math syntax.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT log_date, SUM(pts) AS total
        FROM logs
        WHERE log_date >= date('now', '-6 days')
        GROUP BY log_date
        ORDER BY log_date ASC
        """
    ).fetchall()
    conn.close()
    totals_by_date = {row["log_date"]: row["total"] for row in rows}

    # Build all 7 days (including zero-log days) so the chart has no gaps
    days = []
    for i in range(6, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        days.append({"date": d, "total": totals_by_date.get(d, 0)})
    return days


def get_category_breakdown():
    """
    JOIN combines rows from two tables that share a key — here, logs.cat_id
    matches categories.id, so we can pull the category's name/emoji/color
    without storing them redundantly in the logs table.
    """
    conn = get_db()
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.emoji, c.color, COALESCE(SUM(l.pts), 0) AS total
        FROM categories c
        LEFT JOIN logs l ON l.cat_id = c.id
        GROUP BY c.id
        ORDER BY total DESC
        """
    ).fetchall()
    conn.close()
    return rows


def get_active_days():
    """COUNT(DISTINCT ...) counts unique values, not total rows."""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(DISTINCT log_date) AS n FROM logs"
    ).fetchone()
    conn.close()
    return row["n"]


def get_total_logs():
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) AS n FROM logs").fetchone()
    conn.close()
    return row["n"]


# ---------------------------------------------------------------------------
# REWARDS
# ---------------------------------------------------------------------------

def get_rewards():
    conn = get_db()
    rows = conn.execute("SELECT * FROM rewards ORDER BY pts ASC").fetchall()
    conn.close()
    return rows


def add_reward(pts, text):
    conn = get_db()
    conn.execute(
        "INSERT INTO rewards (pts, text, claimed) VALUES (?, ?, 0)", (pts, text)
    )
    conn.commit()
    conn.close()


def claim_reward(reward_id):
    conn = get_db()
    conn.execute("UPDATE rewards SET claimed = 1 WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()


def delete_reward(reward_id):
    """DELETE also needs a WHERE, same rule as UPDATE — no WHERE, no survivors."""
    conn = get_db()
    conn.execute("DELETE FROM rewards WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# MOOD CHECK-IN
# ---------------------------------------------------------------------------

def set_today_mood(mood):
    """INSERT OR REPLACE — if today already has a mood, overwrite it instead
    of erroring on the duplicate primary key."""
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO moods (log_date, mood) VALUES (?, ?)",
        (date.today().isoformat(), mood),
    )
    conn.commit()
    conn.close()


def get_today_mood():
    conn = get_db()
    row = conn.execute(
        "SELECT mood FROM moods WHERE log_date = ?", (date.today().isoformat(),)
    ).fetchone()
    conn.close()
    return row["mood"] if row else None


# ---------------------------------------------------------------------------
# "WRAPPED" / SHAREABLE CARD DATA
# ---------------------------------------------------------------------------

def get_monthly_summary():
    """
    Pulls everything needed for the 'bloom wrapped' card in one place:
    total logs this calendar month, and the top category by points.
    strftime('%Y-%m', ...) formats a date down to just year+month so we
    can match 'this month' regardless of which day it is.
    """
    conn = get_db()
    this_month = date.today().strftime("%Y-%m")

    total_row = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(pts),0) AS pts FROM logs "
        "WHERE strftime('%Y-%m', log_date) = ?",
        (this_month,),
    ).fetchone()

    top_row = conn.execute(
        """
        SELECT c.name, c.emoji, COUNT(*) AS n
        FROM logs l JOIN categories c ON c.id = l.cat_id
        WHERE strftime('%Y-%m', l.log_date) = ?
        GROUP BY c.id
        ORDER BY n DESC
        LIMIT 1
        """,
        (this_month,),
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

def reset_all():
    """Wipes logs and rewards, re-seeds default rewards. Categories stay
    (your custom names/points survive a reset)."""
    conn = get_db()
    conn.execute("DELETE FROM logs")
    conn.execute("DELETE FROM rewards")
    conn.commit()
    conn.close()
    init_db()  # re-seeds default rewards since the table is empty again
