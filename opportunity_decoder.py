"""
opportunity_decoder.py
------------------------
Deterministic Python text processing (regex + keyword matching, no
external AI API) that turns one pasted job posting into: extracted facts,
a breakdown of the posting, questions worth investigating, a career-value
classification, and one recommended next action.

This is NOT a resume matcher — nothing here compares the posting to a
resume, and nothing here predicts whether the user will be hired. Every
extracted detail is either a literal regex match against the posting text
or a short excerpt of it; when something isn't found, it's reported as
"Not clearly stated" rather than guessed at.

Every function below is small and independently testable — see
test_opportunity_decoder.py.
"""

import hashlib
import re

NOT_STATED = "Not clearly stated"


# ---------------------------------------------------------------------------
# NORMALIZATION
# ---------------------------------------------------------------------------

def normalize_whitespace(text):
    """Collapses whitespace/blank-line runs but preserves original casing
    and line structure otherwise — most extraction below needs to see the
    text roughly the way it was written (line breaks matter for section
    detection and bullet parsing)."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def lowered(text):
    """The normalized, lowercased form used for case-insensitive keyword
    and phrase matching."""
    return normalize_whitespace(text).lower()


def is_posting_too_short(text):
    """Fewer than 8 words isn't a real job posting — used by the route to
    show a friendly validation message instead of decoding noise."""
    return len((text or "").split()) < 8


def posting_fingerprint(text):
    """A short, one-way fingerprint of the posting text — never the text
    itself. Used only to detect 'this is the exact same submission again'
    (e.g. a browser refresh resubmitting the form) without storing or
    reversing the original posting."""
    normalized = normalize_whitespace(text).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:10]


def _contains_term(text_lower, term):
    """Word-bounded substring check using regex \\b, not naive space
    padding — \\b correctly treats punctuation (commas, periods) as a
    word boundary too, so "Python," or "SQL." still match "python"/"sql"
    without needing to strip punctuation out of the source text first."""
    return re.search(r"\b" + re.escape(term) + r"\b", text_lower) is not None


def _clean_bullet(line):
    line = line.strip()
    line = re.sub(r"^[-*••]\s*", "", line)
    line = re.sub(r"^\d+[.)]\s*", "", line)
    return line.strip()


def _truncate(text, max_len=160):
    """Short supporting excerpts only — never a large chunk of the
    posting."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def extract_sentences(text):
    """Splits the posting into individual candidate sentences/bullets:
    one per line, with any multi-sentence line further split on
    end-of-sentence punctuation. Bullet markers and numbering are
    stripped, and lines that are themselves a recognized section heading
    (e.g. "Preferred Qualifications") are excluded — otherwise a heading
    that happens to contain a trigger word like "preferred" would get
    picked up as if it were a qualification sentence. This is the base
    unit every qualification/responsibility extractor scans."""
    sentences = []
    for line in normalize_whitespace(text).splitlines():
        if line.strip().rstrip(":").lower() in SECTION_HEADING_ALIASES:
            continue
        line = _clean_bullet(line)
        if not line:
            continue
        for piece in re.split(r"(?<=[.!?])\s+", line):
            piece = piece.strip()
            if piece:
                sentences.append(piece)
    return sentences


# ---------------------------------------------------------------------------
# SECTION DETECTION — same transparent, whitelist-only approach used by
# the earlier resume parser: a line is a heading only if it exactly
# matches (case/colon insensitive) a known variant, so a bullet like
# "Requirements gathering experience" is never mistaken for the
# "Requirements" heading itself.
# ---------------------------------------------------------------------------

SECTION_HEADING_ALIASES = {
    "responsibilities": "responsibilities",
    "what you'll do": "responsibilities",
    "what you will do": "responsibilities",
    "the role": "responsibilities",
    "about the role": "responsibilities",
    "job duties": "responsibilities",
    "duties": "responsibilities",
    "key responsibilities": "responsibilities",
    "what you'll be doing": "responsibilities",
    "role and responsibilities": "responsibilities",

    "requirements": "required",
    "required qualifications": "required",
    "qualifications": "required",
    "minimum qualifications": "required",
    "basic qualifications": "required",
    "must haves": "required",
    "what you'll need": "required",
    "what you need": "required",
    "skills and experience": "required",
    "who you are": "required",

    "preferred qualifications": "preferred",
    "nice to have": "preferred",
    "nice-to-haves": "preferred",
    "bonus points": "preferred",
    "preferred": "preferred",
    "ideal candidate": "preferred",
}


def detect_sections(text):
    """Returns {"responsibilities": [...], "required": [...], "preferred": [...]},
    each a list of raw lines found under that heading. Lines before any
    recognized heading, or under an unrecognized one, aren't assigned to
    any bucket here (extraction functions fall back to whole-document
    keyword scanning when a bucket is empty).

    A blank line closes out whatever section is currently open. Job
    postings are typically a tight bulleted list per section with no
    internal blank lines, so this keeps a section's own trailing blank
    line (before the next heading, or before unrelated closing
    paragraphs like salary/travel notes) from letting unrelated content
    bleed into the last section seen."""
    buckets = {"responsibilities": [], "required": [], "preferred": []}
    current = None
    for line in normalize_whitespace(text).splitlines():
        if not line.strip():
            current = None
            continue
        key = line.strip().rstrip(":").lower()
        canonical = SECTION_HEADING_ALIASES.get(key)
        if canonical:
            current = canonical
            continue
        if current:
            buckets[current].append(line.strip())
    return buckets


# ---------------------------------------------------------------------------
# JOB TITLE / COMPANY / LOCATION
# ---------------------------------------------------------------------------

_JOB_TITLE_LABEL = re.compile(r"(?im)^\s*(?:job title|position|role|title)\s*:\s*(.+)$")
_COMPANY_LABEL = re.compile(r"(?im)^\s*(?:company|employer|organization)\s*:\s*(.+)$")
_AT_COMPANY = re.compile(r"\bat[ \t]+([A-Z][A-Za-z0-9&.,'-]{1,40}(?:[ \t]+[A-Z][A-Za-z0-9&.,'-]{1,40}){0,3})")
_COMPANY_IS_HIRING = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,'-]{1,40}(?:[ \t]+[A-Z][A-Za-z0-9&.,'-]{1,40}){0,3})[ \t]+is[ \t]+(?:hiring|looking for|seeking)\b"
)
_JOIN_COMPANY = re.compile(r"\bjoin[ \t]+([A-Z][A-Za-z0-9&.,'-]{1,40}(?:[ \t]+[A-Z][A-Za-z0-9&.,'-]{1,40}){0,3})\b")
_LOCATION_LABEL = re.compile(r"(?im)^\s*location\s*:\s*(.+)$")
_CITY_STATE = re.compile(r"\b([A-Z][a-zA-Z.]+(?:\s[A-Z][a-zA-Z.]+)*),\s*([A-Z]{2})\b")


def extract_job_title(text, provided_title=""):
    """A user-supplied title is always trusted first. Otherwise, look for
    a 'Job Title:' style label, then fall back to the first line if it's
    short and doesn't read like a sentence (a common posting convention:
    the title stands alone on line 1)."""
    if provided_title and provided_title.strip():
        return provided_title.strip()
    text = normalize_whitespace(text)
    m = _JOB_TITLE_LABEL.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    lines = text.splitlines()
    if lines:
        first_line = lines[0].strip()
        if first_line and len(first_line) <= 80 and not first_line.endswith((".", ":")):
            return first_line
    return ""


def extract_company(text, provided_company=""):
    if provided_company and provided_company.strip():
        return provided_company.strip()
    text = normalize_whitespace(text)
    m = _COMPANY_LABEL.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = _COMPANY_IS_HIRING.search(text)
    if m:
        return m.group(1).strip().rstrip(".,")
    m = _AT_COMPANY.search(text)
    if m:
        return m.group(1).strip().rstrip(".,")
    m = _JOIN_COMPANY.search(text)
    if m:
        return m.group(1).strip().rstrip(".,")
    return ""


def extract_location(text):
    text = normalize_whitespace(text)
    m = _LOCATION_LABEL.search(text)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m = _CITY_STATE.search(text)
    if m:
        return f"{m.group(1)}, {m.group(2)}"
    return ""


# ---------------------------------------------------------------------------
# WORK ARRANGEMENT / EMPLOYMENT TYPE
# ---------------------------------------------------------------------------

def detect_work_arrangement(text):
    """Hybrid is checked before remote, since a posting mentioning both
    ('hybrid, remote 2 days a week') is describing a hybrid arrangement,
    not a fully remote one."""
    lower = lowered(text)
    if re.search(r"\bhybrid\b", lower):
        return "Hybrid"
    if re.search(r"\bremote\b", lower):
        return "Remote"
    if re.search(r"\b(on[- ]site|onsite|in[- ]office|on location)\b", lower):
        return "On site"
    return NOT_STATED


def detect_employment_type(text):
    """Narrower categories are checked first — a posting can describe
    itself as e.g. 'full-time contract', in which case 'contract' is the
    more specific, useful signal."""
    lower = lowered(text)
    if re.search(r"\bintern(ship)?\b", lower):
        return "Internship"
    if re.search(r"\btemporary\b|\btemp\b", lower):
        return "Temporary"
    if re.search(r"\bcontract(or)?\b|\b1099\b", lower):
        return "Contract"
    if re.search(r"\bpart[- ]time\b", lower):
        return "Part time"
    if re.search(r"\bfull[- ]time\b", lower):
        return "Full time"
    return NOT_STATED


# ---------------------------------------------------------------------------
# SALARY / EXPERIENCE / EDUCATION / TRAVEL
# ---------------------------------------------------------------------------

_SALARY_PATTERNS = [
    # a dollar range: $95,000 - $120,000, $45-$50/hr, $90k - $110k
    re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?[kK]?\s?(?:-|to|–|—)\s?\$?\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?[kK]?(?:\s?/\s?(?:year|yr|hour|hr|annum))?"),
    # a single dollar figure: $95,000, $45/hour, $22.50
    re.compile(r"\$\s?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?[kK]?(?:\s?/\s?(?:year|yr|hour|hr|annum))?"),
    # a plain k-shorthand range with no dollar sign: 90k-110k
    re.compile(r"\b\d{2,3}[kK]\s?(?:-|to|–|—)\s?\d{2,3}[kK]\b"),
]


def extract_salary(text):
    text = normalize_whitespace(text)
    for pattern in _SALARY_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return ""


_EXPERIENCE_PATTERN = re.compile(
    r"\b\d+\+?\s?(?:(?:-|to|–)\s?\d+\+?\s?)?years?\s+(?:of\s+)?experience\b", re.I
)


def extract_experience(text):
    m = _EXPERIENCE_PATTERN.search(normalize_whitespace(text))
    return m.group(0).strip() if m else ""


_EDUCATION_PATTERN = re.compile(
    r"\b(?:Bachelor'?s?|Master'?s?|Ph\.?D\.?|Doctorate|Associate'?s?|B\.?S\.?|M\.?S\.?|B\.?A\.?|M\.?A\.?|M\.?B\.?A\.?)\b[^.\n]{0,80}",
    re.I,
)


def extract_education(text):
    m = _EDUCATION_PATTERN.search(normalize_whitespace(text))
    return m.group(0).strip() if m else ""


def extract_travel(text):
    lower = lowered(text)
    m = re.search(r"\b(?:up to\s+)?\d{1,3}\s?%\s+travel\b", lower)
    if m:
        return m.group(0).strip()
    if re.search(r"\bno travel\b|\btravel is not required\b", lower):
        return "No travel required"
    if re.search(r"\bextensive travel\b|\bfrequent travel\b|\bsignificant travel\b|\bheavy travel\b", lower):
        return "Extensive travel required"
    if re.search(r"\bminimal travel\b|\bsome travel\b|\boccasional travel\b|\blight travel\b", lower):
        return "Some travel required"
    if re.search(r"\btravel required\b|\brequires travel\b", lower):
        return "Travel required"
    return ""


# ---------------------------------------------------------------------------
# RESPONSIBILITIES / REQUIRED / PREFERRED QUALIFICATIONS
# ---------------------------------------------------------------------------

_RESPONSIBILITY_LEAD_VERBS = (
    "design", "build", "develop", "manage", "lead", "own", "create", "collaborate",
    "analyze", "support", "maintain", "coordinate", "partner", "drive", "conduct",
    "write", "implement", "improve", "oversee", "plan", "deliver", "monitor",
)


def extract_responsibilities(text, limit=6):
    """Prefers an explicit 'Responsibilities' style section; if the
    posting doesn't have one, falls back to sentences elsewhere that open
    with a common responsibility verb (e.g. 'Design and build...')."""
    sections = detect_sections(text)
    lines = [_clean_bullet(l) for l in sections["responsibilities"]]
    lines = [l for l in lines if l]

    if not lines:
        for sentence in extract_sentences(text):
            first_word = sentence.split(" ", 1)[0].lower().strip(",.:;")
            if first_word in _RESPONSIBILITY_LEAD_VERBS:
                lines.append(sentence)

    deduped = list(dict.fromkeys(_truncate(l) for l in lines if l))
    return deduped[:limit]


_REQUIRED_TRIGGERS = [r"\brequired\b", r"\bmust have\b", r"\bminimum qualifications\b", r"\byou have\b", r"\bbasic qualifications\b"]
_PREFERRED_TRIGGERS = [r"\bpreferred\b", r"\bnice to have\b", r"\bbonus\b", r"\bdesired\b", r"\bideal candidate\b"]


def extract_required_qualifications(text, limit=6):
    sections = detect_sections(text)
    lines = [_truncate(_clean_bullet(l)) for l in sections["required"] if _clean_bullet(l)]

    for sentence in extract_sentences(text):
        if any(re.search(p, sentence.lower()) for p in _REQUIRED_TRIGGERS):
            lines.append(_truncate(sentence))

    return list(dict.fromkeys(lines))[:limit]


def extract_preferred_qualifications(text, limit=6):
    sections = detect_sections(text)
    lines = [_truncate(_clean_bullet(l)) for l in sections["preferred"] if _clean_bullet(l)]

    for sentence in extract_sentences(text):
        if any(re.search(p, sentence.lower()) for p in _PREFERRED_TRIGGERS):
            lines.append(_truncate(sentence))

    return list(dict.fromkeys(lines))[:limit]


# ---------------------------------------------------------------------------
# TECHNICAL / DOMAIN SKILL DETECTION — a skill is only ever reported if it
# literally appears in the posting (word-bounded substring match).
# ---------------------------------------------------------------------------

KNOWN_SKILLS = [
    "python", "sql", "javascript", "html", "css", "git", "flask", "aws", "azure",
    "saas", "artificial intelligence", "machine learning", "data analysis",
    "clinical research", "biotechnology", "medical devices", "project management",
    "customer success", "product management", "quality assurance", "testing",
    "documentation",
]

SKILL_DISPLAY_LABELS = {
    "python": "Python", "sql": "SQL", "javascript": "JavaScript", "html": "HTML",
    "css": "CSS", "git": "Git", "flask": "Flask", "aws": "AWS", "azure": "Azure",
    "saas": "SaaS", "artificial intelligence": "Artificial intelligence",
    "machine learning": "Machine learning", "data analysis": "Data analysis",
    "clinical research": "Clinical research", "biotechnology": "Biotechnology",
    "medical devices": "Medical devices", "project management": "Project management",
    "customer success": "Customer success", "product management": "Product management",
    "quality assurance": "Quality assurance", "testing": "Testing",
    "documentation": "Documentation",
}


def detect_skills(text):
    text_lower = lowered(text)
    return [SKILL_DISPLAY_LABELS[s] for s in KNOWN_SKILLS if _contains_term(text_lower, s)]


# ---------------------------------------------------------------------------
# QUESTIONS TO INVESTIGATE — each question is gated by one specific
# missing/unclear signal, so only relevant questions ever appear.
# ---------------------------------------------------------------------------

def generate_questions(details):
    """`details` is a dict with: salary, work_arrangement, travel,
    responsibilities, required_qualifications, preferred_qualifications,
    text (the raw posting, used only to check for mentorship/training
    language)."""
    questions = []

    if not details.get("salary"):
        questions.append("What is the expected salary range?")

    if details.get("work_arrangement") == NOT_STATED:
        questions.append("Is this position remote, hybrid, or on site?")

    if not details.get("travel"):
        questions.append("How much travel is required?")

    if len(details.get("responsibilities") or []) < 2:
        questions.append("What does success during the first 90 days look like?")

    if not details.get("required_qualifications") and not details.get("preferred_qualifications"):
        questions.append("Is this a newly created role or a replacement?")

    if not re.search(r"\bmentor(ship)?\b|\btraining\b|\bprofessional development\b|\bonboarding\b", lowered(details.get("text", ""))):
        questions.append("What training or mentorship is available?")

    return questions


# ---------------------------------------------------------------------------
# CAREER VALUE CLASSIFICATION — transparent, documented rule. Evaluates
# the opportunity's career value, never the user's odds of being hired.
# ---------------------------------------------------------------------------

POSITIVE_SIGNAL_PATTERNS = {
    "technical skill development": [r"\blearn\b", r"\bgrow your skills\b", r"\bdevelop your\b", r"\btraining\b", r"\bupskill"],
    "ownership or decision making": [r"\bownership\b", r"\bown the\b", r"\byou will own\b", r"\bautonomy\b", r"\bdecision[- ]making\b"],
    "cross-functional collaboration": [r"\bcross[- ]functional\b", r"\bcollaborate with\b", r"\bpartner with\b", r"\bwork closely with\b"],
    "mentorship or training": [r"\bmentor(ship)?\b", r"\btraining program\b", r"\bprofessional development\b", r"\bonboarding\b"],
    "exposure to products, systems, customers, or data": [r"\bcustomers?\b", r"\bend users?\b", r"\bproduction system\b", r"\breal[- ]world data\b", r"\bour platform\b", r"\bour product\b"],
    "leadership potential": [r"\bleadership\b", r"\blead a team\b", r"\bmanage a team\b", r"\bgrow into\b"],
    "clear advancement language": [r"\bcareer growth\b", r"\badvancement\b", r"\bpromot", r"\bcareer path\b", r"\bgrow your career\b"],
}


def detect_positive_signals(text, salary, skills):
    lower = lowered(text)
    found = [label for label, patterns in POSITIVE_SIGNAL_PATTERNS.items() if any(re.search(p, lower) for p in patterns)]
    if salary:
        found.append("salary transparency")
    if skills:
        found.append("relevant technology, biotech, healthtech, product, data, or AI exposure")
    return found


CONCERN_PATTERNS = {
    "unpaid work": [r"\bunpaid\b", r"\bno compensation\b", r"\bwithout pay\b", r"\bno salary\b"],
    "commission only compensation": [r"\bcommission[- ]only\b", r"\b100% commission\b", r"\bcommission based only\b"],
    "heavy travel without clear value": [r"\bextensive travel\b", r"\bfrequent travel\b", r"\bsignificant travel\b", r"\bheavy travel\b"],
    "repeated language suggesting many unrelated responsibilities": [r"\bother duties as assigned\b", r"\bwide range of tasks\b", r"\band other tasks as needed\b", r"\bvarious other duties\b"],
}

_GROWTH_RELATED_SIGNALS = {
    "technical skill development", "ownership or decision making",
    "mentorship or training", "leadership potential", "clear advancement language",
}


def detect_concerns(text, responsibilities, required_qualifications, employment_type, positive_signals):
    lower = lowered(text)
    concerns = [label for label, patterns in CONCERN_PATTERNS.items() if any(re.search(p, lower) for p in patterns)]

    if len(responsibilities) <= 1 and len(required_qualifications) <= 1:
        concerns.append("extremely vague responsibilities")

    if employment_type == "Temporary" and "technical skill development" not in positive_signals:
        concerns.append("temporary work with little skill development")

    if not (_GROWTH_RELATED_SIGNALS & set(positive_signals)):
        concerns.append("no clear learning, ownership, technical, or advancement opportunity")

    return concerns


_GENERIC_POSITIVE_FALLBACKS = [
    "The posting doesn't clearly state strong growth, ownership, or advancement signals.",
    "There isn't enough detail in the posting to strongly recommend or caution against this role.",
]
_GENERIC_LOW_RETURN_FALLBACK = "No other information in the posting outweighs this concern."

CLASSIFICATION_EXPLANATIONS = {
    "Career accelerator": (
        "This classification requires at least 4 positive career-value signals "
        "(like ownership, mentorship, or clear advancement language) and no "
        "meaningful concerns."
    ),
    "Strategic stepping stone": (
        "This classification applies when at least 2 positive career-value "
        "signals are present, even alongside some concerns — real value, just "
        "not an unambiguous accelerator."
    ),
    "Lateral opportunity": (
        "This classification applies when the posting doesn't show enough "
        "clear positive signals or concerns to lean strongly either way."
    ),
    "Low return opportunity": (
        "This classification applies when the posting is unpaid or "
        "commission-only, or when 2 or more concern signals are present "
        "alongside only 0-1 positive signals — a single concern alone is "
        "never enough for this label unless it's unpaid or commission-only work."
    ),
}


def _cap_list(items, minimum=2, maximum=4, fallback_pool=None):
    items = list(dict.fromkeys(i for i in items if i))
    result = items[:maximum]
    if fallback_pool:
        i = 0
        while len(result) < minimum and i < len(fallback_pool):
            if fallback_pool[i] not in result:
                result.append(fallback_pool[i])
            i += 1
    return result


def classify_career_value(positive_signals, concerns):
    """Returns {"classification", "reasons" (2-4 items), "concerns", "explanation"}.

    Rule (documented, no numeric score is ever shown):
      Low return opportunity   — unpaid or commission-only work, OR 2+
                                  concern signals with at most 1 positive
                                  signal. (A single concern alone never
                                  triggers this label unless it's unpaid
                                  or commission-only.)
      Career accelerator       — 4+ positive signals AND zero concerns.
      Strategic stepping stone — 2+ positive signals (any concern count
                                  that didn't already trigger Low return).
      Lateral opportunity      — everything else.
    """
    unpaid = "unpaid work" in concerns
    commission_only = "commission only compensation" in concerns

    if unpaid or commission_only:
        classification = "Low return opportunity"
    elif len(concerns) >= 2 and len(positive_signals) <= 1:
        classification = "Low return opportunity"
    elif len(positive_signals) >= 4 and not concerns:
        classification = "Career accelerator"
    elif len(positive_signals) >= 2:
        classification = "Strategic stepping stone"
    else:
        classification = "Lateral opportunity"

    if classification == "Low return opportunity":
        forced = (["unpaid work"] if unpaid else []) + (["commission only compensation"] if commission_only else [])
        reasons = _cap_list(forced + concerns, fallback_pool=[_GENERIC_LOW_RETURN_FALLBACK])
    else:
        reasons = _cap_list(positive_signals, fallback_pool=_GENERIC_POSITIVE_FALLBACKS)

    return {
        "classification": classification,
        "reasons": reasons,
        "concerns": concerns,
        "explanation": CLASSIFICATION_EXPLANATIONS[classification],
    }


# ---------------------------------------------------------------------------
# RECOMMENDED NEXT ACTION
# ---------------------------------------------------------------------------

_NEXT_ACTION_EXPLANATIONS = {
    "Apply now": "This posting has strong career value and enough clear information to move forward confidently.",
    "Research before applying": "There's real value here, but some important details are missing or unclear — worth a closer look before applying.",
    "Save for later": "This could be a useful move down the road, even if it's not the strongest fit to pursue immediately.",
    "Skip for now": "The concerns here are significant enough that your time is likely better spent elsewhere.",
}


def recommend_next_action(classification, details):
    """`details` needs: salary, work_arrangement, employment_type, location."""
    missing_core = (
        not details.get("salary")
        or details.get("work_arrangement") == NOT_STATED
        or details.get("employment_type") == NOT_STATED
        or not details.get("location")
    )

    if classification == "Low return opportunity":
        action = "Skip for now"
    elif classification == "Career accelerator":
        action = "Research before applying" if missing_core else "Apply now"
    elif classification == "Strategic stepping stone":
        action = "Save for later"
    else:
        action = "Research before applying"

    return action, _NEXT_ACTION_EXPLANATIONS[action]


# ---------------------------------------------------------------------------
# TOP-LEVEL ORCHESTRATION
# ---------------------------------------------------------------------------

def decode_opportunity(posting_text, provided_title="", provided_company=""):
    """The full, transparent decode. Nothing here invents a fact — every
    field is either a literal regex match, a short excerpt of the
    posting, or the fixed string "Not clearly stated"."""
    text = normalize_whitespace(posting_text)

    job_title = extract_job_title(text, provided_title)
    company = extract_company(text, provided_company)
    location = extract_location(text)
    work_arrangement = detect_work_arrangement(text)
    employment_type = detect_employment_type(text)
    salary = extract_salary(text)
    experience = extract_experience(text)
    education = extract_education(text)
    travel = extract_travel(text)

    responsibilities = extract_responsibilities(text)
    required_qualifications = extract_required_qualifications(text)
    preferred_qualifications = extract_preferred_qualifications(text)
    skills = detect_skills(text)

    positive_signals = detect_positive_signals(text, salary, skills)
    concerns = detect_concerns(text, responsibilities, required_qualifications, employment_type, positive_signals)
    value = classify_career_value(positive_signals, concerns)

    questions = generate_questions({
        "salary": salary,
        "work_arrangement": work_arrangement,
        "travel": travel,
        "responsibilities": responsibilities,
        "required_qualifications": required_qualifications,
        "preferred_qualifications": preferred_qualifications,
        "text": text,
    })

    next_action, next_action_explanation = recommend_next_action(value["classification"], {
        "salary": salary,
        "work_arrangement": work_arrangement,
        "employment_type": employment_type,
        "location": location,
    })

    return {
        "job_title": job_title or NOT_STATED,
        "company": company or NOT_STATED,
        "location": location or NOT_STATED,
        "work_arrangement": work_arrangement,
        "salary": salary or NOT_STATED,
        "employment_type": employment_type,
        "experience": experience or NOT_STATED,
        "education": education or NOT_STATED,
        "travel": travel or NOT_STATED,
        "responsibilities": responsibilities,
        "required_qualifications": required_qualifications,
        "preferred_qualifications": preferred_qualifications,
        "skills": skills,
        "questions": questions,
        "classification": value["classification"],
        "classification_reasons": value["reasons"],
        "classification_concerns": value["concerns"],
        "classification_explanation": value["explanation"],
        "next_action": next_action,
        "next_action_explanation": next_action_explanation,
    }
