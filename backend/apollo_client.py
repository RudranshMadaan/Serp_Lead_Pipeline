"""Apollo.io client.

Two operations:
  1. enrich_company(name)  -> firmographics via Organization Search (by name)
  2. find_leaders(org_id, domain) -> founder / C-suite contacts (optional)

Apollo's exact response fields drift over time, so every getter reads several
possible key names and falls back gracefully. If parsing ever looks wrong, the
raw payload is logged so you can adjust the key paths in one place.

Auth uses the X-Api-Key header (Apollo's current scheme).
Docs index for agents: https://docs.apollo.io/llms.txt
"""
import random
import httpx

import config

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Cache-Control": "no-cache",
    "X-Api-Key": config.APOLLO_KEY,
}


def _g(d, *keys, default=None):
    """Return first present, non-empty value among keys."""
    for k in keys:
        v = d.get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def enrich_company(name: str, log=print):
    """Look up one company by name; return a firmographics dict (or None)."""
    if config.APOLLO_MOCK:
        return _mock_company(name)
    if not config.APOLLO_ENABLED:
        return None  # Apollo disabled (no key) -> firmographic fields stay blank
    if not name:
        return None
    payload = {"q_organization_name": name, "page": 1, "per_page": 1}
    try:
        with httpx.Client(timeout=40.0) as c:
            r = c.post(f"{config.APOLLO_BASE}/mixed_companies/search",
                       headers=HEADERS, json=payload)
            data = r.json()
    except Exception as e:
        log(f"  ! Apollo org search failed for '{name}': {e}")
        return None

    orgs = data.get("organizations") or data.get("accounts") or []
    if not orgs:
        return None
    o = orgs[0]
    revenue = _g(o, "annual_revenue", "organization_revenue", "estimated_annual_revenue")
    return {
        "apollo_org_id": _g(o, "id"),
        "domain": _g(o, "primary_domain", "website_url", default=""),
        "industry": (_g(o, "industry", default="") or "").strip(),
        "estimated_employees": _g(o, "estimated_num_employees", "num_employees"),
        "annual_revenue": revenue,
        "annual_revenue_printed": _g(o, "annual_revenue_printed", "organization_revenue_printed"),
        "founded_year": _g(o, "founded_year"),
        "total_funding": _g(o, "total_funding", "total_funding_printed"),
        "about": (_g(o, "short_description", "seo_description", default="") or "")[:500],
        "keywords": _g(o, "keywords", default=[]) or [],
        "linkedin_url": _g(o, "linkedin_url", default=""),
    }


def find_leaders(org_id, domain, log=print):
    """Return up to 3 leadership contacts. Optional / credit-consuming."""
    if config.APOLLO_MOCK:
        return _mock_leaders()
    if not config.APOLLO_ENABLED:
        return []
    body = {
        "person_seniorities": ["founder", "owner", "c_suite", "partner"],
        "page": 1,
        "per_page": 3,
    }
    if org_id:
        body["organization_ids"] = [org_id]
    elif domain:
        body["q_organization_domains"] = domain
    else:
        return []
    try:
        with httpx.Client(timeout=40.0) as c:
            r = c.post(f"{config.APOLLO_BASE}/mixed_people/search",
                       headers=HEADERS, json=body)
            data = r.json()
    except Exception as e:
        log(f"  ! Apollo people search failed: {e}")
        return []

    people = data.get("people") or data.get("contacts") or []
    leaders = []
    for p in people[:3]:
        leaders.append({
            "name": _g(p, "name", default=""),
            "title": _g(p, "title", default=""),
            "linkedin": _g(p, "linkedin_url", default=""),
            # Email is often masked unless unlocked (consumes credits).
            "email": _g(p, "email", default=""),
        })
    return leaders


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------
_INDUSTRY_BY_NAME = {
    "Brightwell Health": "Hospital & Health Care",
    "Northpeak Logistics": "Logistics & Supply Chain",
    "Cobalt Retail Group": "Retail",
    "Vantage Insurance Co": "Insurance",
    "Acme Software Inc": "Computer Software",
    "TalentBridge Staffing": "Staffing & Recruiting",
    "Meridian Manufacturing": "Mechanical or Industrial Engineering",
    "Lumen Financial": "Financial Services",
    "Orchard Foods": "Food & Beverages",
    "Pinewood Education": "Education Management",
}
_EMP_BY_NAME = {
    "Brightwell Health": 140, "Northpeak Logistics": 320, "Cobalt Retail Group": 210,
    "Vantage Insurance Co": 95, "Acme Software Inc": 60, "TalentBridge Staffing": 80,
    "Meridian Manufacturing": 460, "Lumen Financial": 175, "Orchard Foods": 600,
    "Pinewood Education": 45,
}


def _mock_company(name):
    ind = _INDUSTRY_BY_NAME.get(name, "Business Services")
    emp = _EMP_BY_NAME.get(name, random.choice([60, 120, 240, 380]))
    slug = name.lower().replace(" ", "").replace(",", "")[:14]
    return {
        "apollo_org_id": "mock_" + slug,
        "domain": slug + ".com",
        "industry": ind,
        "estimated_employees": emp,
        "annual_revenue": emp * 250000,
        "annual_revenue_printed": f"${emp * 0.25:.1f}M",
        "founded_year": random.choice([2009, 2012, 2015, 2018]),
        "total_funding": random.choice([None, "$12M", "$30M"]),
        "about": f"{name} is a {ind.lower()} company scaling its product team.",
        "keywords": [ind.lower(), "saas", "growth"],
        "linkedin_url": f"https://linkedin.com/company/{slug}",
    }


def _mock_leaders():
    first = random.choice(["Sarah", "David", "Priya", "Marcus", "Elena"])
    last = random.choice(["Chen", "Okafor", "Mehta", "Andersson", "Rossi"])
    return [{
        "name": f"{first} {last}",
        "title": random.choice(["Founder & CEO", "CTO", "VP Engineering"]),
        "linkedin": "https://linkedin.com/in/mock-lead",
        "email": "email_not_unlocked@example.com",
    }]
