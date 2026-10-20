"""jobwatch dashboard (Streamlit).

Run:  streamlit run app.py

The page reads last_run.json (written by "Refresh" here, or by main.py /
GitHub Actions). Refreshing here only fetches and lists jobs: it does NOT send
Telegram alerts and does NOT change seen_jobs.json, so the twice-daily alerts
stay correct.
"""
import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta, timezone

import streamlit as st

import config
import core
import details
import main

SAMPLE_FILE = core.BASE / "sample_last_run.json"
IST = timezone(timedelta(hours=5, minutes=30))
PAGE_SIZE = 20
MAX_EXP = {"Any experience": None, "Up to 1 year": 1, "Up to 2 years": 2,
           "Up to 3 years": 3, "Up to 5 years": 5}
ROLE_FAMILIES = [
    ("AI / ML", r"\b(ai|ml|machine learning|deep learning|nlp|llm|gen ?ai|computer vision)\b"),
    ("Data science", r"data scien"),
    ("Data engineering", r"data engineer|\betl\b|pipeline|big data|pyspark|hadoop"),
    ("Analytics", r"analy|business intelligence|\bbi\b"),
]

st.set_page_config(page_title="jobwatch", page_icon="🔔", layout="centered")

st.markdown("""
<style>
.block-container {padding-top: 2.2rem; max-width: 900px;}
.title {font-size: 1.9rem; font-weight: 800; letter-spacing: -.02em; margin: 0;}
.sub {color: #64748B; font-size: .9rem; margin-top: .1rem;}
div[class*="st-key-job-"] {background: #FFFFFF; border-radius: 12px !important;
  transition: border-color .15s ease, box-shadow .15s ease;}
div[class*="st-key-job-"]:hover {border-color: #A5B4FC !important;
  box-shadow: 0 6px 20px -10px rgba(79,70,229,.35);}
.co {color: #4F46E5; font-size: .78rem; font-weight: 700;}
.role {font-size: 1.05rem; font-weight: 700; color: #0F172A; line-height: 1.3; margin: .1rem 0;}
.meta {color: #64748B; font-size: .85rem;}
.tag {display: inline-block; padding: .12rem .5rem; margin: .35rem .3rem 0 0; border-radius: 6px;
  background: #F1F5F9; color: #334155; font-size: .75rem; font-weight: 500;}
.new {display: inline-block; padding: .05rem .45rem; margin-left: .4rem; border-radius: 6px;
  background: #DCFCE7; color: #166534; font-size: .7rem; font-weight: 700; vertical-align: middle;}
.fact {background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 10px; padding: .6rem .75rem;}
.fact .k {color: #64748B; font-size: .72rem;}
.fact .v {color: #0F172A; font-size: .92rem; font-weight: 600; margin-top: .1rem;}
.label {color: #64748B; font-size: .78rem; font-weight: 600; margin: 1rem 0 .3rem;}
</style>
""", unsafe_allow_html=True)

esc = html.escape


# ---------- data ----------

def load_data():
    data = core.load_last_run()
    if data is None and SAMPLE_FILE.exists():
        return json.loads(SAMPLE_FILE.read_text(encoding="utf-8")), True
    return data, False


def refresh():
    with st.status("Fetching jobs…") as status:
        jobs, errors = main.collect()
        matches = core.rank([j for j in jobs if core.relevant(j)])
        seen = core.load_seen()
        new = sum(core.key(j) not in seen for j in matches)
        data = core.save_last_run(matches, errors, main.run_counts(jobs, matches, new))
        status.update(label=f"{len(matches)} openings found", state="complete")
    return data


def updated_label(data, is_sample):
    if is_sample:
        return "sample data"
    try:
        mins = int((datetime.now(timezone.utc) - datetime.fromisoformat(data["ran_at"]))
                   .total_seconds() // 60)
    except (KeyError, TypeError, ValueError):
        return ""
    if mins < 60:
        return f"updated {max(mins, 1)} min ago"
    return f"updated {mins // 60} h ago" if mins < 2880 else f"updated {mins // 1440} days ago"


def posted(job, ran_at):
    """(ISO date or "", days since posting or None)."""
    try:
        today = datetime.fromisoformat(ran_at).astimezone(IST).date()
    except (TypeError, ValueError):
        today = datetime.now(IST).date()
    iso = (job.get("details") or {}).get("posted_date") or details.parse_date(job.get("posted"))
    if iso:
        return iso, max((today - date.fromisoformat(iso)).days, 0)
    text = job.get("posted", "").lower()
    m = re.search(r"(\d+)\+?\s*days? ago", text)
    days = 0 if "today" in text else 1 if "yesterday" in text else int(m.group(1)) if m else None
    return ("", None) if days is None else ((today - timedelta(days=days)).isoformat(), days)


def ago(days):
    return "" if days is None else "today" if days == 0 else "yesterday" if days == 1 else f"{days}d ago"


def city(loc):
    loc = (loc or "").strip()
    if not loc or core.MULTI_LOC_RE.match(loc):
        return loc or "—"
    loc = re.sub(r"\s*\([^()]*\)\s*$", "", loc)
    names = []
    for part in loc.split(";"):
        name = re.sub(r"\(.*?\)", "", re.split(r"\s+-\s+|,", part)[0]).strip()
        if name and name not in names:
            names.append(name)
    return ", ".join(names[:2]) + (f" +{len(names) - 2}" if len(names) > 2 else "")


def min_years(exp):
    if exp.lower().startswith("fresher"):
        return 0
    m = re.match(r"(\d+)", exp)
    return int(m.group(1)) if m else None


def role_family(title, category):
    for name, rx in ROLE_FAMILIES:
        if re.search(rx, title, re.I):
            return name
    return category or "Other"


def to_row(job, seen, ran_at):
    d = job.get("details") or {}
    iso, days = posted(job, ran_at)
    exp = d.get("experience") or details.experience("", job["title"])
    return {"job": job, "key": core.key(job), "id": hashlib.md5(core.key(job).encode()).hexdigest()[:10],
            "new": core.key(job) not in seen, "iso": iso, "days": days, "exp": exp,
            "exp_min": min_years(exp), "tech": d.get("tech", []), "type": d.get("employment", ""),
            "role": role_family(job["title"], d.get("category", "")), "summary": d.get("summary", "")}


# ---------- views ----------

def fact(col, k, v):
    col.markdown(f"<div class='fact'><div class='k'>{esc(k)}</div><div class='v'>{esc(v)}</div></div>",
                 unsafe_allow_html=True)


@st.dialog("Details", width="large")
def show(r):
    j = r["job"]
    st.markdown(f"<div class='co'>{esc(j['company'])}</div><div class='role' style='font-size:1.4rem'>"
                f"{esc(j['title'])}</div>", unsafe_allow_html=True)
    a, b = st.columns(2)
    fact(a, "Role", " · ".join(x for x in (r["role"], r["type"]) if x))
    fact(b, "Experience", r["exp"])
    st.write("")
    a, b = st.columns(2)
    fact(a, "Posted", f"{date.fromisoformat(r['iso']):%d %b %Y}" if r["iso"] else "—")
    fact(b, "Location", j.get("location") or "—")
    if r["tech"]:
        st.markdown("<div class='label'>Tech stack</div>" +
                    "".join(f"<span class='tag'>{esc(t)}</span>" for t in r["tech"]),
                    unsafe_allow_html=True)
    if r["summary"]:
        with st.expander("About the role"):
            st.write(r["summary"])
    st.markdown(f"<div class='label'>Referral message · Job ID {esc(j['job_id'])}</div>",
                unsafe_allow_html=True)
    st.code(core.referral_text(j), language=None, wrap_lines=True)
    st.link_button("Apply", j["url"], type="primary", width="stretch")


def card(r):
    j = r["job"]
    with st.container(border=True, key=f"job-{r['id']}"):
        left, right = st.columns([4, 1.3], vertical_alignment="center")
        meta = " · ".join(x for x in (city(j.get("location")), r["exp"], ago(r["days"])) if x)
        left.markdown(
            f"<div class='co'>{esc(j['company'])}{'<span class=new>NEW</span>' if r['new'] else ''}</div>"
            f"<div class='role'>{esc(j['title'])}</div><div class='meta'>{esc(meta)}</div>"
            + "".join(f"<span class='tag'>{esc(t)}</span>" for t in r["tech"][:4]),
            unsafe_allow_html=True)
        with right:
            if st.button("View", key=f"v-{r['id']}", width="stretch"):
                show(r)
            st.link_button("Apply", j["url"], width="stretch")


# ---------- page ----------

data, is_sample = load_data()

head, btn = st.columns([4, 1], vertical_alignment="bottom")
with btn:
    if st.button("Refresh", icon=":material/refresh:", width="stretch"):
        data, is_sample = refresh(), False

seen = core.load_seen()
ran_at = (data or {}).get("ran_at")
rows = [to_row(j, seen, ran_at) for j in (data or {}).get("jobs", [])]
new_count = sum(r["new"] for r in rows)
head.markdown(
    "<div class='title'>🔔 jobwatch</div><div class='sub'>"
    + esc(" · ".join(x for x in (f"{len(rows)} openings", f"{new_count} new",
                                 updated_label(data or {}, is_sample)) if x))
    + "</div>", unsafe_allow_html=True)

if is_sample:
    st.info("Sample data. Tap Refresh to load real jobs.")

st.write("")
q, e, c = st.columns([2.2, 1.3, 1.3])
text = q.text_input("Search", placeholder="Search role, company or skill",
                    label_visibility="collapsed").lower().strip()
max_exp = MAX_EXP[e.selectbox("Experience", list(MAX_EXP), label_visibility="collapsed")]
companies = ["All companies"] + sorted({r["job"]["company"] for r in rows})
company = c.selectbox("Company", companies, label_visibility="collapsed")

view = [r for r in rows
        if (not text or text in f"{r['job']['title']} {r['job']['company']} {' '.join(r['tech'])}".lower())
        and (max_exp is None or r["exp_min"] is None or r["exp_min"] <= max_exp)
        and (company == "All companies" or r["job"]["company"] == company)]

if not view:
    st.write("No openings match.")
limit = st.session_state.get("limit", PAGE_SIZE)
for r in view[:limit]:
    card(r)
if len(view) > limit:
    if st.button(f"Show more ({len(view) - limit})", width="stretch"):
        st.session_state.limit = limit + PAGE_SIZE
        st.rerun()

errors = (data or {}).get("errors", [])
if errors:
    st.caption(f"{len(errors)} source(s) failed in the last fetch: "
               + ", ".join(e.split(":", 1)[0] for e in errors))
