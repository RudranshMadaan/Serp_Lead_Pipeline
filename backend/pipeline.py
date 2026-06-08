"""Pipeline orchestration. Runs in a background thread and streams progress
into a shared job record."""
import time
import datetime
import collections

import config
import serpapi_client as serp
import apollo_client as apollo
import classify
import excel_export


def run_pipeline(job, params):
    """job: mutable dict (status/log/result). params: run options from UI."""
    def log(msg):
        stamp = datetime.datetime.now().strftime("%H:%M:%S")
        job["log"].append(f"[{stamp}] {msg}")

    try:
        queries = [q.strip() for q in params.get("queries", []) if q.strip()]
        platforms = [p.strip().lower() for p in params.get("platforms", []) if p.strip()]
        max_hours = int(params.get("max_hours", config.DEFAULT_MAX_HOURS))
        min_emp = int(params.get("min_employees", config.DEFAULT_MIN_EMPLOYEES))
        max_emp = int(params.get("max_employees", config.DEFAULT_MAX_EMPLOYEES))
        enrich_people = bool(params.get("enrich_people", False))
        drop_staffing = bool(params.get("drop_staffing", True))
        enrich_web = bool(params.get("enrich_web", False))
        country = params.get("country", "United States")
        remote = bool(params.get("remote", True))
        geo = config.COUNTRY_OPTIONS.get(country, {"gl": config.SERPAPI_GL,
                                                   "location": config.SERPAPI_LOCATION})

        job["status"] = "running"
        job["stage"] = "search"
        if config.FORCE_MOCK:
            mode = "MOCK (all synthetic)"
        else:
            serp_s = "LIVE" if not config.SERPAPI_MOCK else "mock"
            if config.APOLLO_ENABLED:
                enr = "Apollo LIVE"
            elif enrich_web and not config.SERPAPI_MOCK:
                enr = "web-enrich (SerpApi)"
            else:
                enr = "enrichment OFF (blank firmographics)"
            mode = f"SerpApi {serp_s} · {enr}"
        log(f"Run started — {mode}. {len(queries)} queries, {country}, "
            f"{'remote-only, ' if remote else ''}window {max_hours}h.")

        # ---- Stage 1: search ----------------------------------------------
        all_jobs = []
        for q in queries:
            raw = serp.search_jobs(q, gl=geo["gl"], location=geo["location"],
                                   remote=remote, log=log)
            norm = serp.normalize_jobs(raw, q, max_hours, platforms, log=log)
            log(f"  '{q}': {len(raw)} fetched -> {len(norm)} within {max_hours}h"
                + (f" on {platforms}" if platforms else ""))
            all_jobs.extend(norm)
        log(f"Stage 1 complete: {len(all_jobs)} postings after recency/platform filter.")

        # ---- Stage 2: dedup by company + hiring-intent count ---------------
        job["stage"] = "dedup"
        by_company = collections.OrderedDict()
        counts = collections.Counter()
        for j in all_jobs:
            name = j["company_name"]
            if not name:
                continue
            counts[name.lower()] += 1
            if name.lower() not in by_company:
                by_company[name.lower()] = j  # keep first (freshest by query order)
        companies = list(by_company.values())
        for c in companies:
            c["roles_count"] = counts[c["company_name"].lower()]
        log(f"Stage 2 complete: {len(companies)} unique companies "
            f"(from {len(all_jobs)} postings).")

        # ---- Stage 3: enrich + classify -----------------------------------
        job["stage"] = "enrich"
        apollo_on = config.APOLLO_ENABLED or config.APOLLO_MOCK
        web_on = enrich_web and not config.SERPAPI_MOCK
        if not apollo_on and not web_on:
            log("  Enrichment off — firmographic columns will be blank. "
                "Add an Apollo key, or tick 'Enrich via web search'.")
        elif web_on and not apollo_on:
            log("  Web enrichment ON (SerpApi) — 1 extra search per company; "
                "values are estimates and small startups may stay blank.")
        enriched = []
        for i, c in enumerate(companies, 1):
            firm = {}
            if apollo_on:
                firm = apollo.enrich_company(c["company_name"], log=log) or {}
            if web_on and not firm.get("estimated_employees"):
                web = serp.web_enrich_company(c["company_name"], gl=geo["gl"], log=log) or {}
                for k, v in web.items():       # apollo wins; web fills the gaps
                    if not firm.get(k):
                        firm[k] = v
            c.update({
                "domain": firm.get("domain", ""),
                "industry": firm.get("industry", ""),
                "estimated_employees": firm.get("estimated_employees"),
                "annual_revenue": firm.get("annual_revenue"),
                "annual_revenue_label": firm.get("annual_revenue_printed")
                    or (f"${firm['annual_revenue']:,}" if isinstance(firm.get("annual_revenue"), (int, float)) else ""),
                "founded_year": firm.get("founded_year"),
                "total_funding": firm.get("total_funding") or "",
                "about": firm.get("about", "") or c.get("description", "")[:300],
                "keywords": firm.get("keywords", []),
                "apollo_org_id": firm.get("apollo_org_id"),
                "data_source": firm.get("source", "apollo" if firm and apollo_on else ("web" if firm else "")),
            })
            classify.classify(c)
            c["role_bucket"] = classify.role_bucket(c["job_title"])
            c["it_native_label"] = "Yes" if c["it_native"] else "No"
            enriched.append(c)
            if i % 5 == 0 or i == len(companies):
                job["stage"] = f"enrich ({i}/{len(companies)})"
        log(f"Stage 3 complete: {len(enriched)} companies enriched & classified.")

        # ---- Stage 4: filters (staffing, employee thresholds) -------------
        job["stage"] = "filter"
        kept = []
        dropped_staffing = dropped_size = 0
        for c in enriched:
            if drop_staffing and c["is_staffing"]:
                dropped_staffing += 1
                continue
            emp = c.get("estimated_employees")
            if isinstance(emp, (int, float)) and (emp > max_emp or emp < min_emp):
                dropped_size += 1
                continue
            kept.append(c)
        log(f"Stage 4 complete: dropped {dropped_staffing} staffing/middlemen, "
            f"{dropped_size} outside {min_emp}-{max_emp} employees. {len(kept)} remain.")

        # ---- Stage 5: optional leadership contacts ------------------------
        if enrich_people and config.APOLLO_ENABLED:
            job["stage"] = "leads"
            for i, c in enumerate(kept, 1):
                leaders = apollo.find_leaders(c.get("apollo_org_id"), c.get("domain"), log=log)
                if leaders:
                    l = leaders[0]
                    c["lead_name"] = l["name"]
                    c["lead_title"] = l["title"]
                    c["lead_linkedin"] = l["linkedin"]
                    c["lead_email"] = l["email"]
            log(f"Stage 5 complete: leadership lookup done for {len(kept)} companies.")
        else:
            if enrich_people and not config.APOLLO_ENABLED:
                log("Stage 5 skipped: leadership lookup needs an Apollo key.")
            for c in kept:
                c.setdefault("lead_name", "")
                c.setdefault("lead_title", "")
                c.setdefault("lead_linkedin", "")
                c.setdefault("lead_email", "")

        # ---- Stage 6: export ----------------------------------------------
        job["stage"] = "export"
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = config.OUTPUT_DIR / f"prospects_{ts}.xlsx"
        excel_export.write_xlsx(kept, str(path))
        log(f"Stage 6 complete: wrote {len(kept)} rows to {path.name}.")

        job["result_path"] = str(path)
        job["result_name"] = path.name
        job["rows"] = [_row_preview(c) for c in sorted(
            kept, key=lambda r: r.get("prospect_score", 0), reverse=True)]
        job["counts"] = {
            "postings": len(all_jobs),
            "companies": len(companies),
            "kept": len(kept),
            "dropped_staffing": dropped_staffing,
            "dropped_size": dropped_size,
        }
        job["stage"] = "done"
        job["status"] = "done"
        log("Pipeline finished.")
    except Exception as e:
        job["status"] = "error"
        job["stage"] = "error"
        log(f"FATAL: {e}")
        raise


def _row_preview(c):
    return {
        "prospect_score": c.get("prospect_score", 0),
        "company_name": c.get("company_name", ""),
        "job_title": c.get("job_title", ""),
        "role_bucket": c.get("role_bucket", ""),
        "roles_count": c.get("roles_count", 1),
        "source_platform": c.get("source_platform", ""),
        "posted_at": c.get("posted_at", ""),
        "industry": c.get("industry", ""),
        "it_native_label": c.get("it_native_label", ""),
        "estimated_employees": c.get("estimated_employees", ""),
        "annual_revenue_label": c.get("annual_revenue_label", ""),
        "founded_year": c.get("founded_year", ""),
        "domain": c.get("domain", ""),
        "lead_name": c.get("lead_name", ""),
        "lead_title": c.get("lead_title", ""),
        "flags": c.get("flags", ""),
    }
