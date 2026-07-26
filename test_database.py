"""
test_database.py
-----------------
Run with:  pytest test_database.py -v

Tests the database layer in isolation, using a temporary throwaway
database file so tests never touch your real onemoretime.db data.

Every function in database.py takes a user_id as its first argument, so
every test here works against a fixed `USER` id via ensure_user(). A
handful of extra tests at the bottom specifically check that one user's
data never leaks into another user's queries — that isolation is the
whole point of the multi-user, no-login design.
"""

import os
import pytest
import database as db

USER = "test-user-1"
OTHER = "test-user-2"


@pytest.fixture(autouse=True)
def temp_db(monkeypatch, tmp_path):
    """Runs before every test: points the app at a fresh temp database
    file instead of the real one, so tests can't corrupt real data."""
    test_db_path = tmp_path / "test_onemoretime.db"
    monkeypatch.setattr(db, "DB_PATH", str(test_db_path))
    db.init_db()
    db.ensure_user(USER)
    yield
    # tmp_path is auto-cleaned by pytest, nothing to do here


def test_ensure_user_seeds_default_categories():
    categories = db.get_categories(USER)
    assert len(categories) == 9
    ids = {c["id"] for c in categories}
    assert ids == {"job", "speech", "code", "up", "care", "water", "reading", "mindfulness", "movement"}


def test_ensure_user_seeds_default_rewards():
    rewards = db.get_rewards(USER)
    assert len(rewards) == 6
    assert all(r["claimed"] == 0 for r in rewards)


def test_ensure_user_is_idempotent():
    # calling it again (e.g. a returning visitor whose cookie round-trips
    # through /me) must not duplicate categories or rewards
    db.ensure_user(USER)
    db.ensure_user(USER)
    assert len(db.get_categories(USER)) == 9
    assert len(db.get_rewards(USER)) == 6


def test_add_log_increases_total_points():
    assert db.get_total_points(USER) == 0
    db.add_log(USER, "job", 1)
    assert db.get_total_points(USER) == 1
    db.add_log(USER, "job", 1)
    assert db.get_total_points(USER) == 2


def test_get_total_points_with_no_logs_returns_zero():
    # regression test for the COALESCE bug: SUM() of zero rows is NULL,
    # not 0, unless you explicitly handle it
    assert db.get_total_points(USER) == 0


def test_counts_by_category():
    db.add_log(USER, "job", 1)
    db.add_log(USER, "job", 1)
    db.add_log(USER, "code", 1)
    counts = db.get_counts_by_category(USER)
    assert counts["job"] == 2
    assert counts["code"] == 1
    assert "speech" not in counts  # never logged, shouldn't appear


def test_streak_is_zero_with_no_logs():
    assert db.get_streak(USER) == 0


def test_streak_counts_today():
    db.add_log(USER, "job", 1)
    assert db.get_streak(USER) == 1


def test_update_category_changes_name_and_points():
    db.update_category(USER, "job", "Applications", 3)
    categories = {c["id"]: c for c in db.get_categories(USER)}
    assert categories["job"]["name"] == "Applications"
    assert categories["job"]["pts"] == 3


def test_add_custom_category_creates_new_row():
    cat_id = db.add_custom_category(USER, "🎨", "Creative time", 2)
    categories = {c["id"]: c for c in db.get_categories(USER)}
    assert cat_id in categories
    assert categories[cat_id]["name"] == "Creative time"
    assert categories[cat_id]["emoji"] == "🎨"
    assert categories[cat_id]["pts"] == 2
    assert categories[cat_id]["custom"] == 1


def test_delete_category_removes_custom_category_only():
    cat_id = db.add_custom_category(USER, "🎨", "Creative time", 2)
    db.delete_category(USER, cat_id)
    categories = {c["id"]: c for c in db.get_categories(USER)}
    assert cat_id not in categories

    # deleting a default category id is a no-op, since custom=0
    db.delete_category(USER, "job")
    categories = {c["id"]: c for c in db.get_categories(USER)}
    assert "job" in categories


def test_delete_category_also_clears_its_logs():
    cat_id = db.add_custom_category(USER, "🎨", "Creative time", 2)
    db.add_log(USER, cat_id, 2)
    assert db.get_total_points(USER) == 2
    db.delete_category(USER, cat_id)
    assert db.get_total_points(USER) == 0


def test_claim_reward_marks_claimed():
    rewards = db.get_rewards(USER)
    first_id = rewards[0]["id"]
    db.claim_reward(USER, first_id)
    updated = {r["id"]: r for r in db.get_rewards(USER)}
    assert updated[first_id]["claimed"] == 1


def test_delete_reward_removes_it():
    rewards = db.get_rewards(USER)
    count_before = len(rewards)
    db.delete_reward(USER, rewards[0]["id"])
    assert len(db.get_rewards(USER)) == count_before - 1


def test_add_reward_creates_new_row():
    db.add_reward(USER, 100, "test reward")
    rewards = [r for r in db.get_rewards(USER) if r["text"] == "test reward"]
    assert len(rewards) == 1
    assert rewards[0]["pts"] == 100


def test_category_breakdown_includes_zero_categories():
    # LEFT JOIN should keep categories with no logs, showing total=0
    db.add_log(USER, "job", 1)
    breakdown = {row["id"]: row["total"] for row in db.get_category_breakdown(USER)}
    assert breakdown["job"] == 1
    assert breakdown["speech"] == 0  # never logged, still appears via LEFT JOIN


def test_reset_all_clears_logs_and_rewards_but_keeps_categories():
    db.add_log(USER, "job", 1)
    db.update_category(USER, "job", "Custom Name", 5)
    db.reset_all(USER)
    assert db.get_total_points(USER) == 0
    assert db.get_total_logs(USER) == 0
    categories = {c["id"]: c for c in db.get_categories(USER)}
    assert categories["job"]["name"] == "Custom Name"  # survives reset


def test_mood_set_and_get():
    assert db.get_today_mood(USER) is None
    db.set_today_mood(USER, "✨")
    assert db.get_today_mood(USER) == "✨"


def test_mood_overwrites_same_day():
    db.set_today_mood(USER, "😩")
    db.set_today_mood(USER, "🙂")
    assert db.get_today_mood(USER) == "🙂"


def test_monthly_summary_with_no_logs():
    summary = db.get_monthly_summary(USER)
    assert summary["total_logs"] == 0
    assert summary["total_pts"] == 0
    assert summary["top_category"] is None


def test_monthly_summary_finds_top_category():
    db.add_log(USER, "job", 1)
    db.add_log(USER, "job", 1)
    db.add_log(USER, "code", 1)
    summary = db.get_monthly_summary(USER)
    assert summary["total_logs"] == 3
    assert summary["top_category"]["name"] == "Job search"


def test_theme_defaults_to_earth():
    settings = db.get_user_settings(USER)
    assert settings["theme"] == "earth"
    assert settings["custom_bg"] is None


def test_set_theme_updates_settings():
    db.set_theme(USER, "y2k")
    assert db.get_user_settings(USER)["theme"] == "y2k"


def test_set_custom_theme_stores_hex_color():
    db.set_custom_theme(USER, "#123456")
    settings = db.get_user_settings(USER)
    assert settings["theme"] == "custom"
    assert settings["custom_bg"] == "#123456"


# ---------------------------------------------------------------------------
# MULTI-USER ISOLATION — one visitor's data must never show up in another
# visitor's queries, since there's no login/password protecting it.
# ---------------------------------------------------------------------------

def test_two_users_get_independent_categories():
    db.ensure_user(OTHER)
    db.update_category(USER, "job", "Renamed for user 1", 9)
    categories_other = {c["id"]: c for c in db.get_categories(OTHER)}
    assert categories_other["job"]["name"] == "Job search"  # untouched


def test_two_users_get_independent_points_and_logs():
    db.ensure_user(OTHER)
    db.add_log(USER, "job", 5)
    assert db.get_total_points(USER) == 5
    assert db.get_total_points(OTHER) == 0
    assert db.get_total_logs(OTHER) == 0


def test_two_users_get_independent_rewards():
    db.ensure_user(OTHER)
    db.add_reward(USER, 42, "only mine")
    other_texts = {r["text"] for r in db.get_rewards(OTHER)}
    assert "only mine" not in other_texts


def test_delete_reward_cannot_touch_another_users_reward():
    db.ensure_user(OTHER)
    mine = db.get_rewards(USER)[0]
    db.delete_reward(OTHER, mine["id"])  # OTHER tries to delete USER's reward id
    still_there = {r["id"] for r in db.get_rewards(USER)}
    assert mine["id"] in still_there


def test_two_users_get_independent_moods():
    db.ensure_user(OTHER)
    db.set_today_mood(USER, "✨")
    assert db.get_today_mood(OTHER) is None


# ---------------------------------------------------------------------------
# CAREER ACTIONS — Today/Progress logging
# ---------------------------------------------------------------------------

def test_log_career_action_increases_weekly_count():
    assert db.get_career_action_count_this_week(USER) == 0
    db.log_career_action(USER, "speech", "Practice intro")
    assert db.get_career_action_count_this_week(USER) == 1


def test_has_completed_action_today_is_false_until_logged():
    assert db.has_completed_action_today(USER, "Practice intro") is False
    db.log_career_action(USER, "speech", "Practice intro")
    assert db.has_completed_action_today(USER, "Practice intro") is True


def test_has_completed_action_today_matches_by_exact_title():
    db.log_career_action(USER, "speech", "Practice intro")
    assert db.has_completed_action_today(USER, "Something else") is False


def test_career_action_counts_by_type():
    db.log_career_action(USER, "speech", "a")
    db.log_career_action(USER, "speech", "b")
    db.log_career_action(USER, "linkedin", "c")
    counts = db.get_career_action_counts_by_type(USER)
    assert counts["speech"] == 2
    assert counts["linkedin"] == 1


def test_most_consistent_action_type_with_no_actions_is_none():
    assert db.get_most_consistent_action_type(USER) is None


def test_most_consistent_action_type_picks_highest_count():
    db.log_career_action(USER, "speech", "a")
    db.log_career_action(USER, "speech", "b")
    db.log_career_action(USER, "linkedin", "c")
    assert db.get_most_consistent_action_type(USER) == "speech"


def test_two_users_get_independent_career_actions():
    db.ensure_user(OTHER)
    db.log_career_action(USER, "speech", "only mine")
    assert db.get_career_action_count_this_week(OTHER) == 0
    assert db.has_completed_action_today(OTHER, "only mine") is False


# ---------------------------------------------------------------------------
# EVENT PREFERENCES
# ---------------------------------------------------------------------------

def test_event_preferences_default_when_unset():
    prefs = db.get_event_preferences(USER)
    assert prefs["location"] == "San Diego, California"
    assert prefs["interests"] == []


def test_save_and_get_event_preferences():
    db.save_event_preferences(USER, "Austin, Texas", ["Biotechnology", "Product management"])
    prefs = db.get_event_preferences(USER)
    assert prefs["location"] == "Austin, Texas"
    assert prefs["interests"] == ["Biotechnology", "Product management"]


def test_save_event_preferences_overwrites_previous_save():
    db.save_event_preferences(USER, "Austin, Texas", ["Biotechnology"])
    db.save_event_preferences(USER, "San Diego, California", ["Artificial intelligence"])
    prefs = db.get_event_preferences(USER)
    assert prefs["location"] == "San Diego, California"
    assert prefs["interests"] == ["Artificial intelligence"]


def test_save_event_preferences_blank_location_falls_back_to_default():
    db.save_event_preferences(USER, "", ["Biotechnology"])
    assert db.get_event_preferences(USER)["location"] == "San Diego, California"


def test_two_users_get_independent_event_preferences():
    db.ensure_user(OTHER)
    db.save_event_preferences(USER, "Austin, Texas", ["Biotechnology"])
    assert db.get_event_preferences(OTHER)["location"] == "San Diego, California"


# ---------------------------------------------------------------------------
# LINKEDIN MESSAGE HISTORY
# ---------------------------------------------------------------------------

def test_save_linkedin_message_does_not_raise():
    db.save_linkedin_message(USER, "Met at an event", "Jordan", "Illumina", "the biotech meetup", "Hi Jordan...")
    # no dedicated getter yet — this just proves the insert succeeds and the
    # row is scoped correctly (checked via table isolation, not a query API)


def test_init_db_is_idempotent_and_safe_to_rerun():
    # simulates an existing user's database getting the new tables added —
    # calling init_db() again must never raise or wipe data
    db.log_career_action(USER, "speech", "existing action")
    db.init_db()
    assert db.get_career_action_count_this_week(USER) == 1
