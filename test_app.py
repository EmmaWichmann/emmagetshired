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
    assert b"Career Opportunity Decoder" in resp.data
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
        assert b'class="growth-trail' in resp.data
        assert b'aria-hidden="true"' in resp.data
        assert b"trail-stem" in resp.data


def test_tools_page_uses_short_trail_variant(client):
    test_client, _ = client
    resp = test_client.get("/tools")
    assert b"trail-short" in resp.data


def test_today_uses_full_trail_variant_not_short(client):
    test_client, _ = client
    resp = test_client.get("/today")
    assert b"trail-short" not in resp.data


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
    assert b"growth-trail-svg" in resp.data
    assert b"stage-leaf-a" in resp.data
    assert b"stage-leaf-b" in resp.data
    assert b"Your momentum is taking root." in resp.data


def test_progress_stage_terminal_matches_each_weekly_range(client):
    test_client, _ = client
    test_client.get("/today")
    uid = test_client.get_cookie("uid").value

    resp = test_client.get("/progress")
    assert b"stage-seed" in resp.data  # 0 actions

    db.log_career_action(uid, "speech", "a")
    resp = test_client.get("/progress")
    assert b"stage-sprout" in resp.data  # 1 action

    db.log_career_action(uid, "speech", "b")
    db.log_career_action(uid, "speech", "c")
    db.log_career_action(uid, "speech", "d")
    resp = test_client.get("/progress")
    assert b"stage-bud" in resp.data  # 4 actions

    db.log_career_action(uid, "speech", "e")
    db.log_career_action(uid, "speech", "f")
    resp = test_client.get("/progress")
    assert b"stage-flower" in resp.data  # 6 actions


def test_mark_complete_still_logs_exactly_one_action_with_growth_trail_present(client):
    """Regression check: adding the growth trail / bloom markup must not
    change the underlying completion logging behavior."""
    test_client, _ = client
    test_client.post("/today/complete")
    test_client.post("/today/complete")
    test_client.post("/today/complete")
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 1


# ---------------------------------------------------------------------------
# ERROR HANDLING — expected HTTP errors (404/405) must keep their real
# status code instead of being collapsed into the catch-all 500 page;
# genuinely unexpected exceptions still get logged and shown the friendly
# error page, with no internal details leaked to the browser.
# ---------------------------------------------------------------------------

def test_missing_route_returns_404_not_500(client):
    test_client, _ = client
    resp = test_client.get("/this-route-does-not-exist-at-all")
    assert resp.status_code == 404
    # confirms it's Werkzeug's own 404, not the app's custom 500 error page
    assert b"oops" not in resp.data


def test_get_on_today_complete_post_only_route_returns_405(client):
    test_client, _ = client
    resp = test_client.get("/today/complete")
    assert resp.status_code == 405


def test_get_on_linkedin_generate_post_only_route_returns_405(client):
    test_client, _ = client
    resp = test_client.get("/tools/linkedin/generate")
    assert resp.status_code == 405


def test_unexpected_exception_returns_500_with_friendly_page_and_no_leak(client):
    test_client, app_module = client
    # TESTING=True normally re-raises exceptions instead of invoking the
    # error handler — disable that so this test exercises the real
    # request/error-handling path, not just a direct function call.
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = False

    @app_module.app.route("/__test_boom__")
    def _boom():
        raise RuntimeError("simulated unexpected failure - should never reach the browser")

    resp = test_client.get("/__test_boom__")
    assert resp.status_code == 500
    assert b"oops" in resp.data
    assert b"Something broke" in resp.data
    # no stack trace, exception type, or internal message leaked
    assert b"RuntimeError" not in resp.data
    assert b"Traceback" not in resp.data
    assert b"simulated unexpected failure" not in resp.data


def test_unexpected_exception_is_still_logged(client, monkeypatch):
    test_client, app_module = client
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = False

    logged_messages = []
    monkeypatch.setattr(app_module.logger, "error", lambda msg: logged_messages.append(msg))

    @app_module.app.route("/__test_boom_logging__")
    def _boom_logging():
        raise RuntimeError("simulated failure for the logging check")

    resp = test_client.get("/__test_boom_logging__")
    assert resp.status_code == 500
    assert any("simulated failure for the logging check" in m for m in logged_messages)


# ---------------------------------------------------------------------------
# CAREER OPPORTUNITY DECODER
# ---------------------------------------------------------------------------

SAMPLE_POSTING = """
Frontend Developer
Location: San Diego, CA
Illumina is hiring a Frontend Developer to join our growing engineering team.

What You'll Do
- Design and build responsive web interfaces using JavaScript, HTML, and CSS
- Collaborate with cross-functional teams including design and product
- Own the frontend architecture for a key internal tool

Requirements
- 3+ years of experience in frontend development
- Required: strong knowledge of JavaScript and Git

This is a hybrid position.
Compensation: $95,000 - $120,000 per year
"""


def test_opportunity_decoder_page_shows_disclaimer_and_privacy_note(client):
    test_client, _ = client
    resp = test_client.get("/tools/opportunity-decoder")
    assert resp.status_code == 200
    assert b"does not predict whether you will be hired" in resp.data
    assert b"is analyzed for this request and is not permanently stored" in resp.data


def test_opening_decoder_page_does_not_log_a_career_action(client):
    test_client, _ = client
    test_client.get("/tools/opportunity-decoder")
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 0


def test_empty_posting_submission_shows_error_and_does_not_log(client):
    test_client, _ = client
    resp = test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": ""})
    assert resp.status_code == 200
    assert b"Paste a job posting" in resp.data
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 0


def test_too_short_posting_submission_shows_error_and_does_not_log(client):
    test_client, _ = client
    resp = test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": "too short"})
    assert resp.status_code == 200
    assert b"too short to decode" in resp.data
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 0


def test_successful_decode_shows_all_result_sections(client):
    test_client, _ = client
    resp = test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    assert resp.status_code == 200
    assert b"Extracted details" in resp.data
    assert b"What you would likely do" in resp.data
    assert b"Required qualifications" in resp.data
    assert b"Preferred qualifications" in resp.data
    assert b"Technical and domain skills" in resp.data
    assert b"Questions to investigate" in resp.data
    assert b"Career value" in resp.data
    assert b"Recommended next action" in resp.data
    assert b"Illumina" in resp.data


def test_successful_decode_logs_exactly_one_job_review_action(client):
    test_client, _ = client
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_counts_by_type(uid).get("job_review") == 1


def test_refresh_resubmission_does_not_create_a_duplicate_log(client):
    test_client, _ = client
    # simulates the browser resubmitting the identical form on refresh
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_counts_by_type(uid).get("job_review") == 1


def test_decoding_a_different_posting_the_same_day_logs_again(client):
    test_client, _ = client
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    other_posting = "Backend Engineer\nWe are hiring a backend engineer with Python and SQL experience."
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": other_posting})
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_counts_by_type(uid).get("job_review") == 2


def test_decoder_page_never_leaks_posting_text_to_a_different_user(client):
    test_client, app_module = client
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})

    with app_module.app.test_client() as other_client:
        resp = other_client.get("/tools/opportunity-decoder")
        # a distinctive phrase from the posting body — not the "e.g. Illumina"
        # placeholder hint that's shown to every visitor regardless of input
        assert b"growing engineering team" not in resp.data


def test_career_tools_card_for_decoder_is_active_not_coming_next(client):
    test_client, _ = client
    resp = test_client.get("/tools")
    assert b'href="/tools/opportunity-decoder"' in resp.data
    assert b"Coming Next" not in resp.data


def test_today_review_job_action_links_to_opportunity_decoder(client):
    _, app_module = client
    review_job = next(a for a in app_module.TODAY_ACTIONS if a["id"] == "review-job")
    assert review_job["cta_endpoint"] == "opportunity_decoder_tool"
    assert review_job["action_type"] == "job_review"


def test_today_page_links_to_opportunity_decoder_when_that_is_the_days_action(client, monkeypatch):
    test_client, app_module = client
    review_job = next(a for a in app_module.TODAY_ACTIONS if a["id"] == "review-job")
    monkeypatch.setattr(app_module, "get_today_action", lambda: review_job)
    resp = test_client.get("/today")
    assert b'href="/tools/opportunity-decoder"' in resp.data


def test_progress_counts_job_review_actions_from_the_decoder(client):
    test_client, _ = client
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    uid = test_client.get_cookie("uid").value
    assert db.get_career_action_count_this_week(uid) == 1


def test_progress_most_consistent_activity_can_be_job_review(client):
    test_client, _ = client
    other_posting = "Backend Engineer\nWe are hiring a backend engineer with Python and SQL experience."
    third_posting = "Data Analyst\nWe are hiring a data analyst with SQL and Python skills."
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": SAMPLE_POSTING})
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": other_posting})
    test_client.post("/tools/opportunity-decoder/decode", data={"posting_text": third_posting})
    resp = test_client.get("/progress")
    assert b"kept up with Job description reviews" in resp.data
