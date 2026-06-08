"""SerpApi Google Jobs client.

We use the google_jobs engine rather than raw Google Search because it returns
title, company_name, the source platform (`via`) and posting recency as clean
structured JSON - no page fetching or H1 parsing required.
"""
import re
import time
import random
import httpx

import config

# ---------------------------------------------------------------------------
# Recency parsing: Google Jobs gives strings like "9 hours ago", "2 days ago",
# "30+ days ago", "just posted". Convert to approximate hours so we can enforce
# the 24h (or chosen) window precisely.
# ---------------------------------------------------------------------------
def posted_at_to_hours(text: str):
    if not text:
        return None
    t = text.lower().strip()
    if "just" in t or "moment" in t or "minute" in t or "hour" not in t and "day" not in t and "week" not in t and "month" not in t and re.search(r"\bnow\b", t):
        return 0
    m = re.search(r"(\d+)\s*\+?\s*(minute|hour|day|week|month)", t)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    mult = {"minute": 1 / 60, "hour": 1, "day": 24, "week": 24 * 7, "month": 24 * 30}[unit]
    return n * mult


def _client():
    return httpx.Client(timeout=40.0)


def search_jobs(query: str, log=print):
    """Return a list of raw job dicts for one role query, paginated."""
    if config.SERPAPI_MOCK:
        return _mock_jobs(query)

    results = []
    next_token = None
    pages = 0
    with _client() as client:
        while pages < config.MAX_PAGES_PER_QUERY:
            params = {
                "engine": "google_jobs",
                "q": query,
                "hl": config.SERPAPI_HL,
                "gl": config.SERPAPI_GL,
                "location": config.SERPAPI_LOCATION,
                "api_key": config.SERPAPI_KEY,
            }
            if next_token:
                params["next_page_token"] = next_token
            try:
                r = client.get(config.SERPAPI_BASE, params=params)
                data = r.json()
            except Exception as e:
                log(f"  ! SerpApi request failed for '{query}': {e}")
                break
            if data.get("error"):
                log(f"  ! SerpApi error for '{query}': {data['error']}")
                break
            jobs = data.get("jobs_results", []) or []
            results.extend(jobs)
            pages += 1
            next_token = (data.get("serpapi_pagination") or {}).get("next_page_token")
            if not next_token:
                break
            time.sleep(0.4)  # be polite
    return results


def normalize_jobs(raw_jobs, query, max_hours, platforms, log=print):
    """Flatten raw SerpApi jobs into our internal records, applying the recency
    and platform filters. `platforms` is a list of lowercase substrings, or
    empty for any."""
    out = []
    for j in raw_jobs:
        det = j.get("detected_extensions") or {}
        posted = det.get("posted_at") or _first_time_extension(j.get("extensions"))
        hours = posted_at_to_hours(posted)
        if hours is not None and hours > max_hours:
            continue
        via = (j.get("via") or "").replace("via", "").strip()
        if platforms:
            if not any(p in via.lower() for p in platforms):
                continue
        out.append({
            "company_name": (j.get("company_name") or "").strip(),
            "job_title": (j.get("title") or "").strip(),
            "source_platform": via,
            "posted_at": posted or "",
            "posted_hours": hours,
            "location": j.get("location") or "",
            "query": query,
            "description": (j.get("description") or "")[:600],
        })
    return out


def _first_time_extension(exts):
    if not exts:
        return None
    for e in exts:
        if any(w in e.lower() for w in ("ago", "posted", "just")):
            return e
    return None


# ---------------------------------------------------------------------------
# Mock data for MOCK_MODE
# ---------------------------------------------------------------------------
_MOCK_COMPANIES = [
    ("Brightwell Health", "Healthcare", 140),
    ("Northpeak Logistics", "Logistics & Supply Chain", 320),
    ("Cobalt Retail Group", "Retail", 210),
    ("Vantage Insurance Co", "Insurance", 95),
    ("Acme Software Inc", "Computer Software", 60),         # IT-native
    ("TalentBridge Staffing", "Staffing & Recruiting", 80),  # staffing -> drop
    ("Meridian Manufacturing", "Manufacturing", 460),
    ("Lumen Financial", "Financial Services", 175),
    ("Orchard Foods", "Food & Beverages", 600),              # too big
    ("Pinewood Education", "Education", 45),
]


def _mock_jobs(query):
    bucket = []
    for name, industry, _ in random.sample(_MOCK_COMPANIES, k=6):
        bucket.append({
            "title": query.replace("remote ", "").title(),
            "company_name": name,
            "location": "Remote (USA)",
            "via": random.choice(["via LinkedIn", "via Wellfound", "via Indeed", "via Glassdoor"]),
            "detected_extensions": {"posted_at": random.choice(
                ["3 hours ago", "9 hours ago", "18 hours ago", "1 day ago", "2 days ago"])},
            "description": f"We are hiring a {query} to join our team.",
        })
    return bucket
