"""Tests for the live Job Bank fetcher -- run with ZERO network.

Every network boundary is injected: `http_get` serves recorded fixtures,
`sleep`/`now` fake the clock. The real transport (`urllib_get`) is never
called here. Fixtures live in tests/fixtures/jobbank/ and mirror markup
verified live on 2026-07-09.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from salesagent.extractors import extract_job_posting
from salesagent.sources.jobbank import (
    HttpResponse,
    JobBankFetcher,
    JobBoardBlocked,
    canonical_posting_url,
    _employer_matches,
    parse_posting,
    parse_search_results,
)

FIX = Path(__file__).parent / "fixtures" / "jobbank"


def _read(name: str) -> str:
    return (FIX / name).read_text()


class FakeHttp:
    """URL-routed fake transport. Records every call it receives."""

    def __init__(self, robots="robots_allow.txt", search="search_testwood.html",
                 status=None, body=None):
        self.calls: list[str] = []
        self.robots = robots
        self.search = search
        self.status = status or {}   # url-substring -> status code
        self.body = body or {}       # url-substring -> body override

    def __call__(self, url: str, user_agent: str) -> HttpResponse:
        self.calls.append(url)
        for sub, code in self.status.items():
            if sub in url:
                return HttpResponse(code, self.body.get(sub, ""), url)
        if "robots.txt" in url:
            return HttpResponse(200, _read(self.robots), url)
        if "/jobsearch/jobsearch" in url:
            return HttpResponse(200, _read(self.search), url)
        if "/jobposting/90000001" in url:
            return HttpResponse(200, _read("posting_90000001.html"), url)
        if "/jobposting/90000002" in url:
            return HttpResponse(200, _read("posting_90000002.html"), url)
        return HttpResponse(404, "", url)


def make(tmp_path, http=None, **kw) -> JobBankFetcher:
    return JobBankFetcher(
        cache_dir=tmp_path,
        http_get=http or FakeHttp(),
        sleep=lambda s: None,
        now=lambda: 0.0,
        **kw,
    )


# -- pure parsers ----------------------------------------------------------
def test_parse_search_results():
    res = parse_search_results(_read("search_testwood.html"))
    assert [r["id"] for r in res] == ["90000001", "90000002"]
    assert res[0]["title"] == "Estimator"
    assert res[0]["employer"] == "Testwood Cabinets Inc."
    assert res[0]["url"] == "https://www.jobbank.gc.ca/jobsearch/jobposting/90000001"
    assert "jsessionid" not in res[0]["url"]


def test_parse_posting_captures_full_body_across_nested_span():
    p = parse_posting(_read("posting_90000001.html"))
    assert p["title"] == "Estimator"
    assert p["employer"] == "Testwood Cabinets Inc."
    # text inside the nested <span> ...
    assert "proficient in Excel and QuickBooks" in p["body"]
    # ... AND text after it -- proves balanced-span extraction, not first-close.
    assert "production/estimating role on the shop floor" in p["body"]


def test_canonical_posting_url():
    assert (
        canonical_posting_url("/jobsearch/jobposting/123;jsessionid=X.y?source=z")
        == "https://www.jobbank.gc.ca/jobsearch/jobposting/123"
    )
    assert canonical_posting_url("/something/else") is None


def test_employer_matching_is_suffix_insensitive():
    assert _employer_matches("Testwood Cabinets", "Testwood Cabinets Inc.")
    assert _employer_matches("tuscan woodworks", "TUSCAN WOODWORKS INC.")
    assert _employer_matches("Testwood", "Testwood Cabinets Inc.")  # token subset
    assert not _employer_matches("Testwood", "Unrelated Millwork Ltd.")


def test_employer_matching_rejects_midword_substring():
    # "aya kitchens" is a *substring* of "maya kitchens" but not a token subset.
    assert not _employer_matches("AyA Kitchens", "Maya Kitchens")
    assert not _employer_matches("Bay", "Baystate Millwork")


# -- fetcher end to end (fixtures, no network) -----------------------------
def test_fetch_returns_extractor_shape_and_filters_by_employer(tmp_path):
    posts = make(tmp_path).fetch_for("Testwood Cabinets")
    assert len(posts) == 1                      # "Unrelated Millwork" dropped
    assert set(posts[0]) == {"title", "body", "url"}
    assert posts[0]["title"] == "Estimator"
    assert "Excel and QuickBooks" in posts[0]["body"]
    assert posts[0]["url"].endswith("/jobposting/90000001")


def test_unfiltered_returns_all_results(tmp_path):
    posts = make(tmp_path, filter_by_employer=False).fetch_for("anything")
    assert len(posts) == 2


def test_fetched_posting_drives_the_real_extractor(tmp_path):
    """The whole point: fetcher output feeds extract_job_posting unchanged."""
    posts = make(tmp_path).fetch_for("Testwood Cabinets")
    evs = extract_job_posting(posts[0]["title"], posts[0]["body"], posts[0]["url"])
    signals = {e.signal for e in evs}
    assert "excel_or_quickbooks_in_production_role" in signals


def test_call_protocol_takes_a_prospect(tmp_path):
    from salesagent import Prospect
    p = Prospect(prospect_id="x", company="Testwood Cabinets")
    posts = make(tmp_path)(p)
    assert posts[0]["title"] == "Estimator"


# -- caching ---------------------------------------------------------------
def test_rerun_is_served_from_disk_cache_with_zero_network(tmp_path):
    http = FakeHttp()
    make(tmp_path, http=http).fetch_for("Testwood Cabinets")
    assert len(http.calls) >= 3                 # robots + search + one detail

    def boom(url, user_agent):
        raise AssertionError(f"warm run hit the network: {url}")

    warm = JobBankFetcher(cache_dir=tmp_path, http_get=boom,
                          sleep=lambda s: None, now=lambda: 0.0)
    posts = warm.fetch_for("Testwood Cabinets")  # robots+search+detail all cached
    assert posts[0]["title"] == "Estimator"


# -- blocking: STOP, never work around -------------------------------------
def test_robots_disallow_raises_blocked(tmp_path):
    http = FakeHttp(robots="robots_disallow.txt")
    with pytest.raises(JobBoardBlocked):
        make(tmp_path, http=http).fetch_for("Testwood Cabinets")


def test_http_403_raises_blocked(tmp_path):
    http = FakeHttp(status={"/jobsearch/jobsearch": 403})
    with pytest.raises(JobBoardBlocked):
        make(tmp_path, http=http).fetch_for("Testwood Cabinets")


def test_http_429_raises_blocked(tmp_path):
    http = FakeHttp(status={"/jobsearch/jobsearch": 429})
    with pytest.raises(JobBoardBlocked):
        make(tmp_path, http=http).fetch_for("Testwood Cabinets")


def test_challenge_page_raises_blocked(tmp_path):
    http = FakeHttp(
        status={"/jobsearch/jobsearch": 200},
        body={"/jobsearch/jobsearch": "<html>Please complete the CAPTCHA to continue.</html>"},
    )
    with pytest.raises(JobBoardBlocked):
        make(tmp_path, http=http).fetch_for("Testwood Cabinets")


# -- resilience: one bad posting must not sink the batch -------------------
def test_expired_posting_is_skipped_not_fatal(tmp_path):
    # 90000002's detail page 404s (posting expired); 90000001 is fine.
    http = FakeHttp(status={"/jobposting/90000002": 404})
    posts = make(tmp_path, http=http, filter_by_employer=False).fetch_for("anything")
    assert [p["title"] for p in posts] == ["Estimator"]   # the 404 one dropped, no raise


def test_transient_search_failure_returns_empty_not_raise(tmp_path):
    http = FakeHttp(status={"/jobsearch/jobsearch": 404})
    assert make(tmp_path, http=http).fetch_for("Testwood Cabinets") == []


def test_benign_block_phrase_in_posting_is_not_a_block(tmp_path):
    # A real posting body mentioning "access denied" must NOT trip the guard.
    body = ('<span property="title">Estimator</span>'
            '<span property="hiringOrganization"><span property="name">'
            'Testwood Cabinets Inc.</span></span>'
            '<span property="description">Review access denied logs and request '
            'blocked events on the shop network.</span>')
    http = FakeHttp(status={"/jobposting/90000001": 200},
                    body={"/jobposting/90000001": body})
    posts = make(tmp_path, http=http).fetch_for("Testwood Cabinets")
    assert posts[0]["title"] == "Estimator"
    assert "access denied" in posts[0]["body"]


# -- politeness: honours the crawl-delay -----------------------------------
def test_respects_crawl_delay_between_requests(tmp_path):
    clock = [0.0]
    slept: list[float] = []

    def now():
        return clock[0]

    def sleep(s):
        slept.append(s)
        clock[0] += s

    http = FakeHttp()
    f = JobBankFetcher(cache_dir=tmp_path, http_get=http, sleep=sleep, now=now,
                       min_interval_s=5.0)
    f.fetch_for("Testwood Cabinets")
    # search->detail gap must be spaced to >= the 5s Crawl-delay from robots.txt
    assert any(s >= 5.0 for s in slept)
