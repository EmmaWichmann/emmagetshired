"""
test_opportunity_decoder.py
-----------------------------
Run with:  pytest test_opportunity_decoder.py -v

Unit tests for opportunity_decoder.py — extraction, classification, and
next-action logic. No Flask, no database.
"""

import opportunity_decoder as decoder


RICH_POSTING = """
Frontend Developer
Location: San Diego, CA
Illumina is hiring a Frontend Developer to join our growing engineering team.

What You'll Do
- Design and build responsive web interfaces using JavaScript, HTML, and CSS
- Collaborate with cross-functional teams including design and product
- Own the frontend architecture for a key internal tool
- Mentor junior engineers as the team grows

Requirements
- 3+ years of experience in frontend development
- Bachelor's degree in Computer Science or related field
- Required: strong knowledge of JavaScript, Git, and testing practices
- You have experience with SQL and data analysis

Preferred Qualifications
- Experience with Python and Flask
- Familiarity with AWS
- Nice to have: exposure to machine learning projects

This is a hybrid position with occasional travel (up to 10%).
Compensation: $95,000 - $120,000 per year
This role offers real career growth and a clear path to a senior engineering position.
"""


# ---------------------------------------------------------------------------
# EMPTY POSTING VALIDATION
# ---------------------------------------------------------------------------

def test_empty_posting_is_too_short():
    assert decoder.is_posting_too_short("") is True


def test_short_junk_posting_is_too_short():
    assert decoder.is_posting_too_short("hi there") is True


def test_real_posting_is_not_too_short():
    assert decoder.is_posting_too_short(RICH_POSTING) is False


# ---------------------------------------------------------------------------
# JOB TITLE / COMPANY / LOCATION
# ---------------------------------------------------------------------------

def test_job_title_extraction_from_first_line():
    assert decoder.extract_job_title(RICH_POSTING) == "Frontend Developer"


def test_job_title_extraction_from_label():
    text = "Job Title: Backend Engineer\nSome other content here."
    assert decoder.extract_job_title(text) == "Backend Engineer"


def test_job_title_provided_by_user_wins():
    assert decoder.extract_job_title(RICH_POSTING, provided_title="Custom Title") == "Custom Title"


def test_company_extraction_is_hiring_phrase():
    assert decoder.extract_company(RICH_POSTING) == "Illumina"


def test_company_extraction_from_label():
    text = "Company: Acme Corp\nWe are looking for a developer."
    assert decoder.extract_company(text) == "Acme Corp"


def test_company_extraction_at_phrase():
    text = "Join our team at Globex Corporation as a developer."
    assert decoder.extract_company(text) == "Globex Corporation"


def test_company_provided_by_user_wins():
    assert decoder.extract_company(RICH_POSTING, provided_company="My Company") == "My Company"


def test_company_extraction_does_not_cross_line_breaks():
    text = "Location: San Diego, CA\nAcme is hiring engineers."
    assert decoder.extract_company(text) == "Acme"


def test_location_extraction_from_label():
    assert decoder.extract_location(RICH_POSTING) == "San Diego, CA"


def test_location_extraction_city_state_pattern():
    text = "This role is based in Austin, TX and offers relocation assistance."
    assert decoder.extract_location(text) == "Austin, TX"


def test_location_missing_returns_empty():
    assert decoder.extract_location("A posting with no location info at all.") == ""


# ---------------------------------------------------------------------------
# WORK ARRANGEMENT DETECTION
# ---------------------------------------------------------------------------

def test_remote_detection():
    assert decoder.detect_work_arrangement("This is a fully remote position.") == "Remote"


def test_hybrid_detection():
    assert decoder.detect_work_arrangement("This is a hybrid role, in office 3 days a week.") == "Hybrid"


def test_hybrid_takes_priority_over_remote_mention():
    text = "This is a hybrid role with some remote flexibility."
    assert decoder.detect_work_arrangement(text) == "Hybrid"


def test_on_site_detection():
    assert decoder.detect_work_arrangement("This position is on-site at our headquarters.") == "On site"


def test_work_arrangement_not_stated():
    assert decoder.detect_work_arrangement("We are looking for a great teammate.") == decoder.NOT_STATED


# ---------------------------------------------------------------------------
# SALARY EXTRACTION
# ---------------------------------------------------------------------------

def test_salary_extraction_range():
    assert decoder.extract_salary(RICH_POSTING) == "$95,000 - $120,000"


def test_salary_extraction_hourly():
    assert "$" in decoder.extract_salary("This role pays $45/hour.")


def test_salary_extraction_k_shorthand():
    text = "Compensation is 90k-110k depending on experience."
    assert decoder.extract_salary(text) == "90k-110k"


def test_salary_missing_returns_empty():
    assert decoder.extract_salary("No compensation details are listed here.") == ""


# ---------------------------------------------------------------------------
# EMPLOYMENT TYPE DETECTION
# ---------------------------------------------------------------------------

def test_employment_type_full_time():
    assert decoder.detect_employment_type("This is a full-time position.") == "Full time"


def test_employment_type_part_time():
    assert decoder.detect_employment_type("This is a part-time role.") == "Part time"


def test_employment_type_contract():
    assert decoder.detect_employment_type("This is a 6-month contract position.") == "Contract"


def test_employment_type_internship():
    assert decoder.detect_employment_type("Summer internship opportunity.") == "Internship"


def test_employment_type_temporary():
    assert decoder.detect_employment_type("This is a temporary position.") == "Temporary"


def test_employment_type_not_stated():
    assert decoder.detect_employment_type("We are looking for a great teammate.") == decoder.NOT_STATED


# ---------------------------------------------------------------------------
# EXPERIENCE / EDUCATION / TRAVEL EXTRACTION
# ---------------------------------------------------------------------------

def test_experience_extraction():
    assert decoder.extract_experience(RICH_POSTING) == "3+ years of experience"


def test_experience_missing_returns_empty():
    assert decoder.extract_experience("No experience requirements listed.") == ""


def test_education_extraction():
    assert "Bachelor" in decoder.extract_education(RICH_POSTING)


def test_education_missing_returns_empty():
    assert decoder.extract_education("This posting says nothing about a degree.") == ""


def test_travel_extraction_percentage():
    assert "10" in decoder.extract_travel("This role requires up to 10% travel.")


def test_travel_extraction_none():
    assert decoder.extract_travel("This role requires no travel.") == "No travel required"


def test_travel_extraction_extensive():
    assert decoder.extract_travel("This role requires extensive travel.") == "Extensive travel required"


def test_travel_missing_returns_empty():
    assert decoder.extract_travel("Nothing about travel here.") == ""


# ---------------------------------------------------------------------------
# RESPONSIBILITY / QUALIFICATION EXTRACTION
# ---------------------------------------------------------------------------

def test_responsibility_extraction_from_section():
    responsibilities = decoder.extract_responsibilities(RICH_POSTING)
    assert any("Design and build" in r for r in responsibilities)
    assert any("Mentor junior engineers" in r for r in responsibilities)


def test_responsibility_extraction_fallback_lead_verbs():
    text = "Build scalable systems. Manage a small team. Some other unrelated sentence about lunch."
    responsibilities = decoder.extract_responsibilities(text)
    assert any("Build scalable systems" in r for r in responsibilities)
    assert any("Manage a small team" in r for r in responsibilities)


def test_required_qualification_extraction():
    required = decoder.extract_required_qualifications(RICH_POSTING)
    assert any("3+ years" in r for r in required)
    assert any("Bachelor" in r for r in required)


def test_required_qualification_section_heading_not_included():
    required = decoder.extract_required_qualifications(RICH_POSTING)
    assert not any(r.strip() == "Requirements" for r in required)


def test_preferred_qualification_extraction():
    preferred = decoder.extract_preferred_qualifications(RICH_POSTING)
    assert any("Python and Flask" in p for p in preferred)
    assert any("AWS" in p for p in preferred)


def test_preferred_qualification_does_not_bleed_into_trailing_content():
    preferred = decoder.extract_preferred_qualifications(RICH_POSTING)
    joined = " ".join(preferred)
    assert "hybrid position" not in joined.lower()
    assert "95,000" not in joined


def test_preferred_qualification_heading_not_included():
    preferred = decoder.extract_preferred_qualifications(RICH_POSTING)
    assert not any(p.strip() == "Preferred Qualifications" for p in preferred)


# ---------------------------------------------------------------------------
# SUPPORTED SKILL DETECTION
# ---------------------------------------------------------------------------

def test_supported_skills_detected_with_punctuation_attached():
    text = "We use Python, SQL, JavaScript, HTML, and CSS. Git and Flask experience is a plus."
    skills = decoder.detect_skills(text)
    for expected in ("Python", "SQL", "JavaScript", "HTML", "CSS", "Git", "Flask"):
        assert expected in skills


def test_unsupported_skills_never_appear():
    text = "We need someone skilled in Kubernetes, Rust, Go, Python, and SQL. Docker experience is a plus."
    skills = decoder.detect_skills(text)
    for unsupported in ("Kubernetes", "Rust", "Go", "Docker"):
        assert unsupported not in skills
    assert "Python" in skills
    assert "SQL" in skills


def test_no_skills_found_returns_empty_list():
    assert decoder.detect_skills("A posting about baking bread and nothing technical.") == []


def test_skill_word_boundary_does_not_false_positive():
    # "css" must not match inside "process" or "success"
    text = "We value process improvement and customer success."
    assert "CSS" not in decoder.detect_skills(text)


# ---------------------------------------------------------------------------
# MISSING-INFORMATION QUESTIONS
# ---------------------------------------------------------------------------

def _base_details(**overrides):
    details = {
        "salary": "$100,000",
        "work_arrangement": "Remote",
        "travel": "No travel required",
        "responsibilities": ["a", "b"],
        "required_qualifications": ["x"],
        "preferred_qualifications": [],
        "text": "This role includes a training program and mentorship.",
    }
    details.update(overrides)
    return details


def test_no_questions_when_everything_is_clear():
    assert decoder.generate_questions(_base_details()) == []


def test_question_for_missing_salary():
    assert "What is the expected salary range?" in decoder.generate_questions(_base_details(salary=""))


def test_question_for_unclear_work_arrangement():
    questions = decoder.generate_questions(_base_details(work_arrangement=decoder.NOT_STATED))
    assert "Is this position remote, hybrid, or on site?" in questions


def test_question_for_missing_travel():
    assert "How much travel is required?" in decoder.generate_questions(_base_details(travel=""))


def test_question_for_thin_responsibilities():
    questions = decoder.generate_questions(_base_details(responsibilities=["only one"]))
    assert "What does success during the first 90 days look like?" in questions


def test_question_for_no_qualifications_at_all():
    questions = decoder.generate_questions(_base_details(required_qualifications=[], preferred_qualifications=[]))
    assert "Is this a newly created role or a replacement?" in questions


def test_question_for_missing_mentorship_language():
    questions = decoder.generate_questions(_base_details(text="A posting with no growth language at all."))
    assert "What training or mentorship is available?" in questions


# ---------------------------------------------------------------------------
# CAREER VALUE CLASSIFICATION
# ---------------------------------------------------------------------------

def test_career_accelerator_classification():
    positive = [
        "ownership or decision making", "mentorship or training",
        "cross-functional collaboration", "clear advancement language",
    ]
    result = decoder.classify_career_value(positive, [])
    assert result["classification"] == "Career accelerator"
    assert 2 <= len(result["reasons"]) <= 4


def test_strategic_stepping_stone_classification():
    positive = ["ownership or decision making", "mentorship or training"]
    result = decoder.classify_career_value(positive, [])
    assert result["classification"] == "Strategic stepping stone"


def test_lateral_opportunity_classification():
    result = decoder.classify_career_value([], [])
    assert result["classification"] == "Lateral opportunity"
    assert 2 <= len(result["reasons"]) <= 4  # generic fallbacks still fill 2-4


def test_low_return_opportunity_classification_from_two_concerns():
    concerns = ["heavy travel without clear value", "extremely vague responsibilities"]
    result = decoder.classify_career_value([], concerns)
    assert result["classification"] == "Low return opportunity"


def test_single_concern_alone_is_not_low_return_unless_unpaid_or_commission():
    # exactly one concern, no unpaid/commission trigger -> must NOT be Low return
    result = decoder.classify_career_value(["salary transparency"], ["heavy travel without clear value"])
    assert result["classification"] != "Low return opportunity"


def test_unpaid_opportunity_is_always_low_return():
    # even with strong positive signals, unpaid work forces Low return
    positive = ["ownership or decision making", "mentorship or training", "leadership potential", "clear advancement language"]
    result = decoder.classify_career_value(positive, ["unpaid work"])
    assert result["classification"] == "Low return opportunity"
    assert "unpaid work" in result["reasons"]


def test_commission_only_is_always_low_return():
    result = decoder.classify_career_value(["salary transparency"], ["commission only compensation"])
    assert result["classification"] == "Low return opportunity"
    assert "commission only compensation" in result["reasons"]


def test_classification_never_shows_a_numeric_score():
    result = decoder.classify_career_value(["ownership or decision making"], [])
    assert isinstance(result["classification"], str)
    assert "%" not in result["explanation"]


def test_classification_reasons_always_two_to_four_items():
    for positive, concerns in [([], []), (["a"], []), (["a", "b", "c", "d", "e"], []), ([], ["unpaid work"])]:
        result = decoder.classify_career_value(positive, concerns)
        assert 2 <= len(result["reasons"]) <= 4


# ---------------------------------------------------------------------------
# RECOMMENDED NEXT ACTION
# ---------------------------------------------------------------------------

def test_next_action_apply_now_for_accelerator_with_full_info():
    details = {"salary": "$100k", "work_arrangement": "Remote", "employment_type": "Full time", "location": "San Diego, CA"}
    action, _ = decoder.recommend_next_action("Career accelerator", details)
    assert action == "Apply now"


def test_next_action_research_before_applying_for_accelerator_missing_info():
    details = {"salary": "", "work_arrangement": "Remote", "employment_type": "Full time", "location": "San Diego, CA"}
    action, _ = decoder.recommend_next_action("Career accelerator", details)
    assert action == "Research before applying"


def test_next_action_save_for_later_for_stepping_stone():
    details = {"salary": "$100k", "work_arrangement": "Remote", "employment_type": "Full time", "location": "San Diego, CA"}
    action, _ = decoder.recommend_next_action("Strategic stepping stone", details)
    assert action == "Save for later"


def test_next_action_skip_for_now_for_low_return():
    details = {"salary": "", "work_arrangement": decoder.NOT_STATED, "employment_type": decoder.NOT_STATED, "location": ""}
    action, _ = decoder.recommend_next_action("Low return opportunity", details)
    assert action == "Skip for now"


def test_next_action_never_claims_the_user_is_qualified():
    for classification in ("Career accelerator", "Strategic stepping stone", "Lateral opportunity", "Low return opportunity"):
        details = {"salary": "$100k", "work_arrangement": "Remote", "employment_type": "Full time", "location": "San Diego, CA"}
        _, explanation = decoder.recommend_next_action(classification, details)
        assert "qualified" not in explanation.lower()


# ---------------------------------------------------------------------------
# FULL ORCHESTRATION
# ---------------------------------------------------------------------------

def test_decode_opportunity_full_posting():
    result = decoder.decode_opportunity(RICH_POSTING)
    assert result["job_title"] == "Frontend Developer"
    assert result["company"] == "Illumina"
    assert result["location"] == "San Diego, CA"
    assert result["work_arrangement"] == "Hybrid"
    assert result["classification"] in (
        "Career accelerator", "Strategic stepping stone", "Lateral opportunity", "Low return opportunity",
    )
    assert result["next_action"] in ("Apply now", "Research before applying", "Save for later", "Skip for now")


def test_decode_opportunity_missing_fields_show_not_clearly_stated():
    result = decoder.decode_opportunity("We are looking for a great teammate to join us.")
    assert result["salary"] == decoder.NOT_STATED
    assert result["work_arrangement"] == decoder.NOT_STATED
    assert result["employment_type"] == decoder.NOT_STATED
    assert result["travel"] == decoder.NOT_STATED
    assert result["experience"] == decoder.NOT_STATED
    assert result["education"] == decoder.NOT_STATED


def test_posting_fingerprint_is_stable_and_deterministic():
    assert decoder.posting_fingerprint(RICH_POSTING) == decoder.posting_fingerprint(RICH_POSTING)


def test_posting_fingerprint_differs_for_different_postings():
    assert decoder.posting_fingerprint(RICH_POSTING) != decoder.posting_fingerprint("A totally different posting.")


def test_posting_fingerprint_never_contains_the_posting_text():
    fingerprint = decoder.posting_fingerprint(RICH_POSTING)
    assert "Frontend Developer" not in fingerprint
    assert len(fingerprint) == 10
