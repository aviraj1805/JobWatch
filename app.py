"""jobwatch dashboard (Streamlit).

Run:  streamlit run app.py

The page reads last_run.json (written by "Refresh now" here, or by main.py /
GitHub Actions). Refreshing here only fetches and lists jobs: it does NOT send
Telegram alerts and does NOT change seen_jobs.json, so the twice-daily alerts
stay correct.
"""
import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta, timezone

import altair as alt
import pandas as pd
import streamlit as st

import config
import core
import details
import main

SAMPLE_FILE = core.BASE / "sample_last_run.json"
IST = timezone(timedelta(hours=5, minutes=30))
SCHEDULE_IST = [(9, 0), (19, 30)]  # keep in step with .github/workflows/jobwatch.yml
LEVELS = {2: "Fresher", 1: "Entry", 0: "Other"}
LEVEL_COLORS = {"Fresher": "#34D399", "Entry": "#818CF8", "Other": "#64748B"}
SCORE_CAP = 6  # title skill scores above this are rare; the bars are scaled to it
PAGE_SIZE = 12
MAX_EXP = {"Any": None, "Up to 1 year": 1, "Up to 2 years": 2, "Up to 3 years": 3, "Up to 5 years": 5}
POSTED_WITHIN = {"Any time": None, "Last 3 days": 3, "Last 7 days": 7, "Last 14 days": 14}
SORTS = ["Best match", "Newest first", "Least experience", "Company A–Z"]
ROLE_FAMILIES = [
    ("AI / ML", r"\b(ai|ml|machine learning|deep learning|nlp|llm|gen ?ai|computer vision)\b"),
    ("Data science", r"data scien"),
    ("Data engineering", r"data engineer|\betl\b|pipeline|big data|pyspark|hadoop"),
    ("Analytics", r"analy|business intelligence|\bbi\b"),
]
FILTER_DEFAULTS = {"f_text": "", "f_companies": [], "f_levels": [], "f_status": "All",
                   "f_score": 0, "f_tech": [], "f_cities": [], "f_exp": "Any",
                   "f_days": "Any time"}

st.set_page_config(page_title="jobwatch · Job intelligence", page_icon="🔔", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1440px;}
.st-key-hero {
  background:
    radial-gradient(900px 260px at 0% 0%, rgba(129,140,248,.32), transparent 60%),
    radial-gradient(700px 260px at 100% 0%, rgba(52,211,153,.16), transparent 60%),
    linear-gradient(135deg, #141B36 0%, #0D1326 100%);
  border: 1px solid rgba(129,140,248,.25); border-radius: 18px; padding: 1.3rem 1.5rem;
}
.hero-eyebrow {font-size: .72rem; letter-spacing: .16em; text-transform: uppercase;
  color: #A5B4FC; font-weight: 700;}
.hero-title {font-size: 2.2rem; font-weight: 800; line-height: 1.1; margin: .25rem 0 .35rem;
  background: linear-gradient(90deg, #FFFFFF, #C7D2FE 60%, #6EE7B7);
  -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;}
.hero-sub {color: #9AA4C7; font-size: .93rem; max-width: 60ch;}
.pulse {display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #34D399;
  margin-right: .45rem; vertical-align: middle; animation: pulse 2s infinite;}
@keyframes pulse {0% {box-shadow: 0 0 0 0 rgba(52,211,153,.6);}
  70% {box-shadow: 0 0 0 8px rgba(52,211,153,0);} 100% {box-shadow: 0 0 0 0 rgba(52,211,153,0);}}
.status-row {display: flex; justify-content: space-between; gap: .75rem; padding: .45rem 0;
  border-bottom: 1px dashed rgba(148,163,184,.18); font-size: .84rem;}
.status-row:last-child {border-bottom: 0;}
.status-row .k {color: #8B95B7;} .status-row .v {font-weight: 650; text-align: right;}
.chip {display: inline-flex; align-items: center; padding: .16rem .55rem; border-radius: 999px;
  font-size: .72rem; font-weight: 600; border: 1px solid rgba(148,163,184,.25);
  background: rgba(148,163,184,.08); color: #CBD5E1; margin: .1rem .25rem .1rem 0; white-space: nowrap;}
.chip.fresher {color: #6EE7B7; border-color: rgba(52,211,153,.35); background: rgba(52,211,153,.10);}
.chip.entry {color: #A5B4FC; border-color: rgba(129,140,248,.35); background: rgba(129,140,248,.10);}
.chip.new {color: #FCD34D; border-color: rgba(252,211,77,.35); background: rgba(252,211,77,.10);}
.chip.tech {color: #7DD3FC; border-color: rgba(125,211,252,.22); background: rgba(125,211,252,.06);
  font-weight: 500;}
.chip.warn {color: #FCA5A5; border-color: rgba(248,113,113,.35); background: rgba(248,113,113,.08);}
.kpi {border: 1px solid rgba(148,163,184,.16); border-radius: 14px; padding: .95rem 1.05rem;
  background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.01));}
.kpi-label {font-size: .7rem; text-transform: uppercase; letter-spacing: .09em; color: #8B95B7;
  font-weight: 700;}
.kpi-value {font-size: 1.85rem; font-weight: 800; margin-top: .1rem;}
.kpi-foot {font-size: .76rem; color: #8B95B7;}
.kpi .bar {height: 4px; border-radius: 4px; background: rgba(148,163,184,.15); margin-top: .55rem;
  overflow: hidden;}
.kpi .bar > span {display: block; height: 100%; background: linear-gradient(90deg, #818CF8, #34D399);}
div[class*="st-key-card-"] {border-radius: 14px !important;
  background: linear-gradient(180deg, rgba(255,255,255,.035), rgba(255,255,255,.008));
  transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;}
div[class*="st-key-card-"]:hover {transform: translateY(-2px);
  border-color: rgba(129,140,248,.6) !important; box-shadow: 0 12px 32px -14px rgba(99,102,241,.55);}
.card-head {display: flex; justify-content: space-between; align-items: center; gap: .5rem;}
.card-co {font-size: .72rem; color: #A5B4FC; font-weight: 700; text-transform: uppercase;
  letter-spacing: .07em;}
.card-title {font-size: 1.02rem; font-weight: 700; line-height: 1.3; margin: .2rem 0 .3rem;
  min-height: 2.6em;}
.card-meta {font-size: .8rem; color: #94A3B8; margin-bottom: .3rem;}
.sum-title {font-size: 1.45rem; font-weight: 800; line-height: 1.2; margin: .15rem 0 .4rem;}
.tile {border: 1px solid rgba(148,163,184,.16); border-radius: 12px; padding: .7rem .85rem;
  background: rgba(255,255,255,.025); min-height: 4.6rem;}
.tile-label {font-size: .66rem; text-transform: uppercase; letter-spacing: .09em; color: #8B95B7;
  font-weight: 700;}
.tile-value {font-size: .93rem; font-weight: 650; margin-top: .2rem; word-break: break-word;}
.section-title {font-size: .8rem; text-transform: uppercase; letter-spacing: .09em; color: #8B95B7;
  font-weight: 700; margin: .9rem 0 .35rem;}
.muted {color: #8B95B7; font-size: .85rem;}
.brand {font-weight: 800; font-size: 1.3rem;}
.stTabs [data-baseweb="tab-list"] {gap: .4rem;}
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
    with st.status("Scanning career sites and reading job details…", expanded=True) as status:
        def report(name, count, error):
            if error:
                st.write(f":red[:material/error:] **{name}**: {error}")
            else:
                st.write(f":green[:material/check_circle:] **{name}**: {count} postings")

        jobs, errors = main.collect(report=report)
        matches = core.rank([j for j in jobs if core.relevant(j)])
        seen = core.load_seen()
        new = sum(core.key(j) not in seen for j in matches)
        data = core.save_last_run(matches, errors, main.run_counts(jobs, matches, new))
        status.update(label=f"Scan complete: {len(matches)} matches", state="complete", expanded=False)
    return data


def parse_ran_at(data):
    try:
        return datetime.fromisoformat(data.get("ran_at", ""))
    except (TypeError, ValueError):
        return None


def ago(dt):
    mins = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if mins < 1:
        return "just now"
    if mins < 60:
        return f"{mins} min ago"
    if mins < 48 * 60:
        return f"{mins // 60} h ago"
    return f"{mins // 1440} days ago"


def next_run(now):
    slots = [(now + timedelta(days=d)).replace(hour=h, minute=m, second=0, microsecond=0)
             for d in (0, 1) for h, m in SCHEDULE_IST]
    return min(t for t in slots if t > now)


def posted_info(job, ran):
    """(ISO date or "", days since posting or None)."""
    today = (ran or datetime.now(timezone.utc)).astimezone(IST).date()
    iso = (job.get("details") or {}).get("posted_date") or details.parse_date(job.get("posted"))
    if iso:
        return iso, max((today - date.fromisoformat(iso)).days, 0)
    text = job.get("posted", "").lower()
    m = re.search(r"(\d+)\+?\s*days? ago", text)
    days = 0 if "today" in text else 1 if "yesterday" in text else int(m.group(1)) if m else None
    if days is None:
        return "", None
    return (today - timedelta(days=days)).isoformat(), days


def posted_label(iso, days, long=False):
    if days is None:
        return "Date not listed"
    rel = "today" if days == 0 else "yesterday" if days == 1 else f"{days} days ago"
    if not long:
        return f"Posted {rel}"
    return f"{date.fromisoformat(iso):%d %b %Y} · {rel}"


def cities(loc):
    loc = (loc or "").strip()
    if not loc:
        return ["Unspecified"]
    if core.MULTI_LOC_RE.match(loc):
        return ["Multiple"]
    loc = re.sub(r"\s*\([^()]*\)\s*$", "", loc)  # trailing "(India)" / "(Hybrid)"
    out = []
    for part in loc.split(";"):
        name = re.sub(r"\(.*?\)", "", re.split(r"\s+-\s+|,", part)[0]).strip()
        if name and name not in out:
            out.append(name)
    return out or ["Unspecified"]


def min_years(exp):
    """'2–4 years' -> 2, 'Fresher …' -> 0, unknown -> None."""
    if exp.lower().startswith("fresher"):
        return 0
    m = re.match(r"(\d+)", exp)
    return int(m.group(1)) if m else None


def role_family(title, category):
    for name, rx in ROLE_FAMILIES:
        if re.search(rx, title, re.I):
            return name
    return category or "Other"


def build_rows(jobs, seen, ran):
    rows = []
    for order, j in enumerate(jobs):
        d = j.get("details") or {}
        rank = core.fresher_rank(j["title"])
        iso, days = posted_info(j, ran)
        exp = d.get("experience") or details.experience("", j["title"])
        rows.append({
            "job": j, "key": core.key(j), "hash": hashlib.md5(core.key(j).encode()).hexdigest()[:10],
            "order": order, "company": j["company"], "title": j["title"], "job_id": j["job_id"],
            "rank": rank, "level": LEVELS[rank], "score": core.skill_score(j),
            "status": "Alerted" if core.key(j) in seen else "New",
            "cities": cities(j.get("location")), "location": j.get("location") or "Not listed",
            "posted_iso": iso, "days": days, "tech": d.get("tech", []), "experience": exp,
            "exp_min": min_years(exp), "employment": d.get("employment", ""),
            "family": role_family(j["title"], d.get("category", "")),
            "summary": d.get("summary", ""), "has_details": bool(d), "url": j["url"],
        })
    return rows


def apply_filters(rows):
    s = st.session_state
    needle = s.f_text.lower().strip()
    max_exp, within = MAX_EXP[s.f_exp], POSTED_WITHIN[s.f_days]
    out = []
    for r in rows:
        if needle and needle not in f"{r['title']} {r['company']} {' '.join(r['tech'])}".lower():
            continue
        if s.f_companies and r["company"] not in s.f_companies:
            continue
        if s.f_levels and r["level"] not in s.f_levels:
            continue
        if s.f_status in ("New", "Alerted") and r["status"] != s.f_status:
            continue
        if r["score"] < s.f_score:
            continue
        if s.f_tech and not set(s.f_tech) & set(r["tech"]):
            continue
        if s.f_cities and not set(s.f_cities) & set(r["cities"]):
            continue
        # Unknown experience / date is kept: the filter only drops what is known not to fit.
        if max_exp is not None and r["exp_min"] is not None and r["exp_min"] > max_exp:
            continue
        if within is not None and r["days"] is not None and r["days"] > within:
            continue
        out.append(r)
    return out


def sort_rows(rows, how):
    if how == "Newest first":
        return sorted(rows, key=lambda r: (r["days"] is None, r["days"] or 0, r["order"]))
    if how == "Least experience":
        return sorted(rows, key=lambda r: (r["exp_min"] is None, r["exp_min"] or 0, r["order"]))
    if how == "Company A–Z":
        return sorted(rows, key=lambda r: (r["company"].lower(), r["order"]))
    return sorted(rows, key=lambda r: r["order"])  # last_run.json is stored in ranked order


def reset_filters():
    for k, v in FILTER_DEFAULTS.items():
        st.session_state[k] = v


def configured_sources():
    out = [(s["company"], "Workday" if s["url"].startswith("http") else "Custom site (no fetcher yet)",
            s["url"].startswith("http")) for s in config.WORKDAY_SITES]
    out += [(b["company"], "Greenhouse", True) for b in config.GREENHOUSE_BOARDS]
    out += [(s["company"], "Lever", True) for s in config.LEVER_SITES]
    out += [("Amazon", "Amazon Jobs", config.ENABLE_AMAZON)]
    out += [("Gmail alerts", "Gmail (read-only)", config.ENABLE_GMAIL)]
    return out


# ---------- small renderers ----------

def chip(text, kind=""):
    return f"<span class='chip {kind}'>{esc(text)}</span>"


def level_chip(level):
    return chip(level, {"Fresher": "fresher", "Entry": "entry"}.get(level, ""))


def tech_chips(tech, limit=None):
    shown = tech if limit is None else tech[:limit]
    more = f"<span class='chip'>+{len(tech) - len(shown)}</span>" if len(tech) > len(shown) else ""
    return "".join(chip(t, "tech") for t in shown) + more


def kpi(col, label, value, foot, pct=None):
    bar = f"<div class='bar'><span style='width:{max(0, min(pct, 1)) * 100:.0f}%'></span></div>" \
        if pct is not None else ""
    col.markdown(f"<div class='kpi'><div class='kpi-label'>{esc(label)}</div>"
                 f"<div class='kpi-value'>{esc(str(value))}</div>"
                 f"<div class='kpi-foot'>{esc(foot)}</div>{bar}</div>", unsafe_allow_html=True)


def tile(col, label, value):
    col.markdown(f"<div class='tile'><div class='tile-label'>{esc(label)}</div>"
                 f"<div class='tile-value'>{esc(value)}</div></div>", unsafe_allow_html=True)


def show_chart(chart, height=260):
    st.altair_chart(
        chart.properties(height=height).configure_view(strokeWidth=0)
        .configure_axis(grid=False, domain=False, tickColor="transparent",
                        labelColor="#94A3B8", titleColor="#94A3B8", labelLimit=180)
        .configure_legend(labelColor="#CBD5E1", orient="top", title=None),
        width="stretch")


def open_job(key):
    st.session_state.open_job = key


def render_summary(r, ns):
    """The full opening summary: used by the dialog and by the table's detail panel."""
    j = r["job"]
    chips = (chip("New", "new") if r["status"] == "New" else chip("Alerted")) + level_chip(r["level"])
    if r["employment"]:
        chips += chip(r["employment"])
    st.markdown(f"<div class='card-co'>{esc(r['company'])}</div>"
                f"<div class='sum-title'>{esc(r['title'])}</div><div>{chips}</div>",
                unsafe_allow_html=True)

    a, b, c, d = st.columns(4)
    role = " · ".join(x for x in (r["family"], r["employment"]) if x)
    tile(a, "Job role", role)
    tile(b, "Experience", r["experience"])
    tile(c, "Posted", posted_label(r["posted_iso"], r["days"], long=True))
    tile(d, "Location", r["location"])

    st.markdown("<div class='section-title'>Tech stack</div>", unsafe_allow_html=True)
    if r["tech"]:
        st.markdown(tech_chips(r["tech"]), unsafe_allow_html=True)
    else:
        st.markdown("<span class='muted'>No specific tools named in the description.</span>"
                    if r["has_details"] else
                    "<span class='muted'>No description from this source. Open the posting.</span>",
                    unsafe_allow_html=True)

    st.progress(min(r["score"] / SCORE_CAP, 1.0),
                text=f"Title skill match: {min(r['score'], SCORE_CAP)} / {SCORE_CAP} "
                     "(SKILL_WEIGHTS in config.py)")

    if r["summary"]:
        st.markdown("<div class='section-title'>About the role</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='muted' style='white-space:pre-line'>{esc(r['summary'])}</div>",
                    unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Job ID and referral message</div>", unsafe_allow_html=True)
    left, right = st.columns([1, 2.2])
    with left:
        st.code(r["job_id"], language=None)
    with right:
        name = st.text_input("Referrer's first name", key=f"ref-{ns}-{r['hash']}",
                             value=config.REFERRERS.get(r["company"], ""),
                             placeholder="blank = generic greeting", label_visibility="collapsed")
    st.code(core.referral_text(j, name or None), language=None, wrap_lines=True)
    st.link_button("Open posting and apply", r["url"], type="primary",
                   icon=":material/open_in_new:", width="stretch")


@st.dialog("Opening summary", width="large")
def job_dialog(r):
    render_summary(r, "dlg")


def job_card(r, ns):
    with st.container(border=True, key=f"card-{ns}-{r['hash']}"):
        status = chip("New", "new") if r["status"] == "New" else ""
        where = ", ".join(r["cities"][:2]) + (f" +{len(r['cities']) - 2}" if len(r["cities"]) > 2 else "")
        st.markdown(
            f"<div class='card-head'><span class='card-co'>{esc(r['company'])}</span>{status}</div>"
            f"<div class='card-title'>{esc(r['title'])}</div>"
            f"<div class='card-meta'>📍 {esc(where)} &nbsp;·&nbsp; 🕒 "
            f"{esc(posted_label(r['posted_iso'], r['days']))}</div>"
            f"<div>{level_chip(r['level'])}{chip(r['experience'])}</div>"
            f"<div style='min-height:1.9rem'>{tech_chips(r['tech'], 3)}</div>",
            unsafe_allow_html=True)
        a, b = st.columns(2)
        a.button("Summary", key=f"open-{ns}-{r['hash']}", icon=":material/visibility:",
                 width="stretch", on_click=open_job, args=(r["key"],))
        b.link_button("Apply", r["url"], icon=":material/open_in_new:", width="stretch")


@st.fragment(run_every="30s")
def live_status(ran, is_sample, n_sources, n_errors):
    now = datetime.now(IST)
    nxt = next_run(now)
    mins = int((nxt - now).total_seconds() // 60)
    last = "Sample data" if is_sample else (ago(ran) if ran else "Unknown")
    health = f"{n_sources - n_errors}/{n_sources} healthy" if n_errors else f"{n_sources} healthy"
    rows = [("Last scan", last),
            ("Next alert run", f"{nxt:%H:%M} IST · in {mins // 60} h {mins % 60:02d} m"),
            ("Sources", health)]
    st.markdown("".join(f"<div class='status-row'><span class='k'>{esc(k)}</span>"
                        f"<span class='v'>{esc(v)}</span></div>" for k, v in rows),
                unsafe_allow_html=True)


# ---------- page ----------

for k, v in FILTER_DEFAULTS.items():
    st.session_state.setdefault(k, v)

data, is_sample = load_data()
seen = core.load_seen()

with st.sidebar:
    st.markdown("<div class='brand'>🔔 jobwatch</div>"
                "<div class='muted'>Job intelligence console</div>", unsafe_allow_html=True)
    st.write("")
    if st.button("Refresh now", type="primary", icon=":material/refresh:", width="stretch",
                 help="Fetch every source now. Does not send alerts or change seen_jobs.json."):
        data, is_sample = refresh(), False

all_jobs = data["jobs"] if data else []
ran = parse_ran_at(data or {})
rows = build_rows(all_jobs, seen, ran)
active_sources = [s for s in configured_sources() if s[2]]
errors = (data or {}).get("errors", [])

with st.sidebar:
    st.caption("Alerts are sent only by the scheduled GitHub Actions run.")
    st.divider()
    st.markdown("**Filters**")
    st.text_input("Search", key="f_text", placeholder="Title, company or tool",
                  label_visibility="collapsed")
    st.pills("Level", list(LEVELS.values()), selection_mode="multi", key="f_levels")
    st.segmented_control("Status", ["All", "New", "Alerted"], key="f_status")
    st.selectbox("Max experience asked", list(MAX_EXP), key="f_exp",
                 help="Openings that don't state experience are kept.")
    st.selectbox("Posted", list(POSTED_WITHIN), key="f_days")
    st.multiselect("Companies", sorted({r["company"] for r in rows}), key="f_companies")
    st.multiselect("Tech stack", sorted({t for r in rows for t in r["tech"]}), key="f_tech")
    st.multiselect("City", sorted({c for r in rows for c in r["cities"]}), key="f_cities")
    st.slider("Min. title skill score", 0, SCORE_CAP, key="f_score")
    st.button("Reset filters", icon=":material/restart_alt:", width="stretch", on_click=reset_filters)

view = apply_filters(rows)

with st.container(key="hero"):
    left, right = st.columns([2.1, 1], vertical_alignment="center", gap="large")
    left.markdown(
        "<div class='hero-eyebrow'><span class='pulse'></span>Job intelligence · Pune</div>"
        "<div class='hero-title'>jobwatch</div>"
        f"<div class='hero-sub'>Fresher and entry-level data &amp; AI openings from "
        f"{len(active_sources)} sources, filtered, ranked and summarised twice a day.</div>",
        unsafe_allow_html=True)
    with right:
        live_status(ran, is_sample, len(active_sources), len(errors))

if is_sample:
    st.warning("Showing **sample data** (fictional companies) so you can see the layout. "
               "Click **Refresh now** in the sidebar to fetch real openings.", icon=":material/science:")

st.write("")
tab_over, tab_jobs, tab_ref, tab_src = st.tabs([
    ":material/insights: Overview",
    f":material/work: Openings ({len(view)})",
    ":material/forward_to_inbox: Referral studio",
    ":material/hub: Sources",
])

# ----- Overview -----
with tab_over:
    counts = (data or {}).get("counts", {})
    c = st.columns(5)
    kpi(c[0], "Postings scanned", f"{counts.get('fetched', 0):,}",
        f"across {len(active_sources)} sources")
    kpi(c[1], "Relevant matches", len(view), f"of {len(rows)} before filters",
        len(view) / len(rows) if rows else 0)
    new_n = sum(r["status"] == "New" for r in view)
    kpi(c[2], "New since last alert", new_n, "not yet sent to Telegram", new_n / len(view) if view else 0)
    low = sum(r["exp_min"] is not None and r["exp_min"] <= 2 for r in view)
    kpi(c[3], "≤ 2 yrs experience", low, "stated in the description", low / len(view) if view else 0)
    fresh = sum(r["rank"] > 0 for r in view)
    kpi(c[4], "Fresher / entry titles", fresh, "intern, trainee, graduate, junior",
        fresh / len(view) if view else 0)

    if not view:
        st.info("No openings match these filters. Try **Reset filters** in the sidebar.")
    else:
        df = pd.DataFrame([{k: r[k] for k in ("company", "level", "experience", "exp_min", "days")}
                           for r in view])
        level_scale = alt.Scale(domain=list(LEVEL_COLORS), range=list(LEVEL_COLORS.values()))
        st.write("")
        a, b = st.columns([1.5, 1], gap="large")
        with a:
            st.markdown("<div class='section-title'>Matches by company</div>", unsafe_allow_html=True)
            show_chart(alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18).encode(
                x=alt.X("count():Q", title=None, axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("company:N", sort="-x", title=None),
                color=alt.Color("level:N", scale=level_scale),
                tooltip=["company", "level", alt.Tooltip("count():Q", title="Openings")]))
        with b:
            st.markdown("<div class='section-title'>Seniority mix</div>", unsafe_allow_html=True)
            mix = df.groupby("level").size().reset_index(name="n")
            donut = alt.Chart(mix).mark_arc(innerRadius=70, cornerRadius=5, padAngle=.02).encode(
                theta="n:Q", color=alt.Color("level:N", scale=level_scale),
                tooltip=["level", alt.Tooltip("n:Q", title="Openings")])
            centre = alt.Chart(pd.DataFrame({"t": [str(len(view))]})).mark_text(
                fontSize=30, fontWeight="bold", color="#E7EAF6").encode(text="t:N")
            show_chart(alt.layer(donut, centre))

        a, b = st.columns([1.5, 1], gap="large")
        with a:
            st.markdown("<div class='section-title'>Most requested tech</div>", unsafe_allow_html=True)
            tech = pd.Series([t for r in view for t in r["tech"]]).value_counts().head(12)
            if tech.empty:
                st.caption("No tech stack data yet. It is filled in on the next fetch.")
            else:
                tdf = tech.rename_axis("tech").reset_index(name="n")
                show_chart(alt.Chart(tdf).mark_bar(cornerRadiusEnd=4, height=16, color="#38BDF8").encode(
                    x=alt.X("n:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                    y=alt.Y("tech:N", sort="-x", title=None),
                    tooltip=["tech", alt.Tooltip("n:Q", title="Openings")]), height=300)
        with b:
            st.markdown("<div class='section-title'>Experience asked</div>", unsafe_allow_html=True)
            order = ["0–1 yrs", "2–3 yrs", "4–5 yrs", "6+ yrs", "Not stated"]
            df["bucket"] = df["exp_min"].map(
                lambda v: "Not stated" if pd.isna(v) else order[0] if v <= 1 else order[1]
                if v <= 3 else order[2] if v <= 5 else order[3])
            show_chart(alt.Chart(df).mark_bar(cornerRadiusEnd=4, width=34).encode(
                x=alt.X("bucket:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("count():Q", title=None, axis=alt.Axis(tickMinStep=1)),
                color=alt.Color("bucket:N", sort=order, legend=None, scale=alt.Scale(
                    domain=order, range=["#34D399", "#A3E635", "#FBBF24", "#F87171", "#64748B"])),
                tooltip=[alt.Tooltip("bucket:N", title="Experience"),
                         alt.Tooltip("count():Q", title="Openings")]), height=300)

        a, b = st.columns([1.5, 1], gap="large")
        with a:
            st.markdown("<div class='section-title'>Where the roles are</div>", unsafe_allow_html=True)
            cdf = pd.Series([ci for r in view for ci in r["cities"]]).value_counts().head(10) \
                .rename_axis("city").reset_index(name="n")
            show_chart(alt.Chart(cdf).mark_bar(cornerRadiusEnd=4, height=16, color="#A78BFA").encode(
                x=alt.X("n:Q", title=None, axis=alt.Axis(tickMinStep=1)),
                y=alt.Y("city:N", sort="-x", title=None),
                tooltip=["city", alt.Tooltip("n:Q", title="Openings")]))
        with b:
            st.markdown("<div class='section-title'>Posting freshness</div>", unsafe_allow_html=True)
            order = ["Today", "1–3 d", "4–7 d", "8–14 d", "15+ d", "Unknown"]
            df["age"] = df["days"].map(
                lambda v: "Unknown" if pd.isna(v) else order[0] if v == 0 else order[1]
                if v <= 3 else order[2] if v <= 7 else order[3] if v <= 14 else order[4])
            show_chart(alt.Chart(df).mark_bar(cornerRadiusEnd=4, width=30, color="#818CF8").encode(
                x=alt.X("age:N", sort=order, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("count():Q", title=None, axis=alt.Axis(tickMinStep=1)),
                tooltip=[alt.Tooltip("age:N", title="Posted"),
                         alt.Tooltip("count():Q", title="Openings")]))

        st.markdown("<div class='section-title'>Top picks</div>", unsafe_allow_html=True)
        picks = sort_rows(view, "Best match")[:3]
        for col, r in zip(st.columns(3), picks):
            with col:
                job_card(r, "top")

# ----- Openings -----
with tab_jobs:
    st.session_state.setdefault("view_mode", "Cards")
    st.session_state.setdefault("sort", SORTS[0])
    t1, t2, t3 = st.columns([1.2, 1.4, 1], vertical_alignment="bottom")
    t1.segmented_control("View", ["Cards", "Table"], key="view_mode")
    t2.selectbox("Sort by", SORTS, key="sort")
    ordered = sort_rows(view, st.session_state.sort)
    export = pd.DataFrame([{
        "Company": r["company"], "Role": r["title"], "Job ID": r["job_id"], "Level": r["level"],
        "Experience": r["experience"], "Tech stack": ", ".join(r["tech"]), "Location": r["location"],
        "Posted": r["posted_iso"], "Status": r["status"], "Link": r["url"],
        "Referral message": core.referral_text(r["job"])} for r in ordered])
    t3.download_button("Export CSV", export.to_csv(index=False).encode("utf-8"),
                       file_name="jobwatch_openings.csv", mime="text/csv",
                       icon=":material/download:", width="stretch", disabled=not ordered)

    if not ordered:
        st.info("No openings match these filters.")
    elif st.session_state.view_mode == "Table":
        table = pd.DataFrame([{
            "Status": r["status"], "Company": r["company"], "Role": r["title"], "Level": r["level"],
            "Experience": r["experience"], "Tech": r["tech"], "Score": r["score"],
            "Location": ", ".join(r["cities"]), "Posted": posted_label(r["posted_iso"], r["days"]),
            "Link": r["url"]} for r in ordered])
        st.caption("Tap a row to see the opening's summary below.")
        event = st.dataframe(
            table, hide_index=True, on_select="rerun", selection_mode="single-row", key="jobs_table",
            column_config={
                "Tech": st.column_config.ListColumn("Tech stack", width="medium"),
                "Score": st.column_config.ProgressColumn("Match", min_value=0, max_value=SCORE_CAP,
                                                         format="%d"),
                "Link": st.column_config.LinkColumn("Apply", display_text="open"),
                "Role": st.column_config.TextColumn(width="large"),
            })
        picked = event.selection.rows if event else []
        if picked:
            with st.container(border=True):
                render_summary(ordered[picked[0]], "tbl")
    else:
        pages = max(1, -(-len(ordered) // PAGE_SIZE))
        if st.session_state.get("page") not in range(1, pages + 1):
            st.session_state.page = 1
        start = (st.session_state.page - 1) * PAGE_SIZE
        chunk = ordered[start:start + PAGE_SIZE]
        for i in range(0, len(chunk), 3):
            for col, r in zip(st.columns(3), chunk[i:i + 3]):
                with col:
                    job_card(r, "grid")
        if pages > 1:
            st.pills("Page", list(range(1, pages + 1)), key="page")

# ----- Referral studio -----
with tab_ref:
    if not view:
        st.info("No openings match these filters.")
    else:
        left, right = st.columns([1.6, 1], gap="large")
        with left:
            labels = {r["key"]: f"{r['company']} · {r['title']} ({r['job_id']})" for r in view}
            key = st.selectbox("Opening", list(labels), format_func=labels.get, key="ref_job")
            r = next(x for x in view if x["key"] == key)
            name = st.text_input("Referrer's first name", key=f"ref-studio-{r['hash']}",
                                 value=config.REFERRERS.get(r["company"], ""),
                                 placeholder="blank = generic greeting")
            st.session_state.setdefault("tpl", config.REFERRAL_TEMPLATE)
            tpl = st.text_area("Message template (this session only)", key="tpl", height=110,
                               help="Placeholders: {name} {company} {title} {job_id} {url}. "
                                    "Change the default in config.py.")
            try:
                msg = tpl.format(name=name or config.REFERRERS.get(r["company"]) or "there", **r["job"])
            except (KeyError, IndexError, ValueError) as ex:
                msg = None
                st.error(f"Template problem: {ex}. Use only {{name}} {{company}} {{title}} "
                         "{job_id} {url}, and double any literal braces.")
            if msg:
                st.markdown("<div class='section-title'>Ready to send</div>", unsafe_allow_html=True)
                st.code(msg, language=None, wrap_lines=True)
                n = len(msg)
                st.caption(f"{n} characters" + (" · fits a LinkedIn connection note (300)" if n <= 300
                                                else " · too long for a LinkedIn connection note (300)"))
                a, b = st.columns(2)
                a.link_button("Open posting", r["url"], icon=":material/open_in_new:", width="stretch")
                bulk = "\n\n".join(tpl.format(name=config.REFERRERS.get(x["company"]) or "there", **x["job"])
                                   for x in view)
                b.download_button("All messages (.txt)", bulk.encode("utf-8"),
                                  file_name="jobwatch_referrals.txt", icon=":material/download:",
                                  width="stretch", help="One message per filtered opening.")
        with right:
            st.markdown("<div class='section-title'>Referrers</div>", unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([{"Company": k, "Referrer": v or "—"}
                                       for k, v in config.REFERRERS.items()]),
                         hide_index=True)
            st.caption("Fill names in REFERRERS in config.py to personalise every message.")
            st.info("Nothing is ever sent for you. Copy the message and send it yourself.",
                    icon=":material/verified_user:")

# ----- Sources -----
with tab_src:
    by_company = (data or {}).get("counts", {}).get("by_company")
    matched = pd.Series([r["company"] for r in rows]).value_counts().to_dict() if rows else {}
    failed = {e.split(":", 1)[0] for e in errors}
    src_rows = []
    for name, platform, active in configured_sources():
        if not active:
            status = "Not active"
        elif name in failed:
            status = "Error"
        elif by_company is not None:
            status = "OK"
        else:
            status = "—"
        src_rows.append({"Source": name, "Platform": platform, "Status": status,
                         "Fetched": (by_company or {}).get(name, 0) if active else None,
                         "Matches": matched.get(name, 0) if active else None})
    left, right = st.columns([1.7, 1], gap="large")
    with left:
        st.markdown("<div class='section-title'>Source health</div>", unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(src_rows), hide_index=True, column_config={
            "Fetched": st.column_config.NumberColumn(format="%d"),
            "Matches": st.column_config.NumberColumn(format="%d")})
        if errors:
            st.markdown("<div class='section-title'>Problems in the last scan</div>",
                        unsafe_allow_html=True)
            for e in errors:
                st.error(e, icon=":material/error:")
    with right:
        st.markdown("<div class='section-title'>Automation</div>", unsafe_allow_html=True)
        st.markdown(
            "- Runs at **09:00** and **19:30 IST** on GitHub Actions\n"
            "- New matches go to **Telegram** with the job ID and a referral message\n"
            "- `seen_jobs.json` makes sure no opening is alerted twice")
        st.markdown("<div class='section-title'>Ground rules</div>", unsafe_allow_html=True)
        st.markdown(
            "- Public job APIs only, `robots.txt` checked first\n"
            "- A pause between requests, at most two runs a day\n"
            "- No logins, CAPTCHAs or scraping of LinkedIn / Naukri / Indeed")

# A card's "Summary" button sets open_job; popping it means the dialog opens once
# and does not reappear on the next full rerun after it is closed.
if (k := st.session_state.pop("open_job", None)):
    match = next((r for r in rows if r["key"] == k), None)
    if match:
        job_dialog(match)
