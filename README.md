# jobwatch

A personal job watcher for fresher / entry-level data and AI roles in Pune.
It checks company career sites and job APIs twice a day, sends new matches
to Telegram with the job ID and a ready-to-paste referral message, and has a
Streamlit dashboard to browse matches.

Scope and rules the tool follows:

- Only public JSON endpoints that career sites publish, plus your own Gmail
  job-alert emails (read-only). It never logs in to, or scrapes, LinkedIn,
  Naukri or Indeed directly.
- Every site's `robots.txt` is checked first. If it disallows the path, or
  can't be read, that source is skipped for the run and the problem is reported.
- No CAPTCHA solving, no browser automation against job portals, no login
  or form submission on any site.
- At most two scheduled runs per day, with pauses between requests.
- Nothing is sent to a referrer automatically. You copy the message yourself.

## Project layout

| File | Purpose |
| --- | --- |
| `config.py` | Companies, search terms, role/location/fresher rules, skill weights, referrer names, referral template |
| `fetchers.py` | Workday, Greenhouse, Lever and Amazon fetchers, plus the robots.txt check |
| `gmail_reader.py` | Optional. Reads job-alert emails (LinkedIn, Indeed, Naukri) from a Gmail label |
| `core.py` | Shared filtering, ranking, state files and referral text |
| `details.py` | Builds each opening's summary (tech stack, experience, role type, posted date) from its description |
| `main.py` | CLI: fetch, filter, send Telegram alerts, update `seen_jobs.json` |
| `app.py` | Streamlit dashboard |
| `tests/test_jobwatch.py` | Offline tests (no network) |
| `.github/workflows/jobwatch.yml` | Runs `main.py` twice a day on GitHub Actions and commits the state files |
| `sample_last_run.json` | Fictional data so the dashboard can be seen before a real run |

## 1. Install

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Test and dry-run

```bash
python -m unittest discover -s tests -v
python main.py --dry-run             # fetch and print, nothing saved or sent
```

`--dry-run` prints each source's count and every new match. Errors appear as
`ERROR <company>: ...`. Common ones:

- `robots.txt disallows ...`: that source is not allowed by its site. Remove it from `config.py`.
- `HTTP 403` or `HTTP 404` on a Workday site: check the URL in `WORKDAY_SITES`. Copy it from a real job page on the careers site.

## 3. Telegram alerts (one-time setup)

1. In Telegram, message **@BotFather**, send `/newbot`, and copy the token.
2. Send any message to your new bot.
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
4. Export the values, then run:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="123456789"
python main.py
```

If the variables are missing, alerts print to the console instead. A message
that fails to send is not recorded as seen, so it is retried on the next run.

## 4. Dashboard

```bash
streamlit run app.py
```

- **Overview**: headline numbers and charts for matches by company, seniority,
  most requested tech, experience asked, cities and posting age, plus the top picks.
- **Openings**: cards or a table. Tap **Summary** on a card, or tap a table row,
  to see the opening's job role, experience asked, posted date, location, tech
  stack, a description excerpt, the job ID and a ready referral message.
  **Export CSV** saves the filtered list.
- **Referral studio**: pick an opening, type the referrer's name, adjust the
  template for this session, and copy the message (with a LinkedIn 300-character check).
  You can also download every filtered opening's message as one text file.
- **Sources**: fetched and matched counts per source, errors from the last scan.
- Sidebar filters: search, level, new/alerted, max experience asked, posting age,
  company, tech stack, city, minimum title skill score.
- **Refresh now** fetches the sources with live progress. It does not send
  alerts or change `seen_jobs.json`.
- Until the first real fetch, the page shows fictional sample data, labelled as such.

The theme is in `.streamlit/config.toml`.

### Where the summary comes from

The tech stack and experience are read from each posting's description with
the patterns in `TECH_KEYWORDS` (config.py) and a "N years of experience"
rule. Experience shows the lowest requirement found; if the description
states none, the title decides ("Fresher / intern", "Entry level" or "Not
stated"). Workday descriptions come from the same detail request used for
locations; Amazon, Greenhouse and Lever include them in their job lists.
Email-sourced jobs have no description.

## 5. Scheduled runs on GitHub (Phase 2)

1. Push this folder to a **private** GitHub repository.
2. Repository → Settings → Secrets and variables → Actions → add
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
3. Actions → jobwatch → Run workflow, to test it once.

The workflow runs at 09:00 and 19:30 IST. After each run it commits
`seen_jobs.json` and `last_run.json`, so the same job is never alerted twice.
GitHub's schedule can run a few minutes late. If you see no runs for a
while, check the Actions tab; GitHub can pause scheduled workflows in
repositories that have had no activity for a long time.

## 6. Gmail job-alert reader (Phase 3, optional)

This reads the job-alert emails you already get, using the `Job Alerts` label
and filter you set up.

1. In Google Cloud Console, create a project, enable the **Gmail API**, and
   configure the OAuth consent screen (External, and add your own account as a test user).
2. Create an OAuth client ID of type **Desktop app**. Download it as `credentials.json` in this folder.
3. `pip install -r requirements-gmail.txt`
4. `python gmail_reader.py`. A browser opens. Approve read-only access. This writes `token.json`.
5. In `config.py`, set `ENABLE_GMAIL = True`.

`credentials.json` and `token.json` are git-ignored. Do not commit them.

## Matching rules

- **Role**: the title must match `ROLE_PATTERN` and must not match `EXCLUDE_PATTERN`
  (senior, lead, manager, II/III...).
- **Location**: must mention Pune, Maharashtra, India, remote or hybrid as a
  whole word ("Indiana" does not count). For a Workday "N Locations" posting
  whose title already matches, one extra request reads the real location list
  and country, and that is checked instead. If that lookup fails, the posting
  is kept. Email-sourced jobs have no location and are kept.
- **Age**: Workday's "Posted 30+ Days Ago" is dropped.
- **Ranking**: intern/trainee/fresher first, then entry-level, then by skill score.
  The skill score uses `SKILL_WEIGHTS` and is matched against the title only,
  because the job lists don't include descriptions.
- **Job ID**: for Workday it is the requisition ID at the end of the job path. For
  others it is the source's own ID.

## Known limits

- Scoring is title-based. Reading full descriptions would cost one extra request
  per job and is not built in.
- The Workday URL for Marsh McLennan has not been verified. Their public careers
  site runs on another platform.
- Global Payments, FIS, John Deere and BMC use custom sites and have no fetcher yet.
- Single-location Workday postings in other Indian cities (e.g. "Bengaluru -
  Bellandur") are dropped, because the list text does not say "India". Add
  city names to `LOCATION_KEYWORDS` if you want them.
