# IT Outsourcing — Lead Pipeline

Finds companies actively hiring software/IT talent who are likely candidates for
IT outsourcing, enriches them, filters out the noise, and exports a ranked Excel
sheet.

Pipeline: **SerpApi Google Jobs → dedup + hiring-intent → staffing/competitor
filter → Apollo firmographics → IT-native vs. prospect scoring → employee-size
filter → optional leadership lookup → formatted .xlsx**

## Why Google Jobs instead of raw search + H1 scraping
The Google Jobs engine returns `company_name`, job `title`, source platform
(`via`), and posting recency as clean JSON — exactly the H1 + company + platform
+ freshness you'd otherwise get by fetching and parsing each result page. No
Puppeteer, far fewer accuracy leaks.

## Setup
```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
cp .env.example .env        # then paste your SERPAPI_KEY and APOLLO_KEY
```

## Run
```bash
cd backend
uvicorn app:app --reload --port 8000
```
Open http://localhost:8000

- The badge top-right shows **LIVE** (keys present) or **MOCK MODE**.
- Set `MOCK_MODE=true` in `.env` to demo the UI with synthetic data (no credits spent).

## How to use the UI
1. Edit the **role queries** (one search per line) to match the stacks you service.
2. Optionally restrict **source platforms** (LinkedIn, Wellfound, …). None = any.
3. Set the **recency window** (default 24h) and **employee band** (default 20–500).
4. Toggle leadership lookup (uses extra Apollo credits) and staffing drop.
5. Press **Run pipeline**, watch the log, then sort/filter the table and download `.xlsx`.

## Scoring
`prospect_score` (0–100) rewards: non-tech company hiring developers (+40),
employee sweet spot (+25), not a staffing/middleman (+20), multiple open roles
in the window (+12), and data completeness. Green ≥70, amber ≥45, red below.

## Tuning (all in `backend/config.py`)
- `DEFAULT_ROLE_QUERIES` — starting search set
- `STAFFING_KEYWORDS` — what counts as a middleman/competitor to drop
- `IT_NATIVE_INDUSTRIES` — industries treated as competitors / unlikely to outsource
- `ROLE_BUCKETS` — how raw titles map to the "Role Offered" column
- `MAX_PAGES_PER_QUERY` — postings pulled per query (10/page)

## Notes / known realities
- Apollo revenue and headcount are **estimates** — treat thresholds as soft.
- Lead emails are often masked unless unlocked (consumes Apollo credits).
- Apollo response field names occasionally change; `apollo_client.py` reads
  several possible keys and logs raw payloads if parsing looks off — adjust the
  getters there in one place if needed.
- In-memory job store is fine for single-user local use. For multi-user or
  scheduled runs, move `JOBS` to Redis/SQLite and add a queue.
- Caching SerpApi responses (e.g. by query+date) will cut credit usage if you
  run the same searches repeatedly.

## File map
```
backend/
  app.py            FastAPI app + endpoints + serves the UI
  pipeline.py       stage orchestration (runs in a thread)
  serpapi_client.py Google Jobs search, recency parsing, platform filter
  apollo_client.py  org enrichment + leadership search (defensive field reads)
  classify.py       staffing detection, role bucketing, IT-native, scoring
  excel_export.py   openpyxl formatting
  config.py         keys, thresholds, keyword dictionaries  ← tune here
frontend/
  index.html        single-file enterprise UI (no build step)
```
