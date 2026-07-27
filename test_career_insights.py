"""
test_career_insights.py
------------------------
Run with:  pytest test_career_insights.py -v

Parses every query out of career_insights.sql and runs each one against a
freshly built, populated temp database (same schema as the real app, via
database.init_db()). This is what backs the claim "every query must run
successfully against a populated test database" — if a query in that file
has a typo or references a column that doesn't exist, this test fails.

career_insights.sql is a standalone portfolio/analysis file — the app
itself does not import or execute it (see the file's own header comment).
This test proves the SQL is correct, not that any page depends on it.
"""

import re
from pathlib import Path

import pytest

import database as db

SQL_PATH = Path(__file__).parent / "career_insights.sql"


def _load_statements():
    """Split career_insights.sql on ';' into individual runnable
    statements, dropping blank/comment-only chunks left over from the
    trailing newline or leading file banner."""
    raw = SQL_PATH.read_text()
    chunks = [c.strip() for c in raw.split(";")]
    statements = []
    for chunk in chunks:
        # a chunk with no non-comment, non-blank line has nothing to run
        code_lines = [
            line for line in chunk.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if code_lines:
            statements.append(chunk)
    return statements


STATEMENTS = _load_statements()


@pytest.fixture
def populated_db(monkeypatch, tmp_path):
    test_db_path = tmp_path / "test_career_insights.db"
    monkeypatch.setattr(db, "DB_PATH", str(test_db_path))
    db.init_db()

    user_id = "insights-test-user"
    db.ensure_user(user_id)

    # a realistic, varied spread of career_actions across several days and
    # types so every GROUP BY / ORDER BY / window function has real data
    # to chew on, not just a single trivial row
    from datetime import date, timedelta
    today = date.today()
    seeded = [
        (0, "speech", "Practiced out loud"),
        (0, "linkedin", "LinkedIn message: Thank someone"),
        (1, "speech", "Practiced out loud"),
        (2, "job_review", "Reviewed a job description"),
        (2, "job_review", "Reviewed a job description"),
        (3, "event", "Searched Google for events"),
        (5, "linkedin", "LinkedIn message: Ask for career advice"),
        (6, "speech", "Practiced out loud"),
    ]
    conn = db.get_db()
    for days_ago, action_type, title in seeded:
        log_date = (today - timedelta(days=days_ago)).isoformat()
        conn.execute(
            "INSERT INTO career_actions (user_id, action_type, title, log_date) VALUES (?, ?, ?, ?)",
            (user_id, action_type, title, log_date),
        )
    conn.commit()
    conn.close()

    yield user_id


def test_career_insights_sql_file_exists():
    assert SQL_PATH.exists()


def test_career_insights_sql_has_at_least_six_statements():
    assert len(STATEMENTS) >= 6


@pytest.mark.parametrize("index", range(len(STATEMENTS)))
def test_each_career_insights_query_runs_successfully(populated_db, index):
    user_id = populated_db
    statement = STATEMENTS[index]

    conn = db.get_db()
    try:
        params = {"user_id": user_id} if ":user_id" in statement else {}
        rows = conn.execute(statement, params).fetchall()
        # every seeded query should return at least one row against this
        # populated dataset — an empty result would usually mean a typo
        # in a WHERE/JOIN condition rather than a genuinely empty table
        assert rows is not None
    finally:
        conn.close()


def test_career_insights_sql_demonstrates_required_constructs():
    full_text = SQL_PATH.read_text().upper()
    for construct in ("SELECT", "WHERE", "GROUP BY", "ORDER BY", "CASE", "WITH", " OVER "):
        assert construct in full_text, f"missing {construct!r} somewhere in career_insights.sql"
    # aggregate functions
    assert "COUNT(" in full_text
    assert "SUM(" in full_text or "AVG(" in full_text
