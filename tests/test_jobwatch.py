"""Offline tests: no network. Run with `python -m unittest discover -s tests -v`."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import core  # noqa: E402
import fetchers  # noqa: E402
import gmail_reader  # noqa: E402
import main  # noqa: E402


def job(**kw):
    base = {"company": "PTC", "title": "Data Science Intern", "job_id": "JR1",
            "location": "Pune, Maharashtra, India", "posted": "Posted Today",
            "url": "https://example.com/j/1", "source": "test"}
    base.update(kw)
    return base


REAL_CHECK = fetchers.check_robots


class RelevanceTests(unittest.TestCase):
    def test_fresher_pune_role_is_relevant(self):
        self.assertTrue(core.relevant(job()))

    def test_senior_role_rejected(self):
        self.assertFalse(core.relevant(job(title="Senior Data Scientist")))

    def test_unrelated_title_rejected(self):
        self.assertFalse(core.relevant(job(title="Sales Executive")))

    def test_wrong_location_rejected(self):
        self.assertFalse(core.relevant(job(location="Austin, Texas")))

    def test_multi_location_kept(self):
        self.assertTrue(core.relevant(job(location="2 Locations")))

    def test_indiana_is_not_india(self):
        self.assertFalse(core.relevant(job(location="Hobart, Indiana, USA")))

    def test_resolved_locations_checked(self):
        self.assertFalse(core.relevant(job(location="Melbourne - 727 Collins; Sydney (Australia)")))
        self.assertTrue(core.relevant(job(location="Bengaluru - Bellandur; Pune - Hinjewadi (India)")))

    def test_posted_30_plus_days_rejected(self):
        self.assertFalse(core.relevant(job(posted="Posted 30+ Days Ago")))

    def test_fresher_ranking(self):
        self.assertEqual(core.fresher_rank("ML Intern"), 2)
        self.assertEqual(core.fresher_rank("Junior Data Analyst"), 1)
        self.assertEqual(core.fresher_rank("Data Analyst"), 0)

    def test_rank_puts_fresher_first_then_skill(self):
        a = job(job_id="a", title="Data Analyst")
        b = job(job_id="b", title="Python ML Intern")
        c = job(job_id="c", title="Data Science Intern")
        ordered = [j["job_id"] for j in core.rank([a, b, c])]
        self.assertEqual(ordered[0], "b")  # intern + python + ML
        self.assertEqual(ordered[-1], "a")  # no fresher signal


class WorkdayParsingTests(unittest.TestCase):
    def test_parse_with_locale(self):
        self.assertEqual(
            fetchers.parse_workday_url("https://csgi.wd5.myworkdayjobs.com/en-US/CSGCareers"),
            ("csgi.wd5.myworkdayjobs.com", "csgi", "CSGCareers", "en-US"))

    def test_parse_without_locale_defaults(self):
        self.assertEqual(
            fetchers.parse_workday_url("https://ptc.wd1.myworkdayjobs.com/PTC"),
            ("ptc.wd1.myworkdayjobs.com", "ptc", "PTC", "en-US"))

    def test_parse_keeps_non_default_locale(self):
        self.assertEqual(
            fetchers.parse_workday_url("https://x.wd1.myworkdayjobs.com/fr-FR/Site")[3], "fr-FR")

    def test_rejects_non_workday(self):
        with self.assertRaises(ValueError):
            fetchers.parse_workday_url("https://example.com/careers")

    def test_job_id_prefers_requisition_in_path(self):
        p = {"externalPath": "/job/Pune/Data-Intern_JR0609524-1", "bulletFields": ["Other"]}
        self.assertEqual(fetchers.workday_job_id(p), "JR0609524-1")


class FakeResponse:
    def __init__(self, payload=None, status=200, text=""):
        self._payload, self.status_code, self.text = payload, status, text
        self.ok = status < 400

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FetcherTests(unittest.TestCase):
    def setUp(self):
        fetchers._robots.clear()
        patcher = mock.patch.object(fetchers, "PAUSE", 0)
        patcher.start()
        self.addCleanup(patcher.stop)
        robots = mock.patch.object(fetchers, "check_robots", return_value=None)
        robots.start()
        self.addCleanup(robots.stop)

    def test_robots_disallow_blocks_request(self):
        robots = "User-agent: *\nDisallow: /wday/\n"
        with mock.patch.object(fetchers.requests, "get",
                               return_value=FakeResponse(status=200, text=robots)):
            with self.assertRaises(fetchers.FetchError):
                REAL_CHECK("https://x.wd1.myworkdayjobs.com/wday/cxs/x/y/jobs")

    def test_missing_robots_is_allowed(self):
        with mock.patch.object(fetchers.requests, "get", return_value=FakeResponse(status=404)):
            REAL_CHECK("https://example.com/anything")

    def test_robots_unreachable_is_an_error(self):
        with mock.patch.object(fetchers.requests, "get", return_value=FakeResponse(status=503)):
            with self.assertRaises(fetchers.FetchError):
                REAL_CHECK("https://example.com/x")

    def test_workday_fetch_builds_job_urls(self):
        page = {"jobPostings": [{"title": "Data Analyst Intern", "locationsText": "Pune",
                                 "postedOn": "Posted Today",
                                 "externalPath": "/job/Pune/Data-Analyst-Intern_R-42"}]}

        def fake_request(method, url, **kw):
            if url.endswith("/robots.txt"):
                return FakeResponse(status=404)
            return FakeResponse(payload=page)

        with mock.patch.object(fetchers.requests, "request", side_effect=fake_request):
            jobs = fetchers.fetch_workday("PTC", "https://ptc.wd1.myworkdayjobs.com/PTC", ["data"])
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["job_id"], "R-42")
        self.assertEqual(jobs[0]["url"],
                         "https://ptc.wd1.myworkdayjobs.com/en-US/PTC/job/Pune/Data-Analyst-Intern_R-42")

    def test_greenhouse_parsing(self):
        payload = {"jobs": [{"id": 9, "title": "ML Intern", "location": {"name": "Pune"},
                             "updated_at": "2026-10-01T10:00:00Z",
                             "absolute_url": "https://boards.greenhouse.io/x/jobs/9"}]}

        def fake_request(method, url, **kw):
            if url.endswith("/robots.txt"):
                return FakeResponse(status=404)
            return FakeResponse(payload=payload)

        with mock.patch.object(fetchers.requests, "request", side_effect=fake_request):
            jobs = fetchers.fetch_greenhouse("X", "x")
        self.assertEqual(jobs[0]["job_id"], "9")
        self.assertEqual(jobs[0]["location"], "Pune")
        self.assertEqual(jobs[0]["posted"], "2026-10-01")
        self.assertEqual(jobs[0]["source"], "greenhouse")

    def test_lever_parsing(self):
        payload = [{"id": "abc", "text": "Data Intern", "categories": {"location": "Pune"},
                    "createdAt": 1767225600000, "hostedUrl": "https://jobs.lever.co/x/abc"}]

        def fake_request(method, url, **kw):
            if url.endswith("/robots.txt"):
                return FakeResponse(status=404)
            return FakeResponse(payload=payload)

        with mock.patch.object(fetchers.requests, "request", side_effect=fake_request):
            jobs = fetchers.fetch_lever("X", "x")
        self.assertEqual(jobs[0]["job_id"], "abc")
        self.assertEqual(jobs[0]["posted"], "2026-01-01")

    def test_workday_locations_reads_detail(self):
        detail = {"jobPostingInfo": {"location": "Bengaluru - Bellandur",
                                     "additionalLocations": ["Pune - Hinjewadi"],
                                     "country": {"descriptor": "India"}}}
        urls = []

        def fake_request(method, url, **kw):
            urls.append(url)
            return FakeResponse(payload=detail)

        with mock.patch.object(fetchers.requests, "request", side_effect=fake_request):
            loc = fetchers.workday_locations(
                "https://synechron.wd1.myworkdayjobs.com/en-US/SynechronCareers/job/Bengaluru/AI-Engineer_JR1")
        self.assertEqual(urls, ["https://synechron.wd1.myworkdayjobs.com/wday/cxs/synechron/"
                                "SynechronCareers/job/Bengaluru/AI-Engineer_JR1"])
        self.assertEqual(loc, "Bengaluru - Bellandur; Pune - Hinjewadi (India)")


class LocationResolveTests(unittest.TestCase):
    def test_only_matching_multi_location_workday_jobs_looked_up(self):
        jobs = [job(location="3 Locations", source="workday"),
                job(job_id="JR2", title="Sales Executive", location="3 Locations", source="workday"),
                job(job_id="JR3", location="Pune", source="workday")]
        with mock.patch.object(main, "workday_locations", return_value="Berlin (Germany)") as look:
            main.resolve_locations(jobs)
        look.assert_called_once_with(jobs[0]["url"])
        self.assertEqual([j["location"] for j in jobs], ["Berlin (Germany)", "3 Locations", "Pune"])

    def test_failed_lookup_keeps_job(self):
        jobs = [job(location="3 Locations", source="workday")]
        with mock.patch.object(main, "workday_locations",
                               side_effect=fetchers.FetchError("robots")):
            main.resolve_locations(jobs)
        self.assertEqual(jobs[0]["location"], "3 Locations")
        self.assertTrue(core.relevant(jobs[0]))


class GmailExtractionTests(unittest.TestCase):
    def test_extracts_linkedin_indeed_naukri(self):
        html = """
        <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trk=x">Data Science Intern</a>
        <a href="https://in.indeed.com/viewjob?jk=abc123def&amp;from=alert">ML Fresher</a>
        <a href="https://www.naukri.com/job-listings-data-analyst-acme-pune-0-to-1-years-123456789012?src=x">Data Analyst</a>
        <a href="https://example.com/unrelated">Ignore me</a>
        """
        found = gmail_reader.extract_jobs(html)
        by_source = {j["source"]: j for j in found}
        self.assertEqual(by_source["linkedin"]["job_id"], "4012345678")
        self.assertEqual(by_source["linkedin"]["title"], "Data Science Intern")
        self.assertEqual(by_source["indeed"]["job_id"], "abc123def")
        self.assertEqual(by_source["naukri"]["job_id"], "123456789012")
        self.assertEqual(len(found), 3)

    def test_duplicate_links_collapsed(self):
        html = ('<a href="https://www.linkedin.com/jobs/view/111/">A</a>'
                '<a href="https://www.linkedin.com/jobs/view/111/">A again</a>')
        self.assertEqual(len(gmail_reader.extract_jobs(html)), 1)


class NotifyStateTests(unittest.TestCase):
    """A Telegram failure must not mark jobs as seen, so they are retried next run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        patches = [mock.patch.object(core, "SEEN_FILE", base / "seen.json"),
                   mock.patch.object(core, "LAST_RUN_FILE", base / "last.json")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.env = mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_main(self, telegram_ok):
        jobs = [job()]
        with mock.patch.object(main, "collect", return_value=(jobs, [])), \
             mock.patch.object(main, "send_telegram", return_value=telegram_ok), \
             mock.patch.object(sys, "argv", ["main.py"]):
            main.main()

    def test_seen_saved_after_successful_send(self):
        self.run_main(telegram_ok=True)
        self.assertIn("PTC|JR1", json.loads((Path(self.tmp.name) / "seen.json").read_text()))

    def test_seen_not_saved_when_telegram_fails(self):
        self.run_main(telegram_ok=False)
        self.assertFalse((Path(self.tmp.name) / "seen.json").exists())

    def test_failed_source_does_not_stop_others(self):
        def boom(*a, **k):
            raise fetchers.FetchError("blocked")
        with mock.patch.object(main, "fetch_workday", side_effect=boom), \
             mock.patch.object(main, "fetch_amazon", return_value=[job(company="Amazon")]), \
             mock.patch.object(main.config, "WORKDAY_SITES",
                               [{"company": "PTC", "url": "https://ptc.wd1.myworkdayjobs.com/PTC"}]), \
             mock.patch.object(main.config, "ENABLE_AMAZON", True):
            jobs, errors = main.collect()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(len(errors), 1)


class ReferralTextTests(unittest.TestCase):
    def test_referral_uses_company_and_job_fields(self):
        text = core.referral_text(job(), referrer="Asha")
        self.assertIn("Hi Asha", text)
        self.assertIn("Job ID: JR1", text)
        self.assertIn("https://example.com/j/1", text)


if __name__ == "__main__":
    unittest.main()
