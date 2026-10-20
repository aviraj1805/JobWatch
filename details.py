"""Turn a job description into the summary the dashboard and alerts show.

No network here: fetchers pass in description text and whatever structured
fields their source has (employment type, category, posting date).
"""
import html
import re
from datetime import datetime

import config
import core

# Case-insensitive; a pattern can opt out with (?-i:...), e.g. the language "R"
TECH_RES = [(name, re.compile(rx, re.I)) for name, rx in config.TECH_KEYWORDS.items()]

YEARS = r"(\d{1,2})\s*\+?\s*(?:-|–|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)|(\d{1,2})\s*\+\s*(?:years?|yrs?)|(\d{1,2})\s*(?:years?|yrs?)"
EXP_RE = re.compile(YEARS, re.I)
FRESHER_TEXT_RE = re.compile(r"\b(freshers?|no (?:prior )?experience|recent graduates?|"
                             r"final[- ]year|graduating in|0\s*(?:-|–|to)\s*1\s*years?)\b", re.I)
# Where the role-specific part of a description usually starts
START_RE = re.compile(r"(job description|about the role|the role|responsibilities|what you'?ll do|"
                      r"your role|key responsibilities|role overview|description)\s*:?", re.I)


def html_to_text(s):
    s = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", s or "", flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(html.unescape(s))  # Greenhouse double-escapes
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\n\s*\n+", "\n", s)).strip()


def tech_stack(text):
    return [name for name, rx in TECH_RES if rx.search(text)]


def experience(text, title):
    """Shortest experience requirement mentioned near the word 'experience'."""
    best = None
    for m in EXP_RE.finditer(text):
        if "experience" not in text[max(0, m.start() - 80): m.end() + 80].lower():
            continue
        lo, hi, plus, single = m.groups()
        if lo:
            low, label = int(lo), f"{int(lo)}–{int(hi)} years"
        elif plus:
            low, label = int(plus), f"{int(plus)}+ years"
        else:
            low, label = int(single), f"{int(single)}+ years"
        if low <= 20 and (best is None or low < best[0]):
            best = (low, label)
    if best:
        return best[1]
    if FRESHER_TEXT_RE.search(text):
        return "Fresher friendly"
    return {2: "Fresher / intern", 1: "Entry level"}.get(core.fresher_rank(title), "Not stated")


def excerpt(text, limit=700):
    """Skip the company boilerplate most descriptions open with, when a heading marks the role."""
    m = START_RE.search(text)
    body = text[m.end():] if m and m.start() < len(text) * 0.6 else text
    body = body.strip(" :-\n")
    return body if len(body) <= limit else body[:limit].rsplit(" ", 1)[0] + "…"


def parse_date(value):
    """'2026-10-15', '2026-10-15T09:00:00Z' or 'October 20, 2026' -> '2026-10-15'."""
    value = (value or "").strip()
    for fmt, n in (("%Y-%m-%d", 10), ("%B %d, %Y", None), ("%b %d, %Y", None)):
        try:
            return datetime.strptime(value[:n] if n else value, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def build(text, title, employment="", category="", posted_date=""):
    text = text or ""
    return {
        "tech": tech_stack(f"{title}\n{text}"),
        "experience": experience(text, title),
        "employment": employment.replace("-", " ").strip().capitalize() if employment else "",
        "category": category or "",
        "posted_date": parse_date(posted_date),
        "summary": excerpt(text),
    }
