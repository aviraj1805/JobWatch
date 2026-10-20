"""jobwatch dashboard (Streamlit).

Run:  streamlit run app.py

The page reads last_run.json (written by "Refresh now" here, or by main.py).
Refreshing here only fetches and lists jobs: it does NOT send Telegram alerts
and does NOT change seen_jobs.json, so the twice-daily alerts stay correct.
"""
import json

import pandas as pd
import streamlit as st

import config
import core
import main

SAMPLE_FILE = core.BASE / "sample_last_run.json"

st.set_page_config(page_title="jobwatch", page_icon="🔔", layout="wide")


def load_data():
    data = core.load_last_run()
    if data is None and SAMPLE_FILE.exists():
        return json.loads(SAMPLE_FILE.read_text()), True
    return data, False


def refresh():
    with st.spinner("Fetching sources. This takes a minute or two (polite rate limits)..."):
        jobs, errors = main.collect()
        matches = core.rank([j for j in jobs if core.relevant(j)])
        counts = {"fetched": len(jobs), "relevant": len(matches),
                  "new": sum(core.key(j) not in core.load_seen() for j in matches)}
        return core.save_last_run(matches, errors, counts)


data, is_sample = load_data()
seen = core.load_seen()

with st.sidebar:
    st.header("Fetch")
    if st.button("Refresh now", type="primary", use_container_width=True):
        data = refresh()
        is_sample = False
        st.success("Fetched. Alerts are still sent only by main.py / GitHub Actions.")
    if data:
        st.caption(f"Last fetch: {data.get('ran_at') or 'unknown'}")
    st.divider()
    st.header("Filters")
    fresher_only = st.checkbox("Fresher-friendly only (intern / trainee / entry)")
    min_score = st.slider("Minimum skill score", 0, 6, 0)
    text = st.text_input("Search title or company")
    jobs = data["jobs"] if data else []
    companies = sorted({j["company"] for j in jobs})
    chosen = st.multiselect("Companies", companies)

st.title("🔔 jobwatch")

if is_sample:
    st.warning("Showing SAMPLE data (fictional companies) so you can see the layout. "
               "Click Refresh now to fetch real postings.")

if data:
    c = data.get("counts", {})
    a, b, d, e = st.columns(4)
    a.metric("Fetched", c.get("fetched", 0))
    b.metric("Relevant", c.get("relevant", len(jobs)))
    d.metric("New since last alert", c.get("new", 0))
    e.metric("Source errors", len(data.get("errors", [])))

if not jobs:
    st.info("No matches yet. Click Refresh now in the sidebar.")
    st.stop()

filtered = []
needle = text.lower().strip()
for j in jobs:
    fr = core.fresher_rank(j["title"])
    sc = core.skill_score(j)
    if fresher_only and fr == 0:
        continue
    if sc < min_score:
        continue
    if chosen and j["company"] not in chosen:
        continue
    if needle and needle not in f"{j['title']} {j['company']}".lower():
        continue
    filtered.append((j, fr, sc))

st.subheader(f"Matches ({len(filtered)})")
rows = [{
    "Status": "new" if core.key(j) not in seen else "alerted",
    "Company": j["company"],
    "Role": j["title"],
    "Level": {2: "fresher", 1: "entry", 0: "other"}[fr],
    "Score": sc,
    "Location": j.get("location", ""),
    "Posted": j.get("posted", ""),
    "Job ID": j["job_id"],
    "Link": j["url"],
} for j, fr, sc in filtered]

if rows:
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={"Link": st.column_config.LinkColumn("Apply link", display_text="open")},
    )
else:
    st.info("Nothing matches these filters.")

st.subheader("Referral message")
if filtered:
    labels = [f"{j['company']} — {j['title']} ({j['job_id']})" for j, _, _ in filtered]
    idx = st.selectbox("Pick a job", range(len(labels)), format_func=lambda i: labels[i])
    job = filtered[idx][0]
    referrer = st.text_input("Referrer's first name (blank = generic)",
                             value=config.REFERRERS.get(job["company"], ""),
                             key=f"ref-{core.key(job)}")
    st.code(core.referral_text(job, referrer or None), language=None)
    st.caption("Use the copy button on the box above. Edit the template in config.py.")

if data and data.get("errors"):
    with st.expander(f"Source problems ({len(data['errors'])})"):
        for err in data["errors"]:
            st.write("• " + err)
