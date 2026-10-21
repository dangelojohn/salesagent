# Ontario real calibration corpus — sources

Every claim in `data/ontario_real.json` traces to a public page fetched on
**2026-07-09**, quoted below. Fields that could not be verified from a directly
fetched page are left **empty/null** in the JSON (never guessed). Integrity
caveats are called out per shop so you can weight them when hand-scoring.

Job postings were pulled from **Job Bank Canada** (jobbank.gc.ca, the
Government of Canada public board), which is also the live source wired into
`JobBoardAdapter` (see `salesagent/sources/jobbank.py`).

> **Read this before scoring.** From public signals alone, 8 of 10 real shops
> land at low fit — because their CNC brand and design software are simply
> **not stated publicly**. Only Chervin (public Biesse + Cabinet Vision) and
> Cartier (public CNC mention) rise. That gap between "known real manufacturer"
> and "publicly-provable capability" is exactly what your hand-scores should
> stress-test. Real BUILDs almost always require S2 deepening beyond page one
> of the web — the corpus reflects that honestly rather than inventing signals.

---

## on-cab-r001 — Deslaurier Custom Cabinets Inc. (Renfrew, ON)
- **Manufacturer / shop floor** — bbb.org (category "Cabinet Manufacturers", A+); deslaurier.com/en-ca/about: *"Our local, state-of-the-art manufacturing facility allows us to control the quality and delivery timeframe of your cabinets."*
- **Address / industrial** — yellowpages.ca: *"550 Hall Ave E, Renfrew, ON K7V 2S9"*; about page: *"rebuild a state-of-the-art green manufacturing facility in Renfrew."*
- **ERP = SAP** — Job Bank posting 49527706 (Data Processing Control Clerk): *"MS Excel. MS Word. SAP (FI/CO / HR / MM / OT SD)."* Also *"Transfer handwritten data to Excel or Word documents… Co-ordinate activities with warehouse and production units."*
- **Job (supervisor)** — Job Bank 49527705 (Woodworking machine operators supervisor).
- **Review (built-not-to-drawing)** — reviews.birdeye.com: *"all the drawers were left in piles on our floor…NONE of them fit. Other specifications outlined in the detailed plans were also not done."*
- **Google rating count 49** — birdeye (3.9★, 49 reviews, all Google).
- **Caveats**: employee count only as a LinkedIn band "51-200" → left null. No CNC brand or CAD/CAM product publicly named. A search-summary lead about a "Mozaik" posting could not be fetched verbatim → **not** recorded. NOTE: the SAP=ERP disqualifier lives in a real posting, but the pipeline only reaches S2 (jobs/reviews) when S1 fit ≥ 6; Deslaurier's public S1 fit is 2, so the agent archives it on low fit before ever seeing SAP. Worth weighing by hand.

## on-cab-r002 — Laurysen Kitchens Ltd. (Carleton Place, ON)
- **Manufacturer** — laurysenkitchens.com story page: *"110,000-square-foot manufacturing facility in Carleton Place, Ontario"*; bbb.org category "Cabinet Manufacturers".
- **Address / industrial** — "7 Industrial Avenue, Carleton Place, ON K7C 3V7" (LinkedIn + careers posting).
- **Employees 140** — story page: *"over 140 people"* (LinkedIn band "51-200").
- **Opens before 07:30 = true** — careers posting: *"Mon to Thurs 7:00 a.m. – 4:00 p.m."*
- **Job** — laurysenkitchens.com careers (5 Ton Truck Driver) — only current posting.
- **Caveats**: no CNC brand, CAD/CAM, or ERP publicly named. No verbatim reviews (HomeStars/Yelp 403).

## on-cab-r003 — Chervin Kitchen & Bath (Hawkesville, ON)
- **Manufacturer** — chervin.ca: *"67,000 square foot custom cabinetry manufacturing facility… 3541 Broadway Street, Hawkesville, ON N0B 1X0."*
- **Employees ~200** — trilliummfg.ca: *"With a team of over 200 employees, Chervin produces everything from custom cabinets… to hotel furniture."* (LinkedIn "201-500").
- **CNC = Biesse** — trilliummfg.ca: *"it purchases machinery from Biesse, a prominent supplier of woodworking automation technology. Other machines include automated sawing systems, drilling systems, and edgebanders."*
- **Software = Cabinet Vision** — planitcanada.ca success story: *"Since 2005, Planit Canada has implemented 35 Cabinet Vision licenses in Chervin's shops… running CV modules Solid Ultimate and S2M Ultimate."*
- **Caveats**: the Cabinet Vision quote was returned by search indexing of the Planit page (direct WebFetch was bot-blocked) — slightly lower confidence than the Biesse source. **Important entity note:** the retail-only "Chervin Furniture & Design" storefront (19 Arthur St S, Elmira) is a *different* entity; this record is the **manufacturing** sister company, Chervin Kitchen & Bath.

## on-cab-r004 — AyA Kitchens and Baths Ltd. (Mississauga, ON)
- **Manufacturer** — ayakitchens.com: *"Canada's foremost manufacturer of high quality, frameless cabinetry… a 150,000 sq. ft. state-of-the-art production facility."*
- **Address / industrial** — "1551 Caterpillar Rd, Mississauga, ON L4X 2Z6" (site + KCMA).
- **Employees 139** — LinkedIn: *"Discover all 139 employees"* (self-reported band "201-500").
- **Job** — ayakitchens.com careers (Retail Business Development Supervisor; *"Knowledge of Microsoft office"* — a **retail sales** role, not production).
- **Review (lead-time slip)** — bestprosintown.com: *"multiple delays… delays in installation date… delivery was not until October 28th - 15 weeks after I started the process!"*
- **Caveats**: no CNC brand / CAD-CAM / ERP publicly named. Location corrected from "Vaughan" (prompt) to Mississauga (all sources). The delay review only reaches scoring if S1 fit ≥ 6; AyA's public fit is 2.

## on-cab-r005 — Cartier Kitchens (Brampton, ON)
- **Manufacturer + CNC present** — ca.indeed.com worker review: *"Working as machine operator (Panel cutter and CNC Router)"*; improvecanada.com: *"manufacturing facility located in Brampton, Ontario."*
- **Address / industrial** — bbb.org: *"8 Chelsea Lane, Brampton, ON L6T 3Y4."* (Concord/Vaughan is a showroom booth, not the plant.)
- **Employees 54** — rocketreach.co: *"54 total employees"* (LinkedIn band "51-200").
- **Review** — bbb.org: *"The job was left incomplete despite clear agreements on timelines, with poor workmanship…"*
- **Caveats**: CNC **brand** is not public (worker review confirms a CNC router exists, no make). The "CNC Router" evidence is sourced from an Indeed worker review, used here as capability text. Employee count is soft (RocketReach). No CAD/CAM or ERP named.

## on-cab-r006 — Downsview Kitchens (Mississauga, ON)
- **Manufacturer** — downsviewkitchens.com/about: *"110,000 square foot building… does everything from cutting and sanding to spray painting and installing… over 200 employees."*
- **Address / industrial** — downsviewkitchens.com location page: *"2635 Rena Road, Mississauga, ON L4T 1G6."*
- **Opens 09:30 (not before 07:30)** — yellowpages.ca.
- **Caveats**: no CNC brand, CAD/CAM, or ERP named (about page: *"automated computerized machinery has never taken priority over the hand of the craftsman"* — no brand). No jobs on Job Bank/Indeed; no fetchable reviews. Location corrected from "North York" to Mississauga plant.

## on-cab-r007 — Muti Kitchen & Bath Inc (Toronto, ON)
- **Manufacturer status = AMBIGUOUS (encoded as no shop floor)** — mutikb.com/about: *"Ontario's Premier Kitchen Designer and Manufacturer… crafted in Canada"*, BUT homepage: *"Made to Measure | Made in Italy"*, LinkedIn industry *"Design Services"*, and a customer: *"items were… damaged during transit from Italy."* No evidence of an owned CNC shop floor.
- **Address** — 143 Tycos Drive, Toronto (showroom) + Oakville showroom + 30,000 sq ft warehouse.
- **Employees 22** — LinkedIn: *"View all 22 employees"* (band "11-50").
- **Reviews (built-not-to-drawing / late)** — archived HomeStars: *"certain items were manufactured differently then shown on drawings we signed off on"*; *"never on time!"*
- **Caveats**: I set `manufacturer_tag = false` (types = store/showroom) because the weight of evidence is import/design, not in-house manufacturing — this drives the "no shop floor" disqualifier. **This is a judgment call on ambiguous evidence; flip it if your read differs.**

## on-cab-r008 — Magnum Kitchens (Mississauga, ON)
- **Manufacturer** — ckca.ca directory (Business Type "Manufacturer"); magnumkitchens.ca: *"custom cabinetry made in house using Canadian materials."*
- **Address / industrial** — magnumkitchens.ca: *"1885 Drew Road Unit #6/7 Mississauga, ON L5S 1J5."*
- **Employees ~5** — LinkedIn (aggregator-surfaced; soft).
- **Google rating 55** — yably (4.80★, 55 Google reviews; page itself 403, figure search-surfaced → soft).
- **Job** — Job Bank 49368623 (Cabinetmakers Foreman): *"Prepare bids. Estimate costs and materials. Operate CADD and other computer software systems. Co-ordinate and schedule activities."* (generic NOC boilerplate — no named product, no Excel/QuickBooks).
- **Caveats**: employee count and Google count are soft (LinkedIn/yably 403). No CNC brand / CAD-CAM / ERP named.

## on-cab-r009 — Bloomsbury Fine Cabinetry Inc. (Newmarket, ON)
- **Manufacturer** — bloomsburykitchens.com: *"we make, in our own quality-controlled workshop… Handmade in Ontario."*
- **Address / industrial** — "415 Harry Walker Parkway North, Unit 4, Newmarket, ON L3Y 8T9" (Harry Walker Pkwy industrial park).
- **Employees ~40** — careers page: *"employing over 40 team members"* (LinkedIn band "11-50").
- **Software (public)** — careers page Designer role: *"Proficient in AutoCAD, CabinetVision, 2020 Technologies, or similar."*
- **Jobs** — bloomsburykitchens.com/careers1 (Cabinetmaker; Designer & Project Manager).
- **Caveats**: they publicly list **Cabinet Vision** (CAD/CAM, ideal), but written as one word "CabinetVision", so the string extractor does **not** auto-detect it (a real parser gap, not fixed here per scope). Weigh this by hand — this is arguably a stronger prospect than the agent's fit score shows.

## on-cab-r010 — Tuscan Woodworks Inc. (North York, ON)
- **Manufacturer** — taggroup.ca/divisons: *"Tuscan Woodworks: produces specialty millwork for unique custom projects with an in house design and fabrication team."*
- **Address / industrial** — "2901 Steeles Avenue West Unit 6, North York, ON M3J 3A5" (toronto-furniture.com, wineguardian.com, Job Bank employer record).
- **Job** — Job Bank 49859515 (Cabinetmaker): *"Operate woodworking machines… Study plans, specifications or drawings… Operate CADD and other computer software systems… Estimate costs and materials."*
- **Caveats**: employees not publicly disclosed → null. No CNC brand / CAD-CAM / ERP named. No reviews found. Division of The Automated Group (Tag Group).
