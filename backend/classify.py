"""Filtering and scoring logic: the part that turns noisy job postings into a
ranked prospect list."""
import config


def role_bucket(title: str) -> str:
    t = (title or "").lower()
    for bucket, kws in config.ROLE_BUCKETS.items():
        if any(k in t for k in kws):
            return bucket
    return "other"


def is_staffing(name: str, industry: str, keywords) -> bool:
    blob = " ".join([
        (name or "").lower(),
        (industry or "").lower(),
        " ".join(keywords or []).lower(),
    ])
    return any(k in blob for k in config.STAFFING_KEYWORDS)


def is_it_native(industry: str) -> bool:
    return (industry or "").strip().lower() in config.IT_NATIVE_INDUSTRIES


def prospect_score(rec: dict) -> int:
    """0-100 composite. Higher = better outsourcing prospect."""
    score = 0
    emp = rec.get("estimated_employees")
    industry = rec.get("industry", "")

    # Non-tech company hiring developers = the core thesis.
    if industry and not is_it_native(industry):
        score += 40
    elif is_it_native(industry):
        score += 5  # likely a competitor / unlikely to outsource core eng

    # Employee sweet spot.
    if isinstance(emp, (int, float)):
        if config.DEFAULT_MIN_EMPLOYEES <= emp <= config.DEFAULT_MAX_EMPLOYEES:
            score += 25
        elif emp < config.DEFAULT_MIN_EMPLOYEES:
            score += 8   # very small, maybe low budget
        else:
            score += 2   # enterprise

    # Not a staffing/recruiting middleman.
    if not rec.get("is_staffing"):
        score += 20

    # Hiring intensity (multiple open roles in window).
    rc = rec.get("roles_count", 1)
    if rc >= 3:
        score += 12
    elif rc == 2:
        score += 8

    # Data completeness / verifiability.
    if rec.get("domain"):
        score += 3
    if rec.get("founded_year"):
        score += 2

    return max(0, min(100, score))


def classify(rec: dict) -> dict:
    """Annotate a company-level record in place with flags and score."""
    rec["is_staffing"] = is_staffing(
        rec.get("company_name", ""), rec.get("industry", ""), rec.get("keywords"))
    rec["it_native"] = is_it_native(rec.get("industry", ""))
    rec["prospect_score"] = prospect_score(rec)

    reasons = []
    if rec["is_staffing"]:
        reasons.append("staffing/recruiting or IT-services middleman")
    if rec["it_native"]:
        reasons.append("IT-native (likely competitor)")
    emp = rec.get("estimated_employees")
    if isinstance(emp, (int, float)) and emp > config.DEFAULT_MAX_EMPLOYEES:
        reasons.append(f"enterprise ({int(emp)} employees)")
    rec["flags"] = "; ".join(reasons)
    return rec
