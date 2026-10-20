"""Read job-alert emails (LinkedIn, Indeed, Naukri, ...) from your own Gmail.

This reads only your own alert emails through the Gmail API (read-only scope).
It does not visit or scrape the job portals themselves.

One-time setup (free):
  1. Google Cloud Console -> create a project -> enable the Gmail API.
  2. OAuth consent screen (External, add yourself as a test user).
  3. Credentials -> Create OAuth client ID -> Desktop app -> download JSON,
     save it here as credentials.json.
  4. pip install -r requirements-gmail.txt
  5. Run `python gmail_reader.py` once; a browser opens to approve access,
     which writes token.json. Both files are git-ignored.
"""
import base64
import re
import sys
from html import unescape
from pathlib import Path

import config

BASE = Path(__file__).resolve().parent
CREDS_FILE = BASE / "credentials.json"
TOKEN_FILE = BASE / "token.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# (regex on the href, source name). Group 1 = the portal's job id.
PATTERNS = [
    (re.compile(r"https?://(?:[a-z]+\.)?linkedin\.com/(?:comm/)?jobs/view/(\d+)"), "linkedin"),
    (re.compile(r"https?://(?:[a-z]+\.)?indeed\.com/[^\"'\s<>]*?[?&]jk=([0-9a-f]+)"), "indeed"),
    (re.compile(r"https?://(?:www\.)?naukri\.com/job-listings-[^\"'\s<>?]*?-(\d{6,})"), "naukri"),
]
ANCHOR_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)


def extract_jobs(html):
    """Pull (title, job_id, url, source) out of an alert email's HTML.
    Pure function, no network, so it can be tested offline."""
    found, seen = [], set()
    for href, inner in ANCHOR_RE.findall(html):
        href = unescape(href)
        for rx, source in PATTERNS:
            m = rx.search(href)
            if not m:
                continue
            job_id = m.group(1)
            if (source, job_id) in seen:
                break
            seen.add((source, job_id))
            text = re.sub(r"<[^>]+>", " ", inner)
            title = " ".join(unescape(text).split()) or "(see alert email)"
            found.append({"title": title, "job_id": job_id, "source": source,
                          "url": unescape(href)})
            break
    return found


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES) if TOKEN_FILE.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _html_parts(payload):
    if payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
        yield base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "replace")
    for part in payload.get("parts", []) or []:
        yield from _html_parts(part)


def fetch_alert_jobs(label=None, days=None):
    """Return job dicts in the same shape as the other fetchers."""
    label = label or config.GMAIL_LABEL
    days = days or config.GMAIL_LOOKBACK_DAYS
    svc = _service()
    refs = svc.users().messages().list(
        userId="me", q=f'label:"{label}" newer_than:{days}d', maxResults=100
    ).execute().get("messages", [])
    jobs = {}
    for ref in refs:
        msg = svc.users().messages().get(userId="me", id=ref["id"], format="full").execute()
        html = "\n".join(_html_parts(msg.get("payload", {})))
        for j in extract_jobs(html):
            jobs[(j["source"], j["job_id"])] = {
                "company": f"Email alert ({j['source']})",
                "title": j["title"],
                "job_id": j["job_id"],
                "location": "",  # alert emails rarely state it reliably
                "posted": "",
                "url": j["url"],
                "source": "gmail",
            }
    return list(jobs.values())


if __name__ == "__main__":
    for j in fetch_alert_jobs():
        print(j["company"], "|", j["title"], "|", j["job_id"], "|", j["url"])
    sys.exit(0)
