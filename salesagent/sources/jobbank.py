"""Live Job Bank Canada fetcher -- the first real source behind JobBoardAdapter.

Job Bank (https://www.jobbank.gc.ca) is the Government of Canada's public job
board. Its robots.txt allows automated access (``User-agent: *``,
``Crawl-delay: 5``, no ``Disallow``). This fetcher honours that, in code:

  * a descriptive, honest User-Agent (no browser spoofing);
  * a robots.txt check on every URL via urllib.robotparser;
  * request spacing >= the advertised Crawl-delay (5s);
  * an on-disk response cache, so re-runs cost zero network.

It is a drop-in ``fetch`` callable for JobBoardAdapter -- the adapter and the
extractor are untouched::

    from salesagent.sources import JobBoardAdapter
    from salesagent.sources.jobbank import JobBankFetcher

    adapter = JobBoardAdapter(fetch=JobBankFetcher(province="Ontario"))

Called with a Prospect, it returns ``list[dict(title, body, url)]`` -- exactly
the shape ``extractors.extract_job_posting`` consumes.

If the board blocks automated access -- robots disallow, HTTP 401/403/429, or
a challenge/captcha page -- it raises :class:`JobBoardBlocked` and STOPS. It
never spoofs a browser, never uses an unofficial API, never works around a
block. That decision belongs to a human.
"""

from __future__ import annotations

import html as _html
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Callable
from urllib.robotparser import RobotFileParser

BASE = "https://www.jobbank.gc.ca"
ROBOTS_URL = f"{BASE}/robots.txt"
SEARCH_PATH = "/jobsearch/jobsearch"

DEFAULT_UA = (
    "salesagent/1.0 (+https://odooiq.example; Ontario cabinetry prospecting "
    "research; respects robots.txt; contact: dangelo.john@gmail.com)"
)


class JobBoardError(Exception):
    """Base class for Job Bank fetch problems."""


class JobBoardBlocked(JobBoardError):
    """Automated access is blocked (robots disallow / 401 / 403 / 429 / challenge).

    Raised so a human decides what to do. We do NOT work around it.
    """


class JobBoardUnavailable(JobBoardError):
    """Transient failure (network down, 5xx). Not a deliberate block."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    body: str
    url: str


# --------------------------------------------------------------------------
# Default transport (real network). Injectable for tests.
# --------------------------------------------------------------------------
def urllib_get(url: str, user_agent: str, timeout: float = 30.0) -> HttpResponse:
    """The only place that touches the network. Tests inject a fake instead."""
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            return HttpResponse(getattr(r, "status", 200), body, r.geturl())
    except urllib.error.HTTPError as e:  # 4xx/5xx still carry a status
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return HttpResponse(e.code, body, url)
    except urllib.error.URLError as e:  # DNS/connection failure -- not a block
        raise JobBoardUnavailable(f"could not reach {url}: {e.reason}") from e


# --------------------------------------------------------------------------
# HTML parsing -- pure functions, no network, unit-testable in isolation.
# --------------------------------------------------------------------------
_POSTING_ID_RE = re.compile(r"/jobsearch/jobposting/(\d+)")
_ARTICLE_RE = re.compile(r'<article[^>]*id="article-(\d+)".*?</article>', re.S)
_TITLE_RE = re.compile(r'property="title"[^>]*>(.*?)</span>', re.S)  # posting detail page
_NOCTITLE_RE = re.compile(r'class="noctitle"[^>]*>(.*?)</span>', re.S)  # search results
_BUSINESS_RE = re.compile(r'class="business"[^>]*>\s*([^<]+)', re.S)
_HIRING_ORG_RE = re.compile(
    r'property="hiringOrganization".*?property="name"[^>]*>(.*?)</span>', re.S
)
# Narrow, anti-bot-specific markers. Deliberately NOT "access denied" /
# "request blocked" -- those appear in legitimate job text and would misread a
# real posting as a block. HTTP status (401/403/429) is the primary signal;
# this only catches a challenge page served with a 200.
_CHALLENGE_RE = re.compile(
    r"(please enable (?:javascript|cookies)|verify you are (?:a )?human|"
    r"complete the captcha|unusual traffic from your|cf-error-details|"
    r"attention required!|/cdn-cgi/challenge-platform)",
    re.I,
)


def _clean_text(s: str | None) -> str:
    if not s:
        return ""
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def canonical_posting_url(href: str) -> str | None:
    """Strip jsessionid / query and return the clean absolute posting URL."""
    m = _POSTING_ID_RE.search(href)
    if not m:
        return None
    return f"{BASE}/jobsearch/jobposting/{m.group(1)}"


def _extract_description(html: str) -> str:
    """Return the posting body with balanced <span> nesting handled.

    A naive non-greedy match to the first </span> truncates the description,
    which nests spans. Walk the tag stream from the opening tag and close on
    the matching depth-0 </span>.
    """
    m = re.search(r'<span[^>]*property="description"[^>]*>', html)
    if not m:
        return ""
    start = m.end()
    depth = 1
    for tag in re.finditer(r"<(/?)span\b[^>]*>", html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return _clean_text(html[start : start + tag.start()])
    return _clean_text(html[start:])  # unterminated -- take the rest


def parse_search_results(html: str) -> list[dict]:
    """Parse a Job Bank search-results page into result stubs.

    Returns [{"id", "url", "title", "employer"}], de-duplicated by posting id,
    in page order.
    """
    out: list[dict] = []
    seen: set[str] = set()
    for art in _ARTICLE_RE.finditer(html):
        block = art.group(0)
        pid = art.group(1)
        if pid in seen:
            continue
        href = None
        hm = re.search(r'href="(/jobsearch/jobposting/\d+[^"]*)"', block)
        if hm:
            href = canonical_posting_url(hm.group(1))
        if not href:
            href = f"{BASE}/jobsearch/jobposting/{pid}"
        tm = _NOCTITLE_RE.search(block)
        bm = _BUSINESS_RE.search(block)
        seen.add(pid)
        out.append(
            {
                "id": pid,
                "url": href,
                "title": _clean_text(tm.group(1)) if tm else "",
                "employer": _clean_text(bm.group(1)) if bm else "",
            }
        )
    return out


def parse_posting(html: str) -> dict:
    """Parse a Job Bank posting-detail page. Returns {title, body, employer}."""
    tm = _TITLE_RE.search(html)
    em = _HIRING_ORG_RE.search(html)
    return {
        "title": _clean_text(tm.group(1)) if tm else "",
        "body": _extract_description(html),
        "employer": _clean_text(em.group(1)) if em else "",
    }


def _employer_matches(company: str, employer: str) -> bool:
    """Loose containment either direction, on normalized names.

    Cabinet shops list themselves inconsistently ("TUSCAN WOODWORKS INC." vs
    "Tuscan Woodworks"), so compare on stripped, punctuation-free, suffix-free
    tokens.
    """
    a = set(_norm_company(company).split())
    b = set(_norm_company(employer).split())
    if not a or not b:
        return False
    return a <= b or b <= a   # token-subset, not substring ("aya" !~ "maya")


_SUFFIXES = {"inc", "ltd", "limited", "corp", "co", "group", "the"}


def _norm_company(name: str) -> str:
    toks = re.findall(r"[a-z0-9]+", name.lower())
    toks = [t for t in toks if t not in _SUFFIXES]
    return " ".join(toks)


def _default_cache_dir() -> Path:
    root = os.environ.get("SALESAGENT_CACHE_DIR")
    base = Path(root) if root else Path.home() / ".cache" / "salesagent"
    return base / "jobbank"


# --------------------------------------------------------------------------
# The fetcher
# --------------------------------------------------------------------------
@dataclass
class JobBankFetcher:
    """Callable that turns a Prospect into its Job Bank postings.

    Robots-aware, rate-limited, and disk-cached. Injectable ``http_get``,
    ``sleep`` and ``now`` make it fully testable with no network.
    """

    province: str = "Ontario"
    max_postings: int = 10
    filter_by_employer: bool = True
    cache_dir: Path = field(default_factory=_default_cache_dir)
    user_agent: str = DEFAULT_UA
    min_interval_s: float = 5.0  # floor; raised to robots Crawl-delay if higher
    http_get: Callable[[str, str], HttpResponse] = urllib_get
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], float] = time.monotonic

    _robots: RobotFileParser | None = field(default=None, init=False, repr=False)
    _last_request_t: float | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- public callable ---------------------------------------------------
    def __call__(self, prospect) -> list[dict]:
        """JobBoardAdapter fetch protocol: Prospect -> Iterable[dict]."""
        return self.fetch_for(prospect.company)

    def fetch_for(self, company: str) -> list[dict]:
        # A deliberate block (JobBoardBlocked) propagates -- that is the "STOP"
        # contract. A transient failure (JobBoardUnavailable: 404/5xx/network)
        # must NOT abort the whole pipeline batch: no jobs this cycle instead.
        try:
            html = self._get(self._search_url(company))
        except JobBoardUnavailable:
            return []

        results = parse_search_results(html)
        if self.filter_by_employer:
            # Keep results whose employer didn't parse (benefit of the doubt);
            # drop only CONFIRMED mismatches, so we never silently discard the
            # highest-confidence signal in the system.
            results = [
                r for r in results
                if not r["employer"] or _employer_matches(company, r["employer"])
            ]

        postings: list[dict] = []
        for r in results[: self.max_postings]:
            try:
                detail = parse_posting(self._get(r["url"]))
            except JobBoardUnavailable:
                continue  # one expired/removed posting must not sink the batch
            postings.append(
                {
                    "title": detail["title"] or r["title"],
                    "body": detail["body"],
                    "url": r["url"],
                }
            )
        return postings

    # -- url building ------------------------------------------------------
    def _search_url(self, company: str) -> str:
        q = urllib.parse.urlencode(
            {"searchstring": company, "locationstring": self.province, "sort": "M"}
        )
        return f"{BASE}{SEARCH_PATH}?{q}"

    # -- robots ------------------------------------------------------------
    def _ensure_robots(self) -> None:
        if self._robots is not None:
            return
        body = self._cache_read(ROBOTS_URL)  # disk-cached -> re-runs cost zero network
        if body is None:
            resp = self.http_get(ROBOTS_URL, self.user_agent)
            self._last_request_t = self.now()  # space the next request off this one
            if resp.status in (401, 403, 429) or _CHALLENGE_RE.search(resp.body or ""):
                raise JobBoardBlocked(
                    f"robots.txt fetch returned {resp.status} / a challenge page -- "
                    "automated access appears blocked. Stopping."
                )
            if resp.status == 200:
                body = resp.body
                self._cache_write(ROBOTS_URL, body)
            elif resp.status >= 500:
                raise JobBoardUnavailable(
                    f"robots.txt returned {resp.status}; refusing to crawl blind."
                )
            else:
                body = ""  # 4xx (e.g. 404) robots -> conventionally, allow all (do not cache)
        rp = RobotFileParser()
        rp.parse(body.splitlines())
        self._robots = rp
        delay = rp.crawl_delay(self.user_agent) or rp.crawl_delay("*")
        if delay:
            self.min_interval_s = max(self.min_interval_s, float(delay))

    # -- one cached, rate-limited, robots-checked GET ----------------------
    def _get(self, url: str) -> str:
        self._ensure_robots()
        assert self._robots is not None
        if not self._robots.can_fetch(self.user_agent, url):
            raise JobBoardBlocked(f"robots.txt disallows fetching {url}. Stopping.")

        cached = self._cache_read(url)
        if cached is not None:
            return cached

        self._respect_rate_limit()
        resp = self.http_get(url, self.user_agent)
        self._last_request_t = self.now()

        if resp.status in (401, 403, 429) or _CHALLENGE_RE.search(resp.body or ""):
            raise JobBoardBlocked(
                f"Job Bank returned {resp.status} for {url} -- automated access "
                "appears blocked. Stopping, per policy. A human decides next."
            )
        if resp.status != 200:
            raise JobBoardUnavailable(f"HTTP {resp.status} for {url}")

        self._cache_write(url, resp.body)
        return resp.body

    def _respect_rate_limit(self) -> None:
        if self._last_request_t is None:
            return
        wait = self.min_interval_s - (self.now() - self._last_request_t)
        if wait > 0:
            self.sleep(wait)

    # -- disk cache --------------------------------------------------------
    def _cache_path(self, url: str) -> Path:
        return self.cache_dir / f"{sha256(url.encode()).hexdigest()}.html"

    def _cache_read(self, url: str) -> str | None:
        p = self._cache_path(url)
        return p.read_text("utf-8") if p.exists() else None

    def _cache_write(self, url: str, body: str) -> None:
        self._cache_path(url).write_text(body, "utf-8")
