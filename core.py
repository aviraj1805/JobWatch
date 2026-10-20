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


def key(job):
    return f"{job['company']}|{job['job_id']}"


def relevant(job):
    title = job["title"]
    if not ROLE_RE.search(title) or EXCL_RE.search(title):
        return False
    loc = job["location"].lower()
    if loc and "locations" not in loc and not any(k in loc for k in config.LOCATION_KEYWORDS):
        return False
    if "30+" in job.get("posted", ""):  # Workday's "Posted 30+ Days Ago"
        return False
    return True


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
    return set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()


def save_seen(seen):
    SEEN_FILE.write_text(json.dumps(sorted(seen), indent=1))


def load_last_run():
    if LAST_RUN_FILE.exists():
        return json.loads(LAST_RUN_FILE.read_text())
    return None


def save_last_run(jobs, errors, counts):
    data = {
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "counts": counts,
        "errors": errors,
        "jobs": jobs,
    }
    LAST_RUN_FILE.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    return data
