# salesagent — C1/C2 Discovery & Validation

Autonomous prospect discovery and validation for the OdooIQ demand-gen loop.
Finds Southbrook-sized cabinetry/millwork manufacturers who need an MRP,
proves they don't already have one, and hands a cited, compliant,
build-ready prospect to C3.

```bash
pip install pytest --break-system-packages
python3 -m pytest tests/ -q     # 28 tests
python3 calibrate.py            # MUST pass before running unattended
python3 demo_run.py             # full cycle over Ontario fixtures
```

---

## The one idea

**You are hunting an absence.** "Has CNC" is confirmable. "Has no MRP" is not —
silence is not evidence. So every prospect carries two independent numbers:

| axis | question | ceiling |
|---|---|---|
| `fit_score` | do they match the ICP? | 14 (threshold 7) |
| `absence_confidence` | are we *sure* they have no MRP? | 1.0 (threshold 0.76) |

```
BUILD   iff fit >= 7 AND confidence >= 0.76 AND software/router tiers permit
ENRICH  iff fit >= 7 AND confidence <  0.76      -> go find more evidence
PARK    iff fit in 4..6
ARCHIVE iff fit < 4 OR any disqualifier
```

With zero S2 evidence, confidence is floored at **0.20 and can never exceed it**.
A perfect-fit shop with no absence evidence goes to ENRICH, never BUILD.

That single rule prevents the failure mode this whole design exists to stop:
emailing a bespoke MRP demo to a shop that quietly bought Epicor in 2023.

---

## Three decisions that matter

### 1. Software is three tiers, not a boolean

Cyncly owns **Mozaik** (CAD/CAM → ideal prospect) *and* **Insight**
(cabinet-shop ERP → disqualification). Microvellum integrates with
**INNERGY ERP** → contested, not greenfield.

A binary "has design software = good signal" rule emails demos to a
competitor's existing customers.

| tier | examples | verdict |
|---|---|---|
| CAD/CAM | Cabinet Vision, Mozaik, KCDw | **ideal** — digital BOMs going nowhere |
| Hybrid | Microvellum, CAD+T | contested track — an ERP vendor is already in the room |
| ERP | Insight, INNERGY, Allmoxy, Epicor, Odoo | **archive** — migration sale, different motion |

### 2. Evidence combines by noisy-OR, not addition

Additive confidence saturated after three signals and made the threshold
decorative — every high-fit prospect sailed through the gate regardless of
evidence quality. `calibrate.py` caught it. The fix:

```
confidence = 1 - Π(1 - cᵢ)     over the strongest signal per category
```

Asymptotes toward 1.0 without ever pinning there. More evidence always helps
and never lies. Per-category caps mean **three job posts naming Excel is one
fact, not three**. The same capping applies to `fit_score`.

Consequence: a single job-board signal can no longer reach the gate.
**Corroboration from a second independent category is required to build.**

### 3. Timing beats fit

`fit` says they *should* buy. A trigger says they're deciding *now*.
The build queue sorts by trigger priority first, then confidence, then fit.

A 7-fit shop hiring an estimator beats a 12-fit shop that's quiet — the first
one is four weeks from spending $70K on the problem you delete.

**The hottest signature in the system:**
> industrial-tier router financed < 18 months ago (PPSA)
> \+ CAD/CAM software, no ERP tier
> \+ estimator posting < 30 days old

Six figures of production capability, digital BOMs going nowhere, about to
hire a human to do software's job. Build that demo the day it surfaces.

---

## Pipeline

Sources are **stages**, not equal-weight inputs. Cheap sources seed;
expensive sources confirm. Cost per qualified prospect is held down by the
funnel shape, not by throttling.

| stage | purpose | runs on |
|---|---|---|
| S0 SEED | build the universe (StatsCan, Frasers, Scott's, Places, CKCA) | everyone in NAICS × region |
| S1 SCORE | score fit from digital exhaust (website, Places, social) | all seeds |
| S2 CONFIRM | **prove absence** (job boards, reviews, PPSA, registry, dealers, communities) | `fit >= 6` only |
| S3 TRIGGER | detect a live buying window | `fit >= 7` only |
| S4 CONTACT | resolve owner + compliant channel | BUILD only |

**Job postings are the richest source in the entire system.** A posting is a
company publicly declaring what it lacks and what it's about to spend money on.
`"proficient in Excel and QuickBooks"` in a *production* role is the strongest
single tell available anywhere (`c = 0.35`). The daily job-board delta is the
cheapest poll in the pipeline and produces the most valuable output. **If only
one job runs every morning, run that one.**

---

## Guardrails, all enforced in code

- **Uncited evidence is rejected at construction.** `Evidence` raises without a
  `source_url` and `matched_text`. No citation → the signal does not count.
- **Disqualifiers dominate score.** An ERP hit archives an 14-fit prospect
  instantly and zeroes confidence.
- **Compliance gate cannot be bypassed.** CASL applies where the message is
  *accessed*, not where the sender sits. US-domiciled + Ontario ops →
  `["CASL", "CAN-SPAM"]`, `strictest_of`. Express consent is **never assumed**.
  Purchased lists, breach data, scraped personal inboxes, and ToS
  circumvention are refused by provenance check. Blocked sends are still audited.
- **Cost governor** cannot be overridden by any agent. Only a human raises a ceiling.
- **Kill switch** is supreme, checked at every stage.
- **Community posts are read-only scoring input, never an outreach hook.**
  Quoting someone's forum complaint back at them in a cold email makes you the
  vendor the whole community warns each other about. In a network this tight,
  that's a one-shot mistake.

---

## Calibrate before you automate

```bash
python3 calibrate.py
```

Hand-score ten shops. Compare against the agent.

- **More than two disagreements** → the weights are wrong, not the model.
- **Zero disagreements** → the threshold is too loose; the agent is agreeing
  with you by construction, not by discrimination.
- **Confidence pinned at ceiling across the corpus** → the axis has stopped
  discriminating and the threshold is decorative.

The harness checks all three and exits non-zero on any of them.
It caught a real saturation bug in this codebase; that's why the combiner is
noisy-OR and not a sum.

**Calibrate on ten before you spend on ten thousand.**

---

## Wiring to live sources

Every adapter takes a `fetch` callable. Swap fixtures for crawlers; nothing
else changes.

```python
JobBoardAdapter(fetch=lambda p: indeed.search(p.company, region="ON"))
PPSAAdapter(fetch=lambda p: ppsa_ontario.liens(p.company))
```

Model routing (per the schema): local models for bulk crawl, dedupe, regex,
and review-text classification; **Claude for job-post semantics** — that nuance
decides `absence_confidence`, the number that matters most — and for evidence-
dossier assembly, which must be legible to you when the agent gets it wrong.

## Layout

```
salesagent/
  models.py       Prospect, Evidence, tiers, decisions
  taxonomy.py     software tiers, router tiers, weights, triggers, thresholds
  scoring.py      two-axis engine, noisy-OR, DQ dominance, queue ordering
  extractors.py   cited-signal extraction (regex floor, model hooks for the ceiling)
  compliance.py   jurisdiction gate, suppression, consent, audit log
  pipeline.py     S0-S4 orchestration, cost governor, kill switch
  sources/        adapters (Places, website, jobs, reviews, PPSA, registry, dealers, community)
calibrate.py      run this before the agent runs unattended
demo_run.py       full cycle over Ontario fixtures
```
