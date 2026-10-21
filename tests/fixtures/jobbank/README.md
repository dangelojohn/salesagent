# Job Bank test fixtures

Recorded HTML doubles for `salesagent.sources.jobbank`, used so the test suite
runs with **zero network**.

The markup here is trimmed but structurally faithful to real Job Bank Canada
pages, verified live on 2026-07-09 against:

- search: `https://www.jobbank.gc.ca/jobsearch/jobsearch?searchstring=cabinetmaker&locationstring=Ontario`
- posting: `https://www.jobbank.gc.ca/jobsearch/jobposting/49859515`

The parser keys on: `<article id="article-ID">`, `<span class="noctitle">` (search
title), `<li class="business">` (employer), `<span property="title">` (posting
title), `<span property="hiringOrganization">…<span property="name">` (employer),
and `<span property="description">` (body, with balanced nested spans).

The *content* (company names, job text) is illustrative — these test the
fetcher's parsing/filtering/caching/blocking logic, not any real company.
Real, sourced company data lives in `data/ontario_real.json`.
