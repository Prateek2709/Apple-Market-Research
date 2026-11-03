# iPhone India Market Signals: Data Collection and Feature Plan

Revised Nov 2, 2026 · @Prateek Mishra

## Objective and scope

The job right now is to build an independent external dataset on the Indian iPhone market: collect, clean and curate public data, engineer market features, and construct two interpretable indicators from them, **Overall Market Sentiment (MS)** and **Demand Pressure (DP)**. The data covers retail prices and offers, consumer interest and intent, Android competitor movements, stock and delivery conditions, and market events. Forecasting, backtesting, inventory optimisation and integration with the existing forecasting pipeline are out of scope.

Nothing here is fixed. Sources, features, component weights, thresholds and implementation details are starting choices, to be revised as the collected data shows what is available, reliable and informative. The working order is: source identification → extraction → cleaning and curation → feature engineering → MS and DP generation.

### Business context

- **Independent market catalogue.** The dataset is built only from public product information, retailer observations, competitor information and consumer-behaviour sources. No step needs the distributor's internal data as an input, and the final table is not built by joining to internal orders.
- **Internal data stays separate.** The distributor's order records feed the existing forecasting process. This research complements that work and does not modify, merge with or replace those records.
- **What the internal data is not.** Those orders are upstream purchases from Apple. They do not show consumer sell-through, retailer or partner inventory movements, or final retail sales. The external indicators likewise describe observable market conditions, not sales, and should be read that way. No supply-chain model is needed for this.
- **External prices** are consumer-facing retail prices: advertised selling price, MRP, discounts, bank offers, cashback, EMI, exchange benefits. Vendor purchase prices appear nowhere in this dataset.
- **Future integration.** Product keys (sku\_id, price\_key, model\_key) and Sunday–Saturday week\_start dates are kept consistent and stable so a later join is possible. No integration is implemented now.
- **Out of scope:** forecasting models and backtests, inventory optimisation, dashboards, schedulers, and DG-specific events and adjustments.

### Active catalogue scope

The active catalogue covers the families below, checked against Indian launch coverage and Apple India listings. ✓ = confirmed from sources found on 2 Nov 2026; ? = expected, to be confirmed on Apple's India configurator before the catalogue is frozen. Only models commercially launched in India are included.

| Model | Storage | Colours | India sale start | Apple India store (Nov 2026) | Verified |
| --- | --- | --- | --- | --- | --- |
| iPhone 18 Pro | 256GB, 512GB, 1TB, 2TB | Black, Silver, Glacier, Burgundy | 18 Sep 2026 | Listed | ✓ |
| iPhone 18 Pro Max | 256GB, 512GB, 1TB, 2TB | Black, Silver, Glacier, Burgundy | 18 Sep 2026 | Listed | ✓ |
| iPhone 17 Pro | 256GB, 512GB, 1TB | Silver, Deep Blue, Cosmic Orange | 19 Sep 2025 | Removed Sep 2026; retailers sell remaining stock | ✓ |
| iPhone 17 Pro Max | 256GB, 512GB, 1TB, 2TB | Silver, Deep Blue, Cosmic Orange | 19 Sep 2025 | Removed Sep 2026; retailers sell remaining stock | ✓ |
| iPhone 17 | 256GB, 512GB | Lavender, Sage, Mist Blue, White, Black | 19 Sep 2025 | Listed; price raised Sep 2026 | ✓ |
| iPhone 17e | 256GB, 512GB | Black, White, Soft Pink | 11 Mar 2026 | Listed; price raised Sep 2026 | ✓ |
| iPhone Air | 256GB, 512GB, 1TB | Space Black, Cloud White, Light Gold, Sky Blue | 19 Sep 2025 | Listed; price raised Sep 2026 | ✓ |
| iPhone 16 (base) | 128GB, 256GB, 512GB (expected) | Black, White, Pink, Teal, Ultramarine (expected) | Sep 2024 | Listed; price raised Sep 2026 | ? storage and colours |
| iPhone 15 (base) | 128GB, 256GB, 512GB (expected) | Black, Blue, Green, Yellow, Pink (expected) | 22 Sep 2023 | Removed Sep 2025; retailer stock only | ? storage and colours |

The verified rows give 81 colour × storage SKUs, assuming every listed colour is sold at every listed storage (to be confirmed on the configurator); the 15 and 16 base models would add about 30 more once their options are confirmed. A model Apple has delisted stays active while any tracked retailer still lists it: the 17 Pro and Pro Max, for example, keep producing rows from retailer observations. Weeks with no observations stay in the table as Insufficient Evidence rather than being dropped.

**Excluded** from the active dataset: iPhone 16e; iPhone 15 Plus, Pro and Pro Max; iPhone 16 Plus, Pro and Pro Max; the iPhone Duo (on sale in India from 23 Oct 2026; its launch is still logged as a market event); and any model not yet on sale in India, including the base iPhone 18, the 18e and the Air 2. Unreleased variants are not added in advance; they enter the catalogue when Indian availability is confirmed.

**Reference-only records.** Models outside the active scope are kept in the catalogue only where a predecessor comparison needs them: iPhone 14 (base), 16e, 16 Pro and 16 Pro Max. They get a catalogue row, launch MRP, a search-interest series and any retail prices needed for the same-date price gap, and nothing else: no ratings or comment collection, no rows in the final table, no derived targets.

**Configurable scope.** One file decides what is active; every stage reads it, so a model can be added or removed without code changes. Adding a model means listing it here and rerunning the catalogue build, which pulls its colour and storage options, identifiers and launch data from Apple India and spec sites.

```
# config/active_scope.yaml
active:
  iphone-15:  [base]
  iphone-16:  [base]
  iphone-17:  [base, e, pro, pro-max]
  iphone-18:  [pro, pro-max]
  iphone-air: [air]
reference_only:
  iphone-14:  [base]
  iphone-16:  [e, pro, pro-max]
```

### Final dataset and product catalogue

The final feature table has one row per **week × model × colour × storage** (Sunday–Saturday weeks, identified by week\_start) for every active SKU, e.g. iPhone 18 Pro Max · Silver · 256GB. Raw and curated tables stay at their natural source grain; the SKU-level table is assembled only at the end of feature engineering, from the independent catalogue and external observations alone. Weekly is the primary grain because observations arrive irregularly; daily views exist only for dates a source was actually captured.

Pricing and colour rule: **retail price varies by model × storage, not by colour.** Price features are computed at model × storage and repeated across colours; colour never gets its own price. Colour matters only through separately observed evidence (colour-level stock, ratings, mentions and search interest, kept in their own tables), which can adjust the two indicators when it is strong enough (see C. Derived targets).

The catalogue (catalogue/products.csv) is the backbone of every join:

| Field | Example |
| --- | --- |
| sku\_id (model \| storage \| colour) | iphone-18-pro-max\|256gb\|silver |
| price\_key (model \| storage) | iphone-18-pro-max\|256gb |
| model\_key (model) | iphone-18-pro-max |
| model, generation, tier | iPhone 18 Pro Max, 18, Pro Max |
| storage\_gb, colour | 256, Silver |
| scope\_status | active or reference\_only |
| segment (competitor group) | Pro Max |
| india\_launch\_date, india\_launch\_mrp, apple\_delisted\_date | 2026-09-18, 179900, — |
| public identifiers | Apple part number, ASIN, Flipkart FSN, Croma and Reliance codes |
| predecessor\_price\_key, mapping\_type | iphone-17-pro-max\|256gb, exact |
| verified\_on, verified\_source | 2026-11-02, Apple India configurator |

Catalogue sources: Apple India product and configurator pages (storage, colours, part numbers, launch MRP), Wayback snapshots for older launches, Smartprix, 91mobiles and GSMArena spec sheets, and retailer listings for identifiers. Predecessor mapping rules are in Feature engineering, section B.

## Data sources

Sources are split into three tiers: reliable and free (build first), experimental (useful but uncertain access or quality), and paid (optional). Marks: ✓ = confirmed from current documentation or coverage; ? = assumption to verify before building.

Two access changes since the original plan matter most. pytrends, the usual Google Trends client, is archived and now fails with HTTP 429s. Reddit's free API needs explicit approval, is non-commercial only, and stopped taking new access requests on 31 Oct 2026. Neither should be a foundation source.

Collection is on demand (see Collection, cleaning and curation), so "per run" and "prospective" entries below mean data exists only for the dates a run captured it. Sources with archives or history (Wayback, Trends, YouTube comments, Wikipedia, GDELT) can be backfilled in any run; retail prices, offers, stock and delivery cannot.

### Tier A: reliable and free

| Source | What we extract | Access and cost | History | Granularity | Python |
| --- | --- | --- | --- | --- | --- |
| Retailer product pages: Amazon.in, Flipkart, Croma, Reliance Digital, Vijay Sales | Selling price, MRP, discount, bank/cashback/EMI/exchange offer text, stock, delivery estimate, seller, star rating and review count, review text with date and verified-purchase flag, the colour or storage variant label where a review shows one, and popularity badges such as "bought in past month" where shown (? confirm per retailer, and that terms permit collecting review text) | No usable free API: Amazon's PA-API was retired in 2026 and its Creators API replacement needs an active Associates account (✓). Scrape public pages at low rate; check robots.txt and terms per site (?) | Prospective only | Per run, SKU × retailer | httpx, selectolax / BeautifulSoup; Playwright for JS-rendered pages |
| Apple India online store | Official MRP per SKU, storage and colour options, part numbers, delivery estimate by pin code, availability (also the catalogue's main source) | Public pages, scrape (?) | Prospective only | Per run, SKU | Same as above |
| Wayback Machine (CDX API) | Archived snapshots of Apple and retailer product pages, to reconstruct past MRP and some past prices | Free, no key (✓ for the API); snapshot coverage per URL is irregular (?) | Back to each URL's first capture | Irregular | requests, cdx\_toolkit or waybackpy |
| Google Trends | Search interest by model and query, India and states; related and rising queries | Official API is an application-gated alpha with a rolling \~5-year window and consistent scaling (✓, [PPC Land](https://ppc.land/google-opens-alpha-testing-for-new-trends-api-targeting-developers-and-journalists/)); apply now. Until approved, use trendspyg (free, maintained, unofficial) (✓ exists; reliability ?) | \~5 years | Daily for short windows, weekly for long | Official client if approved; trendspyg |
| YouTube Data API v3 | Review and unboxing videos: views, likes, comment text and timestamps | Free, 10,000 quota units/day by default; search costs 100 units, comment pages 1 unit (? confirm in console) | Comments: full history. Views: current only, so snapshot at each run | Video/comment level | google-api-python-client |
| Wikipedia pageviews API | Daily views of iPhone and rival model articles | Free, no key | Since July 2015 | Daily | requests or mwviews. Not geo-filterable: a global attention proxy only |
| GDELT | Indian news coverage counts and tone on iPhone pricing, launches, sales, duties | Free | 2015 onward; the DOC API returns a rolling 3-month window, full history via BigQuery free tier (?) | Daily | gdeltdoc |
| Financial context and event calendar | Only two financial series: AAPL daily close and percentage moves, and USD/INR level and percentage moves. Separately, the hand-built events table: Apple and Android launches, Apple price changes, festive sale dates, duty or GST changes | AAPL and USD/INR: yfinance, unofficial, free, no key, may rate-limit (✓). USD/INR cross-check: Frankfurter API, free, no key or quota, central-bank reference rates (✓, Frankfurter docs). Events: public news and releases | AAPL and USD/INR: full history. Events: from the catalogue and hand-built table | AAPL: trading days; USD/INR: working days; events: per occurrence | yfinance (AAPL, INR=X), requests for Frankfurter, manual CSV for events |
| Industry tracker press releases (Counterpoint, IDC, Canalys) | Quarterly India shipment growth, Apple share, premium-segment share | Free press releases; full reports paid | Several years | Quarterly | Manual curation |

### Tier B: experimental

| Source | What we extract | Access and cost | History | Notes |
| --- | --- | --- | --- | --- |
| Smartprix, 91mobiles, GSMArena | Popularity rankings, cross-retailer price listings, spec sheets, comment volume | No public API; scrape (?) | Prospective; any on-site price history needs checking (?) | Spec sheets are reliable for the competitor catalogue; popularity rankings are site-audience-specific |
| Price-history trackers (e.g. pricehistory sites, Keepa's free charts) | Past Amazon/Flipkart prices | Free to view; automated extraction may breach terms (?) | Often years | Only route to free historical retail prices besides Wayback; check terms first |
| Reddit | Intent, switching and complaint posts from r/IndiaTech, r/india, city subs | Free tier is approval-gated and non-commercial (✓, [Serpent API](https://apiserpent.com/blog/free-reddit-api)); new access requests closed on 31 Oct 2026, and a vendor project likely needs a paid contract. Arctic Shift archives exist for history (?) | Archives only | Small Indian sample; treat as optional |

### Tier C: paid, optional

| Source | Why consider it | Cost |
| --- | --- | --- |
| Keepa API | Years of Amazon.in price and rank history per ASIN, the only practical way to recover 15/16-era Amazon prices | From €49/month, no free API tier (✓, [RevenueGeeks](https://revenuegeeks.com/software/keepa/api)). The one paid source worth a month's trial for backfill |
| X API | Sale-day and launch reaction | Pay-per-use, about $0.005 per post read, no free tier for new developers since 6 Feb 2026 (✓, [Postproxy](https://www.postproxy.dev/blog/x-api-pricing-2026/)). Skip initially |
| Managed scrapers (Apify actors etc.) | Fallback for Trends or JS-heavy retailer pages | Small recurring free credits, then paid |

## Retail price and offer collection

Retail pricing is the primary collection area and the one with the least recoverable history, so it gets the earliest runs. Every observation stays at retailer × listing × fetch-time level; market-level prices are computed later, never stored in place of the raw rows. An observation records what a page showed at the moment of a run, nothing more.

### What one observation holds

| Table | Grain | Key fields |
| --- | --- | --- |
| price\_obs | Retailer × listing × fetch time | run\_id, fetch\_ts, retailer, url, listing\_id (ASIN, FSN, retailer SKU), raw\_title, price\_key, sku\_id (canonical; colour only where the page names it), seller, mrp, selling\_price, in\_stock, delivery\_days, pin\_code, rating, review\_count, page\_hash, raw\_path |
| offer\_obs | One row per offer on that observation | offer\_type (bank\_instant, bank\_cashback, no\_cost\_emi, exchange\_bonus, coupon, retailer\_cashback), is\_conditional, eligibility (card issuer, min spend, tenure), value\_abs, value\_pct, cap, raw\_text |

Reviews and colour evidence are stored separately, at their own grain, so scoring methods can change later without re-collecting:

| Table | Grain | Key fields |
| --- | --- | --- |
| review\_obs | One row per retailer review | run\_id, fetch\_ts, retailer, listing\_id, review\_id, review\_date, rating, text, verified\_purchase, variant\_colour and variant\_storage (only where the review shows them), raw\_path |
| colour\_obs | One row per source observation that names a colour | source (retailer stock, review, comment, Trends colour query), model\_key, colour, storage (if known), obs\_ts or week\_start, metric (in\_stock, delivery\_days, rating, mention, sentiment, search\_interest), value, n |

### Advertised vs conditional prices

Keep three price levels per observation, because only the first is available to every buyer:

- **Advertised price** P\_adv = the selling price shown to everyone.
- **Unconditional net price** P\_net = P\_adv − coupons or instant discounts that need no card or trade-in.
- **Best card price** P\_card = P\_net − max(bank instant discount, capped at its stated limit). Store which issuer gives it.

Exchange bonuses and no-cost EMI stay as separate fields, not folded into price: exchange value depends on the buyer's old device, and no-cost EMI is a financing subsidy (record tenure and the waived-interest amount when stated). Parse offer text into these fields with rules first, and keep raw\_text so parsing can be redone.

### Collection settings

- Listing list from the catalogue: every active model × storage, plus colour-level listings where a retailer lists colours separately (needed for colour stock and colour-tagged reviews). Reference-only models are fetched only for the prices and Trends series their predecessor features need.
- Fixed panel of 3–5 metro pin codes for stock and delivery checks.
- One fetch per listing per run. Run more often when the page state changes quickly (launch weeks, festive sales, announced price changes); there is no fixed frequency.
- Polite rate limits, a real user agent, and a stop on any site whose terms prohibit automated access. Review text is collected only where terms permit.

### What can be recovered historically

| Data | Historical? | How |
| --- | --- | --- |
| Apple MRP per SKU, including the Sep 2026 price changes | Yes | Wayback snapshots of the Apple India store, plus launch-day press coverage |
| Retailer selling prices | Partial | Wayback (sparse); price-history sites if their terms allow; Keepa for Amazon.in (paid) |
| Festive-sale headline prices | Partial | News coverage of each sale's iPhone deals, curated manually into an events table |
| Bank, EMI and exchange offers | Mostly no | Sale-period news coverage only; otherwise prospective |
| Stock and delivery | No | Prospective only |

**Between runs nothing is observed.** Prices, temporary promotions, offers, stock and delivery estimates that appeared and disappeared between two runs are not recoverable, except where Wayback or a price-history site happens to hold them. They are not estimated or filled. Each observation keeps its own timestamp, gaps between runs are recorded, and weekly tables carry the number of observations behind each value, so a weekly price means "the price observed in that week", not "the price on every day of it".

## Android competitor groups

Use four small groups aligned to iPhone segments, with membership decided by price relative to the segment's iPhone plus a flagship-class check. No model-to-model mapping and no per-storage or per-colour groups.

### Membership rule

An Android model m belongs to group g on date t when all three hold:

1. It is on sale in India at t.
2. 0.60 · P\_ref,g(t) ≤ P\_m(t) ≤ 1.10 · P\_ref,g(t), where P\_ref,g(t) is the median advertised price of the segment's current reference iPhone (base storage) across retailers, and P\_m(t) is the Android model's median advertised price at comparable storage.
3. It is a flagship or upper-premium model by chip tier, camera system and brand positioning, so a cheap phone that happens to match on price but not capability stays out.

On the threshold: 60% is a reasonable default, since phones at that level often match iPhones on headline specs and are what Indian buyers cross-shop. It should not be fixed blindly. **Collect a wider superset (down to about 50%) and store the price ratio P\_m / P\_ref on every row**, so the threshold can be tested at 55, 60 and 65% at feature time without re-collecting. Check each choice against cross-shopping evidence: Trends related queries ("iPhone 17e vs …") and comparison pages on Smartprix and 91mobiles. Overlap between groups is fine; a Galaxy S Ultra can sit in both Pro and Pro Max.

**Reference prices.** Where a group has two reference iPhones (Entry and base: the 17e and the 17), the lower bound uses the cheaper one and the upper bound the dearer one. Cheaper Android phones are deliberately kept: a phone at 60–70% of the iPhone's price with comparable headline specifications is exactly the cross-shopping case the group exists to capture.

**Stability.** Membership is decided from the dated observations that exist, not from a weekly rhythm, so irregular runs work. A model's price ratio P\_m / P\_ref is evaluated at every observation date. It joins a group once it has been inside the band on at least 2 observation dates at least 14 days apart, with none outside the band in between, so one date caught during a short promotion is not enough. It leaves once it has been more than 5 percentage points outside the band on at least 2 observation dates at least 28 days apart, with none inside in between, or when it is discontinued. Between observations, membership carries forward unchanged; if the gap since the last observation exceeds 60 days, membership is held but flagged stale. On a first run, or when a model has a single observation, membership uses that ratio (and the India launch price where known) and is flagged provisional until the sustained rule can be applied. Overlap is allowed, so one model can sit in two groups and move between groups over time. Because the ratio is stored on every row, these values (2 dates, 14 and 28 days, 5 points, 60 days) can be rerun with different settings without recollecting.

### Groups and representative series

Series names below are starting candidates; confirm the current model in each series and its Indian availability from the Smartprix or 91mobiles spec catalogue (?).

| Group | Reference iPhone (changes over time) | Representative Android series |
| --- | --- | --- |
| Entry and base | 15 and 16 base earlier; 17e and 17 now | Galaxy S (base) and S FE, Pixel (base) and Pixel a, OnePlus numbered flagship, Nothing flagship, vivo X (base), Xiaomi numbered series |
| Pro | 17 Pro from Sep 2025; 18 Pro from Sep 2026 | Galaxy S+ and S Ultra, Pixel Pro, vivo X Pro, OnePlus numbered flagship, Xiaomi Ultra |
| Pro Max | 17 Pro Max from Sep 2025; 18 Pro Max from Sep 2026 | Galaxy S Ultra, Pixel Pro XL, vivo X Pro, Xiaomi Ultra |
| Air | iPhone Air | Galaxy S25 Edge while still sold; otherwise compare the Air against the Entry and base group |

Foldables stay out, since they compete mainly with the excluded Duo.

### What to collect per competitor

- The same price and offer tables as iPhones (price\_obs, offer\_obs), for base storage at minimum.
- A static attribute row: India launch date and launch price, chip, RAM, base storage, main camera, battery, charging, display, software update years.
- Search interest, popularity rank and Wikipedia pageviews at model level.
- Launch events in the events table, so group-level launch pressure can be computed.

## Collection, cleaning and curation

A small Python package with one collector per source, an immutable raw layer, and Parquet tables queried with DuckDB. It runs on demand from scripts or a notebook: no scheduler, cron job, service or monitoring.

### Layout

```
market_signals/
  config/       active_scope.yaml, weights.yaml (component weights, thresholds, minimum volumes)
  catalogue/    products.csv, aliases.csv, competitor_groups.csv, events.csv
  collectors/   retail_amazon.py, retail_flipkart.py, retail_croma.py, ..., apple_in.py,
                wayback.py, trends.py, youtube.py, wiki.py, gdelt.py, financial.py
  parse/        one parser per retailer, offer_parser.py, review_parser.py
  clean/        normalise.py, match.py, dedupe.py
  features/     price.py, competition.py, interest.py, colour.py, lifecycle.py, events.py,
                predecessor.py, targets.py, registry.yaml
  data/
    raw/<source>/<yyyy-mm-dd>/   HTML or JSON exactly as fetched + fetch metadata (append-only)
    bronze/<table>.parquet       parsed fields, no cleaning
    silver/<table>.parquet       cleaned, typed, matched to sku_id or price_key
    gold/<table>.parquet         weekly feature tables and the final SKU table
    meta/runs.parquet            one row per run: fetched, parsed, rebuilt, failed
  run.py        collect | parse | clean | build | targets | all   [--sources ... --since ... --full-rebuild]
```

Raw files are never modified, so any parser or matching fix can be replayed over all history. Libraries: httpx, selectolax or BeautifulSoup, Playwright (JS pages only), tenacity, pandas or polars, pyarrow, duckdb, rapidfuzz, pydantic for row schemas.

### On-demand runs

Everything runs when you start it (`python run.py all`, or the same steps from a notebook). Each run:

1. **Collects** the latest accessible data for every enabled source, plus any historical backfill not yet fetched. Backfills are tracked per source and date range, so a range is fetched once.
2. **Preserves** earlier observations: raw files are append-only and never overwritten.
3. **Cleans and reconciles** by parsing only raw files not yet processed (tracked by content hash) and merging the new rows into the silver tables.
4. **Recalculates the affected features.** New observations or backfills mark the dates they touch. Every feature period that reads those dates (through its lookback window, predecessor or lifecycle alignment, or the reference history used for scaling) is recomputed, wherever it falls in the past; a Trends backfill for 2024, for example, recomputes the 2024 weeks and every later week whose window reaches back to them. A change to a parser, the catalogue, feature\_version or the config triggers a full rebuild instead.
5. **Regenerates MS and DP** for every week whose input features changed or whose scaling reference changed. Both are computed from the input features alone and never read earlier MS or DP values. Every stored value carries the feature\_version, config\_version and run\_id that produced it.
6. **Saves** the updated tables and run metadata: run\_id, start and end time, sources reached, rows added, failures, days since the previous run, and code and config versions.

Rows are keyed by source, listing or video id and fetch timestamp, so repeating a step or a whole run never duplicates records, and a run that fails midway can simply be started again. The most recent, still-open week is flagged is\_partial\_week until it closes.

**Finding the affected periods.** features/registry.yaml declares each feature's lookback and reference windows. A run marks the dates touched by new data, widens them forward by each feature's window (and, for scaling references, to every week that uses a changed reference), and recomputes exactly those periods. Most runs touch only recent weeks, a deep backfill touches more, and a full rebuild is the fallback rather than the default. Raw observations, deduplication and idempotence are unchanged; each recomputed value gets a new computed\_at, and gold rows carry source\_asof (the latest observation date per source used) so freshness is visible.

**First run.** A first run needs no earlier output. MS and DP are calculated whenever their evidence rules are met, using whatever history each source provides; there is no warm-up period tied to the number of runs. Historical gaps are recorded with their actual dates, and a score is reported as Insufficient Evidence where an essential input cannot be obtained.

### Fetching

- **Retries:** tenacity with exponential backoff on timeouts, 429 and 5xx; honour Retry-After; give up after N tries and log it.
- **Rate limits and quotas:** a per-source limiter (e.g. one request every few seconds per retailer) and a per-run quota ledger for YouTube units, so a run stops cleanly before exceeding the daily quota.
- **Pagination:** YouTube nextPageToken, Wayback CDX paging, GDELT date windows; persist the cursor so interrupted backfills resume in the next run.
- **Run log:** one row per fetch (run\_id, source, target, ts, http\_status, bytes, parse\_ok). This is what separates "fetch failed" from "listing gone".
- **Where it runs:** your own machine or notebook environment, started manually. Retailers may block cloud IP ranges, so test the host before relying on it (?).

### Standardising

- **Time:** store fetch timestamps in UTC plus an IST date. Weekly tables use Sunday–Saturday weeks: week\_start = date − ((weekday + 1) mod 7) days, with Python's weekday where Monday = 0.
- **Prices:** parse Indian digit grouping ("₹1,64,900" → 164900) to integer rupees; INR only; reject values outside a per-model plausible range into a review file.
- **Product identity:** the catalogue keyed by sku\_id = model | storage | colour, with price\_key = model | storage used for every price join. A listing is matched to a sku\_id when its page names the colour, otherwise to its price\_key only. Match listings by (1) rule-based extraction of brand, model, storage and colour from the title, then (2) rapidfuzz token\_set\_ratio against the alias table; ≥ 90 auto-accept, 75–90 to a manual review queue, below 75 reject. Once confirmed, store listing\_id → sku\_id so the listing never needs re-matching.
- **Exclusions:** refurbished or renewed, open-box, grey-import or international variants, bundles and accessory listings, filtered by title keywords and seller.
- **Duplicates:** raw keeps every fetch. For day-level views, keep the last successful fetch per retailer × listing × day. Where several sellers list the same SKU, keep all rows with seller, and define the retailer's price for that day as the lowest new-condition price from the featured or authorised seller.

### Missing vs zero

| Situation | Stored as |
| --- | --- |
| Fetch or parse failed | Price NA, with failure reason from the run log |
| Listing removed | is\_listed = false |
| Out of stock | in\_stock = false; any displayed price kept but flagged as not purchasable |
| Page parsed fine, no offers shown | offer count 0 (a real zero) |
| Trends value "<1" | 0.5, flagged; a plain 0 is a real low value only when the request succeeded |
| No new comments on a video | 0 only if that run's fetch succeeded |
| Dates between two runs | No row. Recorded in the gap log, never filled, interpolated or carried forward as a price |
| Colour evidence below its minimum volume | NA with the count n recorded, not zero |

### Aligning frequencies

Observations carry their fetch date, so nothing is forced onto a daily calendar. Weekly tables (Sunday–Saturday) aggregate whatever observations fall in the week (median, min, last value, share of observations in stock, maximum discount) and carry n\_obs, first\_obs and last\_obs so thin weeks are visible. Weekly-only series (long-window Trends) attach to their week. Slow series (MRP, duty changes) are forward-filled with an age\_days column; quarterly tracker figures keep their as-of date and are never interpolated.

**Financial series (AAPL, USD/INR).** Each observation keeps its own market\_date and an available\_ist\_date. AAPL trades on US hours, so a close dated D reaches India on D + 1 (the US close falls after midnight IST); a Friday close therefore lands on Saturday and counts in the week that ends that day. The Frankfurter reference rate is published around 16:00 CET on working days, so it is available the same IST evening. Weekly values use the last observation whose available\_ist\_date is on or before the Saturday ending the week, with age\_days stored. Weekends and market holidays have no observation: nothing is created for them, and a percentage change over k days compares the last available value at t with the last available value at or before t − k, storing both dates. AAPL uses the unadjusted close for levels and the adjusted close for returns. A missing or delayed feed gives NA with its age, never a silently carried-forward value.

**Trends stitching:** every request includes the anchor term "iPhone" with up to four other terms; rescale each request so the anchor matches a reference series, and average three pulls per window to damp sampling noise. If the official alpha is approved, its consistent scaling removes most of this.

### Curated outputs

- silver: price\_obs, offer\_obs, stock\_obs, review\_obs, colour\_obs, search\_interest, pageviews, video\_stats, text\_items, news\_counts, events, catalogue
- gold: weekly\_price\_key (model × storage), weekly\_model, weekly\_segment (competitor groups), weekly\_colour\_evidence, and the final weekly\_sku table carrying MS and DP; daily views only for dates with observations

## Feature engineering

Engineered variables fall into three groups: **A. input features** (collected observations, transformed), **B. previous-generation features** (two predecessor comparisons) and **C. derived targets** (Overall Market Sentiment and Demand Pressure). The final SKU table is assembled from all three at the end.

Each variable is calculated at the finest grain its evidence supports, then repeated across finer rows:

| Grain | Variables | Repeated across |
| --- | --- | --- |
| Model × storage (price\_key) | Prices, discounts, offers, storage-specific affordability, predecessor price gap | Colours |
| Model | Search interest, opinions, ratings, popularity, purchase intent, predecessor search ratio | Storage and colour |
| Segment | Android competitor-group features | All models in the segment |
| Market | Festive sales, events, financial context, news | All rows |
| Colour (sku\_id) | Colour-specific observations only: colour-level stock and delivery, colour-tagged ratings and reviews, colour mentions in comments, colour-query search share. Used for the colour adjustment, never to create colour prices | — |

In the section A tables, "SKU" means model × storage. Every feature is one generic column across generations, with model and generation only as row keys. Notation: P = advertised price, MRP = list price, I = search interest, t = day, k = lookback in days, w = weeks since India launch.

**Irregular observation dates.** Runs are on demand, so a feature that looks back k days uses the nearest observation at or before t − k within a tolerance (±3 days for k = 7, ±7 for k = 28, ±14 for k = 91) and is NA otherwise. Windowed statistics (volatility, promo intensity, rolling means) run over observations rather than calendar days, need a minimum observation count, and report n\_obs beside the value. A week with no observations is NA, not zero.

### A. Input features

### 1. Retail price dynamics

| Feature | Definition | Grain |
| --- | --- | --- |
| Price change | Δ\_k = ln P\_t − ln P\_(t−k), for k = 7, 28, 91 | SKU × retailer, SKU |
| Volatility | Standard deviation of log price changes between consecutive observations in the last 28 days (at least 4 observations) | SKU |
| Price vs launch | P\_t / P\_launch (India launch MRP) | SKU |
| Cross-retailer dispersion | (max − min) / median of P across retailers on day t | SKU |
| Price deviation | (P\_t − median\_90) / MAD\_90: robust z-score against the last 90 days | SKU |

### 2. Discounts and promotional intensity

| Feature | Definition | Grain |
| --- | --- | --- |
| Discount depth | d = 1 − P\_adv / MRP; d\_card = 1 − P\_card / MRP | SKU × retailer |
| Promo flag and duration | Promo active when d ≥ 5% or a bank offer exists; duration = days from the first observation of the current promo to the latest, flagged as a lower bound when observations are more than 7 days apart | SKU × retailer |
| Promo intensity | Share of observations in the last 28 days with a promo active, reported with n\_obs | SKU |
| Offer richness | Count of offers, max bank offer value, no-cost EMI available (0/1), max exchange bonus | SKU × retailer |

### 3. Relative iPhone vs Android pricing

| Feature | Definition | Grain |
| --- | --- | --- |
| Price gap | G = ln P\_ref − ln median(P\_group) | Segment |
| Relative discounting | R = d\_ref − median(d\_group) | Segment |
| Competitor launch pressure | Σ over group launches in the last 8 weeks of exp(−weeks since launch / 4) | Segment |
| Group price movement | 28-day change in median(P\_group) | Segment |

### 4. Search interest and purchase intent

| Feature | Definition | Grain |
| --- | --- | --- |
| Share of search | S\_m = I\_m / Σ\_j I\_j across in-scope iPhone models | Model |
| Search growth | ln(I\_t + 1) − ln(I\_(t−k) + 1), k = 7, 28 | Model |
| Intent share | Interest in intent queries (price, offer, EMI, buy, sale) / interest in all queries for the model | Model |
| iPhone vs Android attention | I\_segment / (I\_segment + I\_group) | Segment |

### 5. Popularity and sentiment

| Feature | Definition | Grain |
| --- | --- | --- |
| Popularity rank | Rank on Amazon.in and Flipkart best-seller lists and on Smartprix or 91mobiles popularity lists, and its 7-day change (popularity) | Model; storage where a listing is variant-level |
| Review velocity | New retailer reviews per week, all and verified-purchase only, with 4-week change; a lagged purchase proxy (purchase) | Model; storage where variant-tagged |
| Video view velocity | Views gained per day between observations, summed over the top N review videos per model (interest) | Model |
| Comment intent mix | Shares of comments labelled bought (purchase), considering and waiting (intent) | Model, weekly |
| Price sentiment | Share of price-related comments and reviews that are negative | Model, weekly |
| Switching ratio (experimental) | (Android→iPhone + 1) / (iPhone→Android + 1); computed but excluded from the scores by default | Model, weekly |

Retailer ratings and review text are collected where accessible and permitted. At model level: the review-count-weighted mean star rating across retailers, and the mean rating of reviews added in the last 4 weeks (retailers pool reviews across colours and usually storage). Review text goes through the same labelling step as video and forum comments (a small classifier or LLM prompt validated on about 500 hand-labelled Indian comments, including Hinglish). Where a review shows its colour or storage variant, it also feeds colour\_obs.

**Sentiment from reviews and comments is an intermediate feature.** Net sentiment is one input to Overall Market Sentiment; it is not the indicator itself.

**Evidence types.** Every feature is tagged with what it actually measures, since these are not interchangeable: *purchase* (self-reported "bought" comments, verified-purchase review velocity, "bought in past month" badges where shown), *intent* ("considering" or "waiting" comments, intent-query share), *interest* (search interest, pageviews, video views), *popularity* (retailer best-seller and popularity ranks) and *supply* (stock-outs, delivery times). Interest and popularity do not show that anyone bought a phone, and stated intent is not purchase.

**Switching and upgrade indicators are experimental.** Comments rarely say clearly that someone is leaving or joining a platform, and the labels are noisy. The switching ratio is computed and stored, but excluded from the scores by default until its labels have been checked against the hand-labelled set.

### 6. Stock availability and delivery

| Feature | Definition | Grain |
| --- | --- | --- |
| Out-of-stock share | Out-of-stock (SKU × retailer) pairs / listed pairs | Model |
| Delivery time | Median quoted delivery days across the pin-code panel, and its 7-day change | SKU, model |
| Apple store tightness | Apple India delivery estimate in days | SKU |

Availability is supply-side context, not a demand signal. A stock-out or longer delivery time can come from launch allocation, logistics or retailer inventory decisions as easily as from strong demand, so these features are stored and flagged, and count towards Demand Pressure only as corroboration (see C).

### 7. Product lifecycle

| Feature | Definition | Grain |
| --- | --- | --- |
| Lifecycle position | Days since India launch; successor launched (0/1) and days since successor launch; delisted by Apple (0/1) and days since delisting | Model |

### 8. Events, seasonality and market activity

| Feature | Definition | Grain |
| --- | --- | --- |
| Event flags | Festive sales (Diwali, Flipkart Big Billion Days, Amazon Great Indian Festival, Republic and Independence Day sales), Apple launches, Apple price changes, duty or GST changes, competitor launches | Day |
| Event response | For an event at day e: mean(x over e…e+7) / mean(x over e−14…e−1) − 1, for search, rank and comment volume | Model × event |
| Financial context | AAPL: close and its 7- and 28-day percentage change. USD/INR: level and 7- and 28-day percentage change. Each carries market\_date and age\_days. Supplementary context only: no weight in MS or DP, and no assumption that either moves iPhone demand in India | Day |
| News | GDELT article count and average tone for iPhone price and launch stories | Day |

The event-response feature is how consumer reactions to price moves get measured: the Sep 2026 price increases on the 17, Air and 17e are the first events to run it on.

### 9. Colour-specific observations

Kept in colour\_obs at their own grain (model × colour, or model × storage × colour where a source shows both). They feed only the colour adjustment in section C, and each stays in its own column so other scoring methods can be tried later.

| Feature | Definition | Source |
| --- | --- | --- |
| Colour search share | a\_c = interest in "\[model\] \[colour\]" queries / sum over the model's colours, 4-week mean; equal share is 1/n for n colours. Pulled in one Trends request so the series share a scale; likely sparse for less popular colours (?) | Google Trends |
| Colour mention share | m\_c = comments and reviews mentioning colour c / all colour-mentioning comments and reviews for the model, 8-week window | YouTube, forums, review text |
| Colour comment sentiment | Net sentiment of items mentioning colour c minus the model's overall net sentiment | Same |
| Colour rating delta | Mean rating of reviews tagged colour c minus the model's mean rating, 12-week window; needs at least 30 tagged reviews (variant label shown on reviews, ?) | Retailer reviews |
| Colour stock and delivery | In-stock share and median delivery days by colour, where a retailer lists colours separately | Retailers, Apple India |
| Colour-specific promotion | Recorded only where a retailer actually runs a colour-specific offer; otherwise none | Retailers |

Below the minimum volumes a value is NA with the count n recorded. Internal order quantities are never used to infer colour preference.

### B. Previous-generation features

**Mapping (in the catalogue).** Each current model × storage maps to its predecessor by tier and storage, never by colour:

| Current | Predecessor | mapping\_type | Predecessor status |
| --- | --- | --- | --- |
| 18 Pro, 18 Pro Max | 17 Pro, 17 Pro Max | exact | active |
| 17 | 16 (base) | exact | active |
| 17 Pro, 17 Pro Max | 16 Pro, 16 Pro Max | exact | reference-only |
| 17e | 16e | exact | reference-only |
| 16 (base) | 15 (base) | exact | active |
| 15 (base) | 14 (base) | exact | reference-only |
| Air | none | none | no like-for-like predecessor |

Storage must match exactly. Examples: 18 Pro Max 2TB → 17 Pro Max 2TB (exact); 18 Pro 2TB → none, because the 17 Pro tops out at 1TB; 17 256GB → 16 256GB (exact); the 16 128GB has no successor with that capacity. If a predecessor never offered a capacity, mapping\_type is `none` and the predecessor features are NA; no neighbouring capacity is substituted. An equivalent mapping is allowed only where the justification is written into the catalogue.

**Selected features (two):**

| Feature | Definition | Grain | Interpretation |
| --- | --- | --- | --- |
| B1. Same-date predecessor price gap | gap\_same(t) = ln P\_cur(t) − ln P\_prev(t), both the weekly median advertised price across retailers; defined only while both are on sale | Model × storage | How much extra the new model costs over its predecessor on the same shelf. In India older models are discounted hard after a launch, so this is the main within-Apple substitution choice |
| B2. Lifecycle-aligned search ratio | r\_life(w) = I\_cur(w) / I\_prev(w), trailing 3-week mean, with w = weeks since each model's India launch. Both terms are pulled in the same Trends request so they share one scale | Model | Whether the new model draws more or less attention than its predecessor did at the same point in its life |

**Why these two, and what was dropped:**

- **Predecessor retail price at the same lifecycle stage** was considered and dropped. Street prices for the 14, 15 and 16 cycles are largely unrecoverable, so a lifecycle-aligned price would mostly fall back to launch MRP, a constant. The launch MRP ratio (P\_launch,cur / P\_launch,prev) is kept as a static catalogue attribute instead.
- **Search growth vs search level ratio:** growth on both sides is a difference of two noisy series; a level ratio from a single request is more stable. Trends' \~5-year window reaches back to late 2021, enough for every pair including 14 → 15.
- **Both comparison types are kept** because they answer different questions: B1 is a same-week shelf comparison and exists only while both models are on sale (prospective logs plus Wayback); B2 is a momentum comparison and exists for every generation. Neither is redundant with the other.

Missing predecessor values stay NA with a reason code (no mapping, predecessor not on sale, no history); nothing is imputed.

**Reference-only predecessors** (14 base, 16e, 16 Pro, 16 Pro Max) are collected only for these two features: launch MRP, Trends interest and retail prices. For pairs whose predecessor Apple has delisted, B1 will often be NA, because it needs both models on a retailer shelf in the same week; B2 needs only Trends history. The Air has no like-for-like predecessor, so its mapping is none. The earlier Air → 16 Plus mapping was dropped: the 16 Plus is out of scope and sits in a different price tier.

### C. Derived targets

Both targets are constructed analytical indicators, computed weekly. They are not observed labels, statistically calibrated predictions, end-consumer sales, sell-through or forecasts of order quantities, and no figure derived from them should be read as a percentage change in demand. They are kept distinct by design:

|  | Overall Market Sentiment (MS) | Demand Pressure (DP) |
| --- | --- | --- |
| Question | How does the market currently regard this product? | Is purchase-related activity strengthening or weakening? |
| Built from | Levels of evaluation: opinion, ratings, perceived value, standing | Changes in behaviour: purchase and intent evidence, attention momentum, retailer popularity, offer response, competition; availability only as corroboration |
| Output | Score −1 to +1; Positive / Neutral / Negative / Insufficient Evidence | Index −1 to +1; Increasing / Stable / Decreasing / Insufficient Evidence; strength; evidence fields |

So a well-liked model with falling interest scores high MS and negative DP, and a model whose price draws complaints while purchase and intent evidence keeps rising scores low MS and positive DP. The overlap is limited to search, used as a level in MS and as a change in DP.

**Component scaling (both targets).** Each component x becomes a score s = clip(z / 3, −1, 1), with robust z = (x − median\_ref) / (1.4826 · MAD\_ref). The reference is a set of observed values of that same feature: the pooled weekly values of the in-scope models over the trailing 104 weeks ending at the scored week, restricted to a comparable lifecycle band for features that decay with product age. It is built from market observations only, never from earlier scores. Components are equally weighted at first, with weights stored in a config file so they can be revisited after exploratory analysis.

**Not autoregressive.** MS and DP are calculated independently from the available external features. Computing a week's score never reads earlier MS or DP values, so both can be produced on the very first run and rebuilt at any time from raw observations. History enters only as observed market data: lookback changes, rolling statistics, lifecycle alignment and the reference distributions above. These are inputs, not previous scores.

**Numerical safeguards.** Fallbacks are deliberately simple, and where evidence is inadequate they remove the component or the score instead of inventing one.

| Situation | Fallback |
| --- | --- |
| MAD zero or near zero (below the feature's floor ε\_f) | Use the scaled IQR (IQR / 1.349) if it is above ε\_f; otherwise treat the feature as constant. A constant feature gets no score: the component is marked unavailable (constant\_feature) and left out, not set to 0, because no variation means no evidence either way |
| Too few reference observations (fewer than 20 values over at least 8 distinct weeks) | Widen the reference, first to the pooled values of all in-scope models and lifecycle stages, then to the full trailing 104 weeks. If still short, the component is unavailable (short\_reference). No default scale is invented |
| Coverage varies across models | The reference is pooled across in-scope models, so a model with a short history is judged against the market's distribution of that feature rather than its own. Each row reports n\_obs, and the evidence fields show the resulting coverage |
| Lifecycle stages not comparable | Features that decay with product age (search interest, review velocity, discount depth, ranks) use reference values from the same lifecycle band (weeks since India launch ± 3). If the band is too thin, widen to ± 6 and then ± 12 weeks; if still thin, the component is unavailable rather than comparing a launch week with a year-old model. B2 is already lifecycle-aligned and needs no band |
| Missing or stale input | A missing value makes the component unavailable. A value older than its maximum age (set per source in the config, for example retail observations 14 days, Trends 21 days, comments 28 days) is treated as missing. Stale values are never carried forward into a score |
| Too few components | Weights are renormalised over the available components only when the existing coverage rules are met (MS: at least 3 of 4 components; DP: coverage ≥ 0.5 and a purchase- or intent-type component). Otherwise the result is Insufficient Evidence, with no numerical score |
| Zero or undefined values | A ratio with a zero denominator, or a log of a zero share, is NA rather than ±∞ or a patched value; count-based changes keep the +1 smoothing already defined |
| Sparse colour evidence | No adjustment: adj = 0 and colour\_evidence = none. A missing colour is never imputed from its siblings |

Component weights, thresholds, minimum evidence volumes, reference windows, staleness limits, the floors ε\_f and the colour cap all live in config/weights.yaml and are provisional until real data has been examined.

**Overall Market Sentiment components**

| Component | Input features | Grain | Higher means |
| --- | --- | --- | --- |
| Consumer opinion | Net sentiment (positive minus negative share) of YouTube and forum comments and retailer review text; an intermediate feature, not the target itself | Model | More favourable discussion |
| Ratings | Review-weighted retailer rating and the rating of reviews from the last 4 weeks | Model | Better buyer ratings |
| Perceived value | Price-sentiment net score (model), combined with the price gap vs the Android group relative to that gap's own history (model × storage) | Model × storage | Price seen as more reasonable |
| Market standing | Share-of-search level and popularity-rank percentile among in-scope models | Model | Stronger standing |

MS = mean of the available component scores. Positive if MS ≥ +0.25, Negative if MS ≤ −0.25, otherwise Neutral; these are starting thresholds. Insufficient Evidence if fewer than 3 of the 4 components are available, or if neither consumer opinion nor ratings is.

**Demand Pressure components** (changes over the last 4 weeks vs the 4 before)

| Component | Input features | Evidence type | Grain | Higher means |
| --- | --- | --- | --- | --- |
| Intent momentum | Change in intent-query share; change in "considering" and "waiting" comment share | intent | Model | Rising stated purchase intent |
| Purchase evidence | Change in "bought" comment share; growth in verified-purchase review velocity; change in "bought in past month" badge where shown | purchase | Model; storage where variant-tagged | More self-reported or retailer-visible purchases |
| Attention momentum | Change in B2 (r\_life), so normal post-launch decay is not read as weakening | interest | Model | Attention holding up better than the predecessor's did |
| Retailer popularity | Change in best-seller or popularity-rank percentile on Amazon.in, Flipkart, Smartprix and 91mobiles | popularity | Model; storage where the listing is variant-level | Rising retailer popularity |
| Offer response | Event response of search, rank and review velocity to a promotion or price cut in the window; NA when no such event | mixed | Model × storage | Offers drawing a response |
| Competitive pressure | Negative of the change in relative discounting R and in Android group price | competition | Segment | Android competition easing |
| Availability (corroboration only) | Rise in out-of-stock share or delivery days; excluded at launch and around known supply events | supply | Model × storage | See availability rule |
| Switching and upgrade (experimental) | Change in switching ratio | intent | Model | Weight 0 by default |

DP is the weighted mean of the available component scores (equal weights, set in the config file; switching weight 0 by default). Increasing if DP ≥ +0.2, Decreasing if DP ≤ −0.2, otherwise Stable. Strength = |DP|.

**Availability rule.** Stock and delivery do not measure demand by themselves. The availability component is added only as corroboration: when at least one intent, purchase or popularity component is positive and tightness is rising, it enters at half weight. Otherwise it is left out of DP and reported separately as supply\_flag (tight, normal or unknown) so a reader can see it. Launch-week allocation and known supply disruptions from the events table are excluded from tightness altogether.

**Interest alone never decides direction.** DP needs at least one purchase- or intent-type component. If every available component is interest- or popularity-type, the result is Insufficient Evidence, not Increasing or Decreasing.

A price change on its own is never a component of either target, and neither is a stock-out or a longer delivery time. A cut affects DP only through an observed response (offer response, purchase and intent evidence) and MS only through perceived value and opinion.

**Evidence fields (both targets),** kept separate because they measure different things:

| Field | Definition | Measures |
| --- | --- | --- |
| coverage | Available component weight / total weight | How much data there is |
| source\_reliability | Weight-averaged source tier (Tier A = 1.0, Tier B = 0.6) | Quality of the inputs |
| agreement | Share of available components whose sign matches the overall score | Confidence in the interpretation |
| evidence\_mix | Share of component weight by evidence type (purchase, intent, interest, popularity, supply, competition) | What kind of evidence the score rests on |
| supply\_flag | DP only: tight, normal or unknown | Supply context, kept out of the score |

DP is Insufficient Evidence when coverage < 0.5, when no purchase- or intent-type component is available, or when agreement < 0.5 with |DP| < 0.4 (contradictory evidence). MS follows the rule above. An Insufficient Evidence result is reported as such, never as Neutral or Stable.

**Calculation grain of the targets**

| Target | Baseline computed at | Varies by storage through | Varies by colour |
| --- | --- | --- | --- |
| MS | Model × storage | Perceived value | Only through the colour adjustment, when its evidence thresholds are met |
| DP | Model × storage | Offer response, corroborating availability, storage-tagged purchase evidence | Only through the colour adjustment |

Storage-level targets are justified only because price and availability genuinely differ by capacity (the 18 Pro Max ranges from ₹1,79,900 to ₹3,29,900 across storage options). Opinion and attention do not, so they stay model-level. When a model × storage row lacks its storage-specific inputs, the target is computed from model-level components only and flagged grain\_used = model.

### Colour adjustment

Final scores are a **shared model × storage baseline plus an evidence-based colour adjustment**. The baseline comes from the components above. A colour is adjusted only when its own evidence is strong enough; otherwise every colour of that model × storage carries the baseline unchanged, and the row says so.

**Evidence needed** (all must hold for a colour to be adjusted):

- At least two independent colour-evidence sources (for example colour search share and colour mentions, or colour-tagged reviews and comments).
- Minimum volumes: at least 30 colour-mentioning comments or reviews in the trailing 8 weeks, and 30 colour-tagged reviews in 12 weeks for the rating delta.
- At least three colours of the model with data, so a colour can be compared with its siblings.
- A baseline that is not Insufficient Evidence.

**Relative scores**, each in \[−1, 1\], compared with the model's other colours:

- Share-type evidence (search share, mention share): r = clip(ln(n · share\_c) / ln 2, −1, 1), so double the equal share scores +1 and half scores −1.
- Rating delta: r = clip(Δstars / 0.5, −1, 1). Sentiment delta: r = clip(Δnet sentiment / 0.4, −1, 1).
- MS uses the colour sentiment delta, rating delta and search share. DP uses the 4-week change in colour search share and in the colour's share of purchase- and intent-type mentions. Colour stock never adjusts DP.

**Adjustment.** adj\_c = 0.15 × mean of the available r, so it never moves a score by more than ±0.15; score\_c = clip(baseline + adj\_c, −1, 1), and the category is assigned from the adjusted score. Stored columns: ms\_base, ms\_colour\_adj, ms; dp\_base, dp\_colour\_adj, dp; colour\_evidence (none, partial or sufficient), n\_colour\_sources, grain\_used.

The weights, cap and minimum volumes sit in the config file and are expected to change once real colour evidence has been examined. Colour observations stay in colour\_obs, independent of this method, so a different scoring method can replace it later. Most rows are expected to carry the shared baseline.

### Building the final SKU table

1. Spine: every active sku\_id × week, from its India launch week until the model is delisted at all tracked retailers. Reference-only models are not included.
2. Join model × storage features on price\_key, model features on model\_key, segment features on segment, and market features on week\_start.
3. Join colour evidence (colour\_obs aggregates) on sku\_id. Leave NA where not observed instead of copying another colour's value.
4. Join B features (B1 on price\_key, B2 on model\_key), attach the baseline targets, and apply the colour adjustment, producing ms, dp, their categories and the evidence fields.

Apart from the colour adjustment, which is applied here from stored baselines and colour aggregates, this step is joins only. No internal order data is joined. Weeks before the first run have no retail observations: their rows carry only archive-based columns (Trends, pageviews, MRP history) and Insufficient Evidence targets.

### Traceability

All feature and target logic lives in features/\*.py, one function per variable. A registry (features/registry.yaml) records for every column: group (A, B or C), evidence type, source tables, formula, calculation grain, lookback period, interpretation and source tier. Gold rows carry computed\_at, run\_id, feature\_version and the input tables used, so every value can be traced back to raw files.

## Signal checks and exploratory analysis

This replaces the earlier modeling and validation section. The aim is to confirm the data is trustworthy and to describe market behaviour, not to predict quantities.

### Data quality checks (after every build)

| Check | Definition | Action when it fails |
| --- | --- | --- |
| Catalogue validity | Every observed listing maps to an active or reference sku\_id or price\_key; unmatched colour or storage combinations are listed | Review queue; add an alias or a catalogue row |
| Coverage per run | Listings with a parsed observation / listings attempted, per retailer | Investigate the collector or parser for that retailer |
| Run gaps | Days between consecutive runs per source; gaps over 7 days flagged | Recorded in the gap log; weekly rows show n\_obs; nothing is filled |
| Parse failure rate | Failed parses / fetches, per source per run | Usually a layout change: fix the parser and replay raw |
| Match rate | Listings matched to a sku\_id or price\_key / all listings | Add aliases from the review queue |
| Price sanity | Prices outside the per-model plausible range, or moves above 30% between consecutive observations | Review file; keep the row but flag it |
| Staleness | Days since the last successful run per source | Reported in the run metadata |

### Cross-source consistency

- Retailer MRP against Apple India MRP for the same SKU.
- Wayback-recovered prices against live scrapes over overlapping weeks (and Keepa, if a trial is taken).
- Direction agreement between Google Trends, Wikipedia pageviews and YouTube views around launches. Large disagreements point to a collection problem or a source-specific audience effect.

### Checks on the derived targets

- **Distinctness:** rolling correlation between MS and DP across rows. If |corr| stays above 0.8 for a quarter, the two are not carrying distinct information and their components need revisiting.
- **Insufficient Evidence share** per model and week, so thin coverage is visible rather than hidden behind neutral scores.
- **Known-event sanity:** inspect both targets around launch weeks, festive sales and the Sep 2026 price increases. If they look wrong, inspect the components rather than tune thresholds to fit.
- **Threshold sensitivity:** share of rows that change category when thresholds move by ±0.05.
- **Colour adjustment:** share of rows adjusted and the distribution of adjustments, confirming none exceeds ±0.15.

### Exploratory methods

- **Lifecycle curves:** price, discount and search interest plotted against days since India launch, overlaid across generations.
- **Event studies:** behaviour in windows around festive sales, Apple launches, the Sep 2026 price increases and major competitor launches, using the event-response feature.
- **Rolling and lagged correlations** between price/promo features and interest/popularity features, reported with their sign and how stable that sign is across generations.
- **Anomaly detection:** robust z-scores (median and MAD) on prices, discounts and interest, to flag unusual market moves and data errors alike.
- **Basic text classification:** intent and price-sentiment labels on comments, checked against the hand-labelled set for accuracy before use.

No assumption is built in that higher prices lower demand or that more searches mean more sales; relationships are measured and reported as observed, including when deep discounts produce little response.

## Implementation sequence

In order. Nothing runs on a schedule, so the most useful early step is to finish the catalogue and the test fetches and make the first extraction run: retail prices, offers, stock and delivery can only be captured when a run happens, and each run is a dated snapshot.

1. **Finalise the independent catalogue and active-SKU list**
   - Build catalogue/products.csv for every active model × storage × colour from Apple India's configurator and spec pages; confirm the two unverified families (16 and 15 base: storage options and colours).
   - Add predecessor mappings with mapping\_type, the reference-only rows (14 base, 16e, 16 Pro, 16 Pro Max) and config/active\_scope.yaml.
   - List candidate Android models per competitor group, with spec attributes and Indian launch prices.
2. **Verify source access and historical coverage**
   - For each retailer, read robots.txt and terms, then do one manual test fetch and parse. Drop any site that prohibits automated access, and collect review text only where terms permit.
   - Apply for the Google Trends API alpha; create a YouTube Data API key; test trendspyg in the meantime.
   - Reddit: new public API access requests closed on 31 Oct 2026, so skip it unless access was already approved.
   - Decide whether a one-month Keepa trial is worth it for Amazon.in price history.
3. **Run extraction (APIs and permitted scraping)**
   - First run as soon as the catalogue and test fetches are ready: Apple India, Amazon.in, Flipkart, Croma, Reliance Digital, Vijay Sales, and Smartprix/91mobiles rankings, for iPhones and Android candidates, including ratings, review text and colour-level listings. Retail history is only what runs capture, so early runs matter most.
   - Backfill in the same runs where possible: Wayback snapshots, Google Trends (\~5 years, geo IN) including paired current-vs-predecessor requests for B2 and colour queries, Wikipedia pageviews, YouTube comments for the active and reference models, GDELT, AAPL and USD/INR history.
   - Build events.csv by hand: Indian launch and sale dates, festive sale windows, Apple price changes and delistings, duty changes, competitor launches.
   - Run again whenever fresh data matters (launches, festive sales, announced price changes).
4. **Clean, standardise and curate**
   - Parsers to bronze, matching to sku\_id or price\_key with the review queue, the missing-vs-zero rules, then silver tables and the quality checks.
5. **Engineer features**
   - Price and discount features first, then competitor-group, search and intent, ratings and reviews, lifecycle and events; stock and delivery as context; colour-specific observations; then the two predecessor features (B2 from Trends history first, B1 from logs and Wayback).
6. **Construct MS and DP** as separate indicators
   - Baselines at model × storage, colour adjustments where evidence allows, evidence fields and Insufficient Evidence where the rules require it; then assemble the final SKU table.
7. **Exploratory analysis and interpretation, later**
   - The exploratory work and target checks above and deeper market research, decided once steps 1–6 are in place.

## Limitations

- **Retail history is mostly lost.** Offers, stock and most past selling prices for the 15 and 16 cycles cannot be recovered for free; historical work on those models leans on MRP, Trends, Wikipedia, YouTube and news.
- **Collection is on demand.** Observations exist only for the dates a run captured them. Temporary promotions, delivery estimates and stock between runs are not recoverable and are not filled or assumed; gaps are recorded and weekly values show how many observations support them.
- **Weeks before the first run** carry only archive-based columns, so their targets are mostly Insufficient Evidence.
- **The indicators are constructed, not measured.** MS and DP describe observable market conditions. They are not sales, sell-through or order forecasts, and the distributor's data (upstream orders to Apple) says nothing about consumer sell-through or partner inventory either.
- **Colour evidence is thin.** Many colour-level signals will fall below the minimum volumes, so most rows will carry the shared model × storage baseline.
- **Scrapers are fragile.** Layout changes and anti-bot measures will break parsers; the immutable raw layer means a fix can be replayed rather than data lost.
- **Search data is relative.** Trends returns normalised, sampled interest, and the free client is unofficial and may break.
- **Audience skew.** YouTube and forum commenters skew urban and English-speaking, and Wikipedia pageviews are global, not Indian.
- **Offer parsing is imperfect.** Caps, eligibility rules and stacked offers are written inconsistently; keeping raw text allows re-parsing.
- **Terms of service.** Each scraped site needs a check before collection and periodically after.

## Sources

- [Outlook Business: iPhone 18 Pro and Pro Max India availability](https://www.outlookbusiness.com/corporate/apple-iphone-18-pro-iphone-18-pro-max-to-be-available-in-india-from-sep-18)
- [91mobiles: iPhone 18 Pro storage and prices in India](https://www.91mobiles.com/hub/iphone-18-pro-goes-on-sale-india-price-launch-offers-availability/amp/)
- [Croma: iPhone 17 series prices in India](https://www.croma.com/unboxed/iphone-17-iphone-17-pro-prices-in-india)
- [Croma: iPhone Air price in India](https://www.croma.com/unboxed/iphone-air-price-in-india)
- [Business Standard: iPhone 17e India launch](https://www.business-standard.com/technology/gadgets/apple-iphone-17e-launched-price-in-india-specs-features-availability-126030300257_1.html)
- [Business Today: iPhone 17, Air and 17e price increases in India](https://www.businesstoday.in/technology/news/story/iphone-17-iphone-air-17e-get-costlier-in-india-after-apple-event-check-new-prices-554418-2026-09-10)
- [Deccan Chronicle: Apple price increases by model and storage](https://www.deccanchronicle.com/technology/apple-hikes-iphone-prices-in-india-iphone-16-17e-17-and-air-get-costlier-1986266)
- [Gizbot: Apple removes the iPhone 17 Pro and 17 Pro Max](https://www.gizbot.com/mobile/news/apple-discontinues-iphone-17-pro-17-pro-max-after-iphone-18-pro-launch-128463.html)
- [Gizbot: iPhone 16 Pro, 16 Pro Max, 15 and 15 Plus discontinued in India](https://www.gizbot.com/amphtml/mobile/news/iphone-16-pro-pro-max-iphone-15-models-discontinued-in-india-011-118589.html)
- [PPC Land: Google Trends API alpha](https://ppc.land/google-opens-alpha-testing-for-new-trends-api-targeting-developers-and-journalists/)
- [ScrapeGraphAI: pytrends archived](https://scrapegraphai.com/blog/google-trends-api)
- [Serpent API: Reddit free API status in 2026](https://apiserpent.com/blog/free-reddit-api)
- [Amazon: PA-API 5 deprecation notice](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/paapiv5-deprecation)
- [RevenueGeeks: Keepa API pricing](https://revenuegeeks.com/software/keepa/api)
- [Postproxy: X API pricing 2026](https://www.postproxy.dev/blog/x-api-pricing-2026/)

* [Frankfurter: free exchange-rate API (central-bank reference rates)](https://frankfurter.app/docs)
