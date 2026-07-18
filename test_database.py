"""
test_database.py
-----------------
Run with:  pytest test_database.py -v

Tests the database layer in isolation, using a temporary throwaway
database file so tests never touch your real bloom.db data.
"""

import os
import pytest
import database as db


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Runs before every test: points the app at a fresh temp database
    file instead of the real one, so tests can't corrupt real data."""
    test_db_path = tmp_path / "test_bloom.db"
    monkeypatch.setattr(db, "DB_PATH", str(test_db_path))
    db.init_db()
    yield
    # tmp_path is auto-cleaned by pytest, nothing to do here


def test_init_db_seeds_default_categories():
    categories = db.get_categories()
    assert len(categories) == 5
    ids = {c["id"] for c in categories}
    assert ids == {"job", "speech", "code", "up", "care"}


def test_init_db_seeds_default_rewards():
    rewards = db.get_rewards()
    assert len(rewards) == 6
    assert all(r["claimed"] == 0 for r in rewards)


def test_add_log_increases_total_points():
    assert db.get_total_points() == 0
    db.add_log("job", 1)
    assert db.get_total_points() == 1
    db.add_log("job", 1)
    assert db.get_total_points() == 2


def test_get_total_points_with_no_logs_returns_zero():
    # regression test for the COALESCE bug: SUM() of zero rows is NULL,
    # not 0, unless you explicitly handle it
    assert db.get_total_points() == 0


def test_counts_by_category():
    db.add_log("job", 1)
    db.add_log("job", 1)
    db.add_log("code", 1)
    counts = db.get_counts_by_category()
    assert counts["job"] == 2
    assert counts["code"] == 1
    assert "speech" not in counts  # never logged, shouldn't appear


def test_streak_is_zero_with_no_logs():
    assert db.get_streak() == 0


def test_streak_counts_today():
    db.add_log("job", 1)
    assert db.get_streak() == 1


def test_update_category_changes_name_and_points():
    db.update_category("job", "Applications", 3)
    categories = {c["id"]: c for c in db.get_categories()}
    assert categories["job"]["name"] == "Applications"
    assert categories["job"]["pts"] == 3


def test_claim_reward_marks_claimed():
    rewards = db.get_rewards()
    first_id = rewards[0]["id"]
    db.claim_reward(first_id)
    updated = {r["id"]: r for r in db.get_rewards()}
    assert updated[first_id]["claimed"] == 1


def test_delete_reward_removes_it():
    rewards = db.get_rewards()
    count_before = len(rewards)
    db.delete_reward(rewards[0]["id"])
    assert len(db.get_rewards()) == count_before - 1


def test_add_reward_creates_new_row():
    db.add_reward(100, "test reward")
    rewards = [r for r in db.get_rewards() if r["text"] == "test reward"]
    assert len(rewards) == 1
    assert rewards[0]["pts"] == 100


def test_category_breakdown_includes_zero_categories():
    # LEFT JOIN should keep categories with no logs, showing total=0
    db.add_log("job", 1)
    breakdown = {row["id"]: row["total"] for row in db.get_category_breakdown()}
    assert breakdown["job"] == 1
    assert breakdown["speech"] == 0  # never logged, still appears via LEFT JOIN


def test_reset_all_clears_logs_and_rewards_but_keeps_categories():
    db.add_log("job", 1)
    db.update_category("job", "Custom Name", 5)
    db.reset_all()
    assert db.get_total_points() == 0
    assert db.get_total_logs() == 0
    categories = {c["id"]: c for c in db.get_categories()}
    assert categories["job"]["name"] == "Custom Name"  # survives reset


def test_mood_set_and_get():
    assert db.get_today_mood() is None
    db.set_today_mood("✨")
    assert db.get_today_mood() == "✨"


def test_mood_overwrites_same_day():
    db.set_today_mood("😩")
    db.set_today_mood("🙂")
    assert db.get_today_mood() == "🙂"


def test_monthly_summary_with_no_logs():
    summary = db.get_monthly_summary()
    assert summary["total_logs"] == 0
    assert summary["total_pts"] == 0
    assert summary["top_category"] is None


def test_monthly_summary_finds_top_category():
    db.add_log("job", 1)
    db.add_log("job", 1)
    db.add_log("code", 1)
    summary = db.get_monthly_summary()
    assert summary["total_logs"] == 3
    assert summary["top_category"]["name"] == "Job search"
