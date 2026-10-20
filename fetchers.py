"""Job-source fetchers.

Every fetcher returns a list of dicts with the same keys:
    company, title, job_id, location, posted, url, source

Only public JSON endpoints that the career sites / job boards publish are used.
Before each request the site's robots.txt is checked; a disallowed path or an
unreadable robots.txt raises FetchError and that source is skipped for the run.
"""
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

UA = "Mozilla/5.0 (personal job-alert script; runs twice a day)"
LOCALE_RE = re.compile(r"^[a-z]{2}-[A-Z]{2}$")  # e.g. en-US
TIMEOUT = 20
PAUSE = 1.0  # seconds between requests to the same site

_robots = {}


class FetchError(Exception):
    pass


def check_robots(url):
    """Raise FetchError if robots.txt does not allow fetching `url`."""
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt", headers={"User-Agent": UA}, timeout=TIMEOUT)
        except requests.RequestException as ex:
            raise FetchError(f"could not read robots.txt for {p.netloc}: {ex}")
        if r.status_code == 404:
            rp.parse([])  # no robots.txt means no restrictions
        elif r.ok:
            rp.parse(r.text.splitlines())
        else:
            raise FetchError(f"robots.txt for {p.netloc} returned HTTP {r.status_code}")
        _robots[base] = rp
    if not _robots[base].can_fetch(UA, url):
        raise FetchError(f"robots.txt disallows {url}")


def _request(method, url, **kw):
    check_robots(url)
    headers = {"User-Agent": UA, "Accept": "application/json", **kw.pop("headers", {})}
    r = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    time.sleep(PAUSE)
    return r


def _job(company, job_id, title, location, posted, url, source):
    return {"company": company, "job_id": str(job_id), "title": title or "",
            "location": location or "", "posted": posted or "", "url": url,
            "source": source}


# ---------- Workday ----------

def parse_workday_url(url):
    """https://acme.wd5.myworkdayjobs.com/en-US/AcmeCareers -> (host, tenant, site, locale)"""
    p = urlparse(url.strip())
    host = p.netloc
    if "myworkdayjobs.com" not in host:
        raise ValueError(f"not a Workday URL: {url}")
    tenant = host.split(".")[0]
    parts = [s for s in p.path.split("/") if s]
    locale = next((s for s in parts if LOCALE_RE.match(s)), "en-US")
    sites = [s for s in parts if not LOCALE_RE.match(s)]
    if not sites:
        raise ValueError(f"no site name in URL: {url}")
    return host, tenant, sites[0], locale


def workday_job_id(posting):
    """Prefer the requisition-style id at the end of the job path (unique per posting);
    fall back to the first bullet field."""
    path = posting.get("externalPath", "")
    tail = path.rsplit("_", 1)[-1] if "_" in path else ""
    if tail:
        return tail
    bullets = posting.get("bulletFields") or []
    return bullets[0] if bullets else path


def fetch_workday(company, url, search_terms, max_per_term=100):
    host, tenant, site, locale = parse_workday_url(url)
    api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    jobs = {}
    for term in search_terms:
        offset = 0
        while offset < max_per_term:
            body = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term}
            r = _request("POST", api, json=body, headers={"Content-Type": "application/json"})
            postings = r.json().get("jobPostings", [])
            for p in postings:
                path = p.get("externalPath", "")
                job_id = workday_job_id(p)
                jobs[job_id] = _job(company, job_id, p.get("title"), p.get("locationsText"),
                                    p.get("postedOn"), f"https://{host}/{locale}/{site}{path}",
                                    "workday")
            if len(postings) < 20:
                break
            offset += 20
    return list(jobs.values())


def workday_locations(job_url):
    """All locations of one Workday posting, from its public detail endpoint.

    The job list only says "4 Locations"; the detail has the primary location,
    additionalLocations and the country. Returns e.g.
    "Bengaluru - Bellandur (GTP); Pune - Hinjewadi (India)".
    """
    p = urlparse(job_url)
    tenant = p.netloc.split(".")[0]
    parts = [s for s in p.path.split("/") if s and not LOCALE_RE.match(s)]
    api = f"https://{p.netloc}/wday/cxs/{tenant}/" + "/".join(parts)
    info = _request("GET", api).json()["jobPostingInfo"]
    places = [info.get("location")] + (info.get("additionalLocations") or [])
    text = "; ".join(x for x in places if x)
    country = (info.get("country") or {}).get("descriptor")
    return f"{text} ({country})" if country else text


# ---------- Greenhouse / Lever ----------

def fetch_greenhouse(company, token):
    r = _request("GET", f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs")
    return [_job(company, j["id"], j.get("title"), (j.get("location") or {}).get("name"),
                 (j.get("updated_at") or "")[:10], j.get("absolute_url"), "greenhouse")
            for j in r.json().get("jobs", [])]


def fetch_lever(company, site):
    r = _request("GET", f"https://api.lever.co/v0/postings/{site}?mode=json")
    out = []
    for j in r.json():
        posted = ""
        if j.get("createdAt"):
            posted = datetime.fromtimestamp(j["createdAt"] / 1000, tz=timezone.utc).date().isoformat()
        out.append(_job(company, j["id"], j.get("text"), (j.get("categories") or {}).get("location"),
                        posted, j.get("hostedUrl"), "lever"))
    return out


# ---------- Amazon ----------

def fetch_amazon(search_terms, location="India"):
    jobs = {}
    for term in search_terms:
        r = _request("GET", "https://www.amazon.jobs/en/search.json",
                     params={"base_query": term, "loc_query": location,
                             "result_limit": 100, "sort": "recent"})
        for j in r.json().get("jobs", []):
            job_id = str(j.get("id_icims") or j.get("id"))
            jobs[job_id] = _job("Amazon", job_id, j.get("title"),
                                j.get("normalized_location") or j.get("location"),
                                j.get("posted_date"),
                                "https://www.amazon.jobs" + j.get("job_path", ""), "amazon")
    return list(jobs.values())
