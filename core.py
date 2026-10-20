"""Shared logic: relevance filter, ranking, state files, referral text.

Used by main.py (CLI / Telegram / GitHub Actions) and app.py (Streamlit UI).
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import config

BASE = Path(__file__).resolve().parent
SEEN_FILE = BASE / "seen_jobs.json"    # keys of jobs already alerted (committed by CI)
LAST_RUN_FILE = BASE / "last_run.json"  # matches from the latest fetch (read by the UI)

ROLE_RE = re.compile(config.ROLE_PATTERN, re.I)
EXCL_RE = re.compile(config.EXCLUDE_PATTERN, re.I)
STRONG_RE = re.compile(config.FRESHER_STRONG, re.I)
WEAK_RE = re.compile(config.FRESHER_WEAK, re.I)
SKILL_RES = [(re.compile(p, re.I), w) for p, w in config.SKILL_WEIGHTS.items()]
# Whole words only, so "india" does not match "Indiana"
LOC_RE = re.compile(r"\b(" + "|".join(map(re.escape, config.LOCATION_KEYWORDS)) + r")\b", re.I)
MULTI_LOC_RE = re.compile(r"^\d+ locations$", re.I)  # Workday's "4 Locations"


def key(job):
    return f"{job['company']}|{job['job_id']}"


def title_ok(job):
    title = job["title"]
    return bool(ROLE_RE.search(title)) and not EXCL_RE.search(title)


def is_multi_location(job):
    return bool(MULTI_LOC_RE.match(job["location"].strip()))


def location_ok(job):
    # "N Locations" is only left unresolved when the detail lookup failed; keep it.
    loc = job["location"]
    return not loc or is_multi_location(job) or bool(LOC_RE.search(loc))


def fresh(job):
    return "30+" not in job.get("posted", "")  # Workday's "Posted 30+ Days Ago"


def relevant(job):
    return title_ok(job) and location_ok(job) and fresh(job)


def fresher_rank(title):
    if STRONG_RE.search(title):
        return 2
    if WEAK_RE.search(title):
        return 1
    return 0


def skill_score(job):
    return sum(w for rx, w in SKILL_RES if rx.search(job["title"]))


def rank(jobs):
    """Fresher-friendly roles first, then best skill match."""
    return sorted(jobs, key=lambda j: (-fresher_rank(j["title"]), -skill_score(j)))


def referral_text(job, referrer=None):
    name = referrer or config.REFERRERS.get(job["company"]) or "there"
    return config.REFERRAL_TEMPLATE.format(name=name, **job)


def load_seen():
    return set(json.loads(SEEN_FILE.read_text(encoding="utf-8"))) if SEEN_FILE.exists() else set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=1), encoding="utf-8")


def load_last_run():
    if LAST_RUN_FILE.exists():
        return json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
    return None


def save_last_run(jobs, errors, counts):
    data = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "counts": counts,
        "errors": errors,
        "jobs": jobs,
    }
    LAST_RUN_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return data
