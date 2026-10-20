"""jobwatch — find new relevant openings and send them to Telegram.

Usage:
    python main.py            # fetch, alert, remember what was sent
    python main.py --dry-run  # fetch and print only; nothing is saved or sent
"""
import html
import os
import sys

import requests

import config
import core
from fetchers import (FetchError, fetch_amazon, fetch_greenhouse, fetch_lever,
                      fetch_workday)


def send_telegram(text):
    """Return True if the message was delivered (or printed because Telegram is not set up)."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[telegram not configured — printing instead]\n" + text)
        return True
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
    except requests.RequestException as ex:
        print("Telegram request failed:", ex)
        return False
    if not r.ok:
        print("Telegram error:", r.text)
        return False
    return True


def format_job(job):
    e = html.escape
    referral = core.referral_text(job)
    return (f"<b>{e(job['company'])}</b> — {e(job['title'])}\n"
            f"ID: <code>{e(job['job_id'])}</code> | {e(job['location'])} | {e(job['posted'])}\n"
            f"{e(job['url'])}\n"
            f"Referral msg (tap to copy):\n<code>{e(referral)}</code>")


def notify(new_jobs, errors):
    """Send alerts. Returns True only if every message was delivered."""
    blocks = [format_job(j) for j in new_jobs]
    if errors:
        blocks.append("⚠️ Fetcher problems:\n" + html.escape("\n".join(errors)))
    if not blocks:
        return send_telegram("No new matching openings this run.")
    ok = True
    msg = f"🔔 {len(new_jobs)} new matching opening(s)\n\n"
    for b in blocks:  # Telegram limit is 4096 chars per message
        if len(msg) + len(b) > 3800 and msg.strip():
            ok = send_telegram(msg) and ok
            msg = ""
        msg += b + "\n\n"
    if msg.strip():
        ok = send_telegram(msg) and ok
    return ok


def collect():
    """Run every enabled source. Returns (jobs, errors); one failing source never stops the rest."""
    jobs, errors = [], []

    def run(name, fn, *args):
        try:
            found = fn(*args)
            print(f"{name}: {len(found)} postings fetched")
            jobs.extend(found)
        except (FetchError, requests.RequestException, ValueError, KeyError) as ex:
            errors.append(f"{name}: {ex}")
            print(f"ERROR {name}: {ex}")

    for site in config.WORKDAY_SITES:
        if site["url"].startswith("http"):
            run(site["company"], fetch_workday, site["company"], site["url"], config.SEARCH_TERMS)
    for b in config.GREENHOUSE_BOARDS:
        run(b["company"], fetch_greenhouse, b["company"], b["token"])
    for s in config.LEVER_SITES:
        run(s["company"], fetch_lever, s["company"], s["site"])
    if config.ENABLE_AMAZON:
        run("Amazon", fetch_amazon, config.SEARCH_TERMS)
    if config.ENABLE_GMAIL:
        from gmail_reader import fetch_alert_jobs
        run("Gmail alerts", fetch_alert_jobs)
    return jobs, errors


def main():
    dry_run = "--dry-run" in sys.argv
    seen = core.load_seen()

    all_jobs, errors = collect()
    matches = core.rank([j for j in all_jobs if core.relevant(j)])
    new_jobs = [j for j in matches if core.key(j) not in seen]
    print(f"{len(all_jobs)} fetched, {len(matches)} relevant, {len(new_jobs)} new, {len(errors)} errors")

    if dry_run:
        for j in new_jobs:
            print(f"- [{j['company']}] {j['title']} | {j['job_id']} | {j['location']} | {j['url']}")
        return

    # Save what the UI shows, whether or not anything is sent.
    core.save_last_run(matches, errors, {"fetched": len(all_jobs), "relevant": len(matches),
                                         "new": len(new_jobs)})
    # Only remember jobs once the alert was delivered, so a Telegram failure
    # means the same jobs are retried on the next run.
    if notify(new_jobs, errors):
        core.save_seen(seen | {core.key(j) for j in matches})
    else:
        print("Telegram delivery failed; seen list left unchanged.")


if __name__ == "__main__":
    main()
