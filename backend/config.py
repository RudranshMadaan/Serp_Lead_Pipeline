"""Central configuration: API keys, tunable thresholds, and the keyword
dictionaries that drive filtering/classification. Everything a non-coder might
reasonably want to adjust lives here."""

import os
from dotenv import load_dotenv

load_dotenv()

# ---- API credentials (set these in backend/.env) ----------------------------
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "").strip()
APOLLO_KEY = os.getenv("APOLLO_KEY", "").strip()

# Optional password gate for public deployments (Render etc.). If set, the API
# requires this value in an X-App-Password header. Leave blank for local use.
APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()

# FORCE_MOCK (env MOCK_MODE=true) makes BOTH services return synthetic data so
# you can demo the whole UI with zero API calls.
FORCE_MOCK = (os.getenv("MOCK_MODE", "").lower() in ("1", "true", "yes"))

# Each service is independent:
#   - SerpApi runs live whenever a key is present.
#   - Apollo runs live only when its key is present; otherwise enrichment is
#     SKIPPED (firmographic columns left blank) rather than faked.
SERPAPI_MOCK = FORCE_MOCK or (not SERPAPI_KEY)
APOLLO_MOCK = FORCE_MOCK
APOLLO_ENABLED = bool(APOLLO_KEY) and not FORCE_MOCK

# Backwards-compat flag (true only when everything is synthetic).
MOCK_MODE = FORCE_MOCK or (SERPAPI_MOCK and not APOLLO_ENABLED and not APOLLO_KEY)

# ---- SerpApi -----------------------------------------------------------------
SERPAPI_BASE = "https://serpapi.com/search"
SERPAPI_GL = os.getenv("SERPAPI_GL", "us")          # country for results
SERPAPI_HL = os.getenv("SERPAPI_HL", "en")          # language
SERPAPI_LOCATION = os.getenv("SERPAPI_LOCATION", "United States")
MAX_PAGES_PER_QUERY = int(os.getenv("MAX_PAGES_PER_QUERY", "2"))  # 10 jobs/page

# ---- Apollo ------------------------------------------------------------------
APOLLO_BASE = "https://api.apollo.io/v1"

# ---- Default role queries (the kinds of hiring you can service) --------------
# Edit freely in the UI; this is just the starting set.
DEFAULT_ROLE_QUERIES = [
    "remote software developer",
    "remote backend developer",
    "remote frontend developer",
    "remote full stack developer",
    "remote react developer",
    "remote node js developer",
    "remote python developer",
    "remote devops engineer",
    "remote ui ux designer",
    "remote qa engineer",
    "remote mobile app developer",
    "remote data engineer",
]

# Maps raw job titles to a normalized "role offered" bucket for the sheet.
ROLE_BUCKETS = {
    "backend": ["backend", "back-end", "back end", "api developer"],
    "frontend": ["frontend", "front-end", "front end"],
    "fullstack": ["full stack", "full-stack", "fullstack"],
    "devops": ["devops", "dev ops", "sre", "site reliability", "platform engineer"],
    "ui_ux": ["ui/ux", "ui ux", "ux designer", "ui designer", "product designer"],
    "qa": ["qa", "quality assurance", "test engineer", "sdet", "automation tester"],
    "mobile": ["ios", "android", "react native", "flutter", "mobile"],
    "data": ["data engineer", "data scientist", "ml engineer", "machine learning", "ai engineer"],
    "frameworks": ["react", "angular", "vue", "node", "python", "django", "java", "golang", ".net", "php", "ruby"],
    "software_general": ["software", "developer", "engineer", "programmer"],
}

# ---- Filtering --------------------------------------------------------------
# Companies whose name/industry matches these are middlemen or competitors,
# not end-customer prospects. They are dropped (or flagged) before enrichment.
STAFFING_KEYWORDS = [
    "staffing", "recruit", "talent", "headhunt", "manpower", "outsourc",
    "placement", "hiring partner", "rpo", "workforce", "consultancy",
    "consulting services", "it services", "software services",
    "technology services", "infotech", "softech", "global services",
]

# Apollo industries we treat as "IT-native" (often competitors / less likely
# to outsource their core engineering).
IT_NATIVE_INDUSTRIES = {
    "information technology & services",
    "information technology and services",
    "computer software",
    "internet",
    "computer & network security",
    "computer hardware",
    "computer networking",
    "software development",
}

# ---- Scoring & thresholds (UI can override per run) -------------------------
DEFAULT_MIN_EMPLOYEES = 20
DEFAULT_MAX_EMPLOYEES = 500     # drop big enterprises above this
DEFAULT_MAX_HOURS = 24          # recency window for postings

# Output location
import pathlib
OUTPUT_DIR = pathlib.Path(os.getenv("OUTPUT_DIR", "/tmp/serp_leads"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
