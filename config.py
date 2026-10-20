# ---------------------------------------------------------------
# jobwatch config — edit this file, not the code.
# ---------------------------------------------------------------

# Workday career sites. Copy the URL up to the site name, e.g.
#   https://example.wd5.myworkdayjobs.com/en-US/ExampleCareers
# "PASTE_URL" (or any non-http value) = skipped.
# NOTE: Marsh McLennan's public careers site runs on Phenom
# (careers.marsh.com), not Workday. Verify this URL on your first run.
WORKDAY_SITES = [
    {"company": "PTC",               "url": "https://ptc.wd1.myworkdayjobs.com/PTC"},
    {"company": "CSG International", "url": "https://csgi.wd5.myworkdayjobs.com/CSGCareers"},
    {"company": "Marsh McLennan",    "url": "https://mmc.wd1.myworkdayjobs.com/MMC"},
    {"company": "Synechron",         "url": "https://synechron.wd1.myworkdayjobs.com/SynechronCareers"},
    # Not Workday: Global Payments, FIS, John Deere, BMC Software need custom
    # fetchers (not built). Leave as PASTE_URL.
    {"company": "Global Payments",   "url": "PASTE_URL"},
    {"company": "FIS",               "url": "PASTE_URL"},
    {"company": "John Deere",        "url": "PASTE_URL"},
    {"company": "BMC Software",      "url": "PASTE_URL"},
]

# Greenhouse / Lever public job boards (Phase 3). Add a company only if you
# have confirmed its board token, e.g. boards.greenhouse.io/<token>.
GREENHOUSE_BOARDS = [
    # {"company": "Example Co", "token": "exampleco"},
]
LEVER_SITES = [
    # {"company": "Example Co", "site": "exampleco"},   # jobs.lever.co/<site>
]

ENABLE_AMAZON = True

# Read job-alert emails from the Gmail label below (Phase 3, needs OAuth setup).
ENABLE_GMAIL = False
GMAIL_LABEL = "Job Alerts"
GMAIL_LOOKBACK_DAYS = 3

# Words typed into each site's search box (one request batch per term)
SEARCH_TERMS = ["data", "machine learning", "AI", "analyst"]

# Title MUST match this (case-insensitive)
ROLE_PATTERN = (r"\b(data|machine learning|ml|ai|artificial intelligence|analyst|"
                r"analytics|gen ?ai|llm|nlp|deep learning|computer vision)\b")

# Title must NOT match this
EXCLUDE_PATTERN = (r"\b(senior|sr|lead|principal|staff|manager|director|head|"
                   r"architect|vp|ii|iii|iv)\b")

# Ranked to the top of the alert
FRESHER_STRONG = r"\b(intern|internship|fresher|trainee|apprentice)\b"
FRESHER_WEAK = r"\b(graduate|associate|junior|jr|entry)\b"

# Resume match score: regex -> weight. Matched against the job title.
# Only titles are available from the job lists, so keep these terms broad.
SKILL_WEIGHTS = {
    r"\bpython\b": 2,
    r"\bmachine learning\b|\bml\b": 2,
    r"\bdeep learning\b|\bnlp\b|\bllm\b|gen ?ai": 2,
    r"\bdata scien": 2,
    r"\bdata analy": 1,
    r"\bai\b|artificial intelligence": 1,
    r"\bcomputer vision\b": 1,
    r"\banalytics\b": 1,
}

# Location must contain one of these (Workday "2 Locations" style is kept)
LOCATION_KEYWORDS = ["pune", "maharashtra", "india", "remote", "hybrid"]

# Who refers you at each company. Fill names; blank = generic greeting.
REFERRERS = {
    "Global Payments": "",
    "PTC": "",
    "FIS": "",
    "John Deere": "",      # already in a referral process — monitor only
    "Marsh McLennan": "",
    "Synechron": "",
    "BMC Software": "",
    "CSG International": "",
    "Amazon": "",
}

REFERRAL_TEMPLATE = (
    "Hi {name}, there's an opening at {company}: {title} (Job ID: {job_id}). "
    "Link: {url} . It matches my Python / SQL / ML profile. "
    "Could you please refer me for it? Thank you!"
)
