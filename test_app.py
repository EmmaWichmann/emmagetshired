"""
test_app.py
-----------
Run with:  pytest test_app.py -v

Route-level tests for the Today / Career Tools / Progress career copilot,
using Flask's test client against a temporary throwaway database (never the
real onemoretime.db).

`app.py` calls db.init_db() at import time now (so gunicorn/production gets
new tables too — see app.py), which means the *first* import of `app` in a
test run must already have database.DB_PATH pointed at a temp file. The
`client` fixture below patches DB_PATH and then imports/reloads `app` so
every test gets a fresh app+db pair.
"""

import importlib

import pytest

import database as db


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_db_path = tmp_path / "test_onemoretime.db"
    monkeypatch.setattr(db, "DB_PATH", str(test_db_path))
    db.init_db()

    import app as app_module
    importlib.reload(app_module)  # re-runs app.py's module-level db.init_db() against the patched path
    app_module.app.config["TESTING"] = True

    with app_module.app.test_client() as test_client:
        yield test_client, app_module


def test_today_shows_recommended_action(client):
    test_client, app_module = client
    resp = test_client.get("/today")
    assert resp.status_code == 200
    action = app_module.get_today_action()
    assert action["title"].encode() in resp.data


def test_today_mark_complete_logs_career_action(client):
    test_client, app_module = client
    action = app_module.get_today_action()
    resp = test_client.post("/today/complete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Nice work" in resp.data
    assert action["title"].encode() in resp.data


def test_today_mark_complete_is_idempotent_per_day(client):
    test_client, app_module = client
    test_client.post("/today/complete")
    test_client.post("/today/complete")
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 1


def test_career_tools_page_lists_four_cards(client):
    test_client, _ = client
    resp = test_client.get("/tools")
    assert resp.status_code == 200
    assert b"Walk and Speak" in resp.data
    assert b"LinkedIn Message Creator" in resp.data
    assert b"Resume Match Checker" in resp.data
    assert b"Coming Next" in resp.data
    assert b"Career Event Finder" in resp.data


def test_walk_and_speak_page_renders_a_prompt(client):
    test_client, _ = client
    resp = test_client.get("/tools/speak")
    assert resp.status_code == 200
    assert b"I practiced this" in resp.data


def test_walk_and_speak_done_logs_speech_action(client):
    test_client, _ = client
    test_client.get("/tools/speak")
    resp = test_client.post("/tools/speak/done", follow_redirects=True)
    assert resp.status_code == 200
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_counts_by_type(uid).get("speech") == 1


def test_linkedin_generate_creates_message_and_logs_action(client):
    test_client, _ = client
    resp = test_client.post("/tools/linkedin/generate", data={
        "purpose": "Met at an event",
        "name": "Jordan",
        "company": "Illumina",
        "detail": "the San Diego Biotech Meetup",
    })
    assert resp.status_code == 200
    assert b"Jordan" in resp.data
    assert b"San Diego Biotech Meetup" in resp.data
    progress = test_client.get("/progress")
    assert b"LinkedIn messages" in progress.data


def test_linkedin_generate_requires_known_purpose(client):
    test_client, _ = client
    resp = test_client.post("/tools/linkedin/generate", data={
        "purpose": "not a real purpose",
        "name": "Jordan",
    })
    assert resp.status_code == 200
    assert b"Your message" not in resp.data


def test_events_save_preferences(client):
    test_client, _ = client
    resp = test_client.post("/tools/events/save", data={
        "location": "Austin, Texas",
        "interests": ["Biotechnology", "Product management"],
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert b"Austin, Texas" in resp.data
    assert b"Saved your location" in resp.data


def test_events_go_redirects_to_external_search_and_logs_action(client):
    test_client, _ = client
    resp = test_client.get("/tools/events/go/google")
    assert resp.status_code == 302
    assert "google.com" in resp.headers["Location"]
    progress = test_client.get("/progress")
    assert b"Event searches" in progress.data


def test_events_go_unknown_engine_redirects_back_to_events_tool(client):
    test_client, _ = client
    resp = test_client.get("/tools/events/go/not-a-real-engine")
    assert resp.status_code == 302
    assert "/tools/events" in resp.headers["Location"]


def test_progress_page_renders_stats(client):
    test_client, _ = client
    resp = test_client.get("/progress")
    assert resp.status_code == 200
    assert b"Actions this week" in resp.data
    assert b"Speech practices" in resp.data


def test_cover_next_button_points_to_today(client):
    test_client, _ = client
    resp = test_client.get("/")
    assert resp.status_code == 200
    assert b'href="/today"' in resp.data


def test_new_nav_does_not_show_legacy_habit_tracker_wording(client):
    test_client, _ = client
    for path in ("/today", "/tools", "/progress"):
        resp = test_client.get(path)
        assert b"Log today" not in resp.data
        assert b"Rewards to unlock" not in resp.data
        assert b"API access" not in resp.data


# ---------------------------------------------------------------------------
# PROGRESS INSIGHT — a tie (or too little data) must never be presented as
# a clear "most consistent" winner.
# ---------------------------------------------------------------------------

def test_get_progress_insight_with_no_actions(client):
    _, app_module = client
    assert app_module.get_progress_insight({}) == "Your first small career move will appear here."


def test_get_progress_insight_below_momentum_threshold(client):
    _, app_module = client
    assert app_module.get_progress_insight({"speech": 2}) == \
        "You are building momentum across multiple career activities."


def test_get_progress_insight_tied_leaders_even_with_enough_actions(client):
    _, app_module = client
    insight = app_module.get_progress_insight({"speech": 2, "linkedin": 2, "event": 1})
    assert insight == "You are building momentum across multiple career activities."


def test_get_progress_insight_names_a_clear_leader(client):
    _, app_module = client
    insight = app_module.get_progress_insight({"speech": 3, "linkedin": 1})
    assert "Walk and Speak practice" in insight


def test_progress_page_shows_empty_state_with_zero_actions(client):
    test_client, _ = client
    resp = test_client.get("/progress")
    assert b"Your first small career move will appear here." in resp.data


def test_progress_page_shows_momentum_state_on_a_tie(client):
    test_client, _ = client
    test_client.get("/today")  # establishes the uid cookie
    uid = test_client.get_cookie("uid").value
    db.log_career_action(uid, "speech", "a")
    db.log_career_action(uid, "linkedin", "b")
    db.log_career_action(uid, "event", "c")  # 3 actions, but a 3-way tie
    resp = test_client.get("/progress")
    assert b"You are building momentum across multiple career activities." in resp.data


def test_progress_page_names_leader_once_clearly_ahead(client):
    test_client, _ = client
    test_client.get("/today")
    uid = test_client.get_cookie("uid").value
    db.log_career_action(uid, "speech", "a")
    db.log_career_action(uid, "speech", "b")
    db.log_career_action(uid, "linkedin", "c")
    resp = test_client.get("/progress")
    assert b"kept up with Walk and Speak practice" in resp.data


# ---------------------------------------------------------------------------
# GROWTH TRAIL — signature animation component and weekly growth stage
# ---------------------------------------------------------------------------

def test_get_growth_stage_covers_every_weekly_range(client):
    _, app_module = client
    cases = {
        0: "seed",
        1: "sprout",
        2: "leafy-stem",
        3: "leafy-stem",
        4: "flower-bud",
        5: "flower-bud",
        6: "open-flower",
        10: "open-flower",
    }
    for weekly_count, expected_key in cases.items():
        assert app_module.get_growth_stage(weekly_count)["key"] == expected_key


def test_growth_stage_labels_match_spec_wording(client):
    _, app_module = client
    expected_labels = {
        0: "Your next step begins here.",
        1: "Your first step is growing.",
        2: "Your momentum is taking root.",
        4: "Your consistency is beginning to bloom.",
        6: "Your career garden is growing.",
    }
    for weekly_count, expected_label in expected_labels.items():
        assert app_module.get_growth_stage(weekly_count)["label"] == expected_label


def test_today_tools_and_progress_all_render_the_growth_trail(client):
    test_client, _ = client
    for path in ("/today", "/tools", "/progress"):
        resp = test_client.get(path)
        assert resp.status_code == 200
        assert b'class="growth-trail" aria-hidden="true"' in resp.data
        assert b"trail-stem" in resp.data


def test_today_incomplete_state_has_no_bloom(client):
    test_client, _ = client
    resp = test_client.get("/today")
    assert b"trail-bloom" not in resp.data


def test_today_completed_state_shows_bloom(client):
    test_client, _ = client
    test_client.post("/today/complete")
    resp = test_client.get("/today")
    assert b"trail-bloom" in resp.data


def test_progress_page_shows_growth_stage_figure_and_label(client):
    test_client, _ = client
    test_client.get("/today")
    uid = test_client.get_cookie("uid").value
    db.log_career_action(uid, "speech", "a")
    db.log_career_action(uid, "linkedin", "b")  # 2 actions this week -> leafy-stem
    resp = test_client.get("/progress")
    assert b"growth-stage-svg" in resp.data
    assert b"Your momentum is taking root." in resp.data


def test_mark_complete_still_logs_exactly_one_action_with_growth_trail_present(client):
    """Regression check: adding the growth trail / bloom markup must not
    change the underlying completion logging behavior."""
    test_client, _ = client
    test_client.post("/today/complete")
    test_client.post("/today/complete")
    test_client.post("/today/complete")
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 1
