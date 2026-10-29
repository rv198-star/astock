# Maintained astock source library

This public fork maintains a consumer-independent Python source library alongside
the original a-stock-data skill. Its initial upstream baseline is
`simonlin1212/a-stock-data@cb57c7aba720380b48a11dd065c6db57a2c39db9` (SKILL 3.10.3).
The library has its own version, currently 0.1.4. The original skill version and
the library version are different identities.

## Scope and adapters

`astock` owns bounded source requests, explicit source identity, raw response
evidence, parsing and clearly reported errors. Consumers own warehouse publication,
historical PIT admission, task scheduling, policies and trading decisions. The
library imports no consumer package, writes no warehouse and launches no timers.

The maintained contracts enumerate 21 default requests across these adapters:

| Capability | Actual backend | Use ceiling |
| --- | --- | --- |
| `astock.lpr` | ChinaMoney `LprHis`, HTTPS POST | Source-observed LPR rates with effective dates; no inferred publication clock |
| `astock.rss` | Configured RSS/Atom publisher; default CNBC public feed | News discovery with optional publisher-provided, timezone-aware clocks |
| `astock.quotes` | Tencent, Sina and Eastmoney single-security snapshots | Native-price diagnostics, explicit venue and unknown adjustment basis; no suspension or fill inference |
| `astock.macro` | Eastmoney CPI, PPI, PMI, GDP and M2 | Current-vintage, named numeric source fields; report period text is not a release clock |
| `astock.bonds` | ChinaBond identified treasury maturity curve | Exact curve ID/name and source date; native maturity/yield pairs |
| `astock.disclosures` | CNINFO HTTPS announcement index | Index metadata and exact millisecond timestamp; no attachment/body retrieval |
| `astock.news` | Sina roll channels 2516 and 2510 | Feed metadata and optional creation epoch; no regulatory-authority or freshness claim |
| `astock.funds` | Eastmoney historical NAV, two rows for one explicitly requested fund by default | Native unit/accumulated NAV, daily change percent, valuation date and actual SGZT/SHZT status fields; currency requires fund metadata |
| `astock.announcements` | Current Eastmoney `/api/security/ann`, two stock-specific records | Source notice-date label and original display/production time text; no completeness, recency or historical publication claim |
| `astock.etf_flow` | Eastmoney one explicitly identified mainland ETF | Signed vendor-classified secondary-market trading flows and percentages; not subscription/redemption flow or verified investor-position change |
| `astock.convertibles` | Jisilu current public `/webapi/cb/list/`, anonymous subset capped at 30 records | Anonymous partial coverage, separate convertible/exchangeable types, reference prices and optional time text; full-list login is not attempted |
| `astock.futures` | Sina one named dated PVC contract | Contract-price diagnostics, independent date/time labels; exchange listing, trading-day and quantity admission remain the caller's responsibility |
| `astock.a_shares` | Eastmoney one security's bounded margin window and one A-share block-trade date | First page only; source-native amounts, shares and fractional premium, explicit session labels and reported total/page counts |

ChinaMoney is an additional backend to the original skill's Eastmoney LPR helper.
It is not an automatic fallback disguised as the same provider. Duplicate endpoints
and wrapper aliases do not become independent sources.

These interface leads came from `cn-financial-scraper` 1.0.51 (SkillHub coordinate
`@user_9d5a2a39/cnfinancialscraper`, skill document 12.0.0). Its delivered README
declares MIT, while the inspected snapshot lacks a separate license text and a
verified public source repository. No code from that snapshot is copied here;
these are independent implementations of the public interfaces. Original upstream
a-stock-data code, license and history remain intact.

## Evidence contract

`RawObservation` retains exact response bytes/SHA256, request identity and a
timezone-aware acquisition clock. Request identity covers provider, capability,
method, full URL, body hash and declared headers. It is an in-request identity,
not a sufficient cross-job warehouse/cache key.

`FetchResult` separates `SUCCESS` (nonempty parsed records), `EMPTY` (a valid source
schema explicitly containing no records) and `FAILED`. Transport errors, truncated
responses, unexpected schemas, missing rates and mismatched source identity cannot
be labelled successful. No adapter silently substitutes another vendor.

LPR values retain percent units as Decimal and their source effective date. That
date is not treated as a release timestamp. RSS preserves original publication text;
missing, unrecognized or timezone-free times remain unknown. Acquisition time never
fills a missing publication time. A successful parse does not grant historical PIT
or whole-vendor/whole-universe acceptance.

Macro, curve and quote records label values `SOURCE_NATIVE_UNNORMALIZED`. Consumers
must establish field units/basis before numerical integration. No series is silently
rebased, rescaled or adjusted. An absent Eastmoney quote clock remains unknown.
CNINFO's source timestamp remains an integer in milliseconds, including values later
than acquisition; it is not asserted to be an exact publication or knowledge clock.
The disclosure request is a bounded broad index search, not a verified security or
exchange filter. Sina's channel 2510 can return old items; successful retrieval says
nothing about current-policy coverage. The raw envelope retains fields not projected
into the typed records. A malformed item rejects the response rather than dropping
bad records and reporting a misleading partial success.

The HTTPS transport disables ambient proxies, retries and redirects, uses a 3-second
connect/5-second read timeout, and caps retained bodies at 256 KiB by default. It
checks a 12-second body-read budget between chunks. DNS resolution and an active
socket read are not a hard end-to-end deadline. Callers must bound overall jobs.
TLS verification remains enabled. Credentials and payloads belong outside Git.

## Use from a pinned checkout or package

```python
from astock import lpr
from astock.transport import fetch

raw = fetch(lpr.request(page_size=2))
result = lpr.parse(raw)
print(result.status, result.reason)
```

For RSS, use `rss.request(provider="cnbc", url=rss.CNBC_URL)` and `rss.parse(raw)`.
`astock.capabilities()` enumerates the 19 default source requests without network
access; it is an interface registry, not an admission or availability registry.
Parsing can be replayed from retained observations without network access.
Consumers should pin an exact commit or built package digest, rather than install
`main`/`latest` during a running job. No consumer-specific path is embedded here.

Fund NAV identity is request-bound because the usual response does not echo the
fund code. An echoed conflicting code rejects the response. Pagination counts,
valuation dates and finite Decimal values are checked; invalid values never become
zero. The source's `SGZT`/`SHZT` fields supply subscription/redemption status.
Neither that status nor a valuation date establishes trade execution or publication
time. NAV currency and accumulation interpretation remain the consumer's contract.

The current announcement route replaces the older `/security/announcement` lead;
they are different request contracts, not an automatic retry/fallback. A valid old
notice can support archival metadata while failing a current-coverage use. Source
notice dates and native millisecond clock text do not define a knowledge interval.

ETF flow identity includes the exact security and venue; the request contains one
`secids` value instead of a changing market ranking. Native field `f62` is the
vendor's main-order net trading flow; `f66/f72/f78/f84` retain its size buckets.
Monetary scale and percent-to-ratio normalization belong to the consuming contract.
The unqualified total-market-value field from the original lead is omitted.

Jisilu's anonymous response explicitly limits coverage. The parser retains that
prompt and distinguishes C convertibles from E exchangeables, without asserting a
complete bond universe. Its `info.date` and each row's optional `last_time` remain
separate: combining them can manufacture a future quote time around midnight.
Missing listing dates are unknown, not proof of trading/listing status. Reference
prices supply neither a transaction nor a fill. The caller must qualify monetary
units separately for each instrument type; support for E metadata is no numerical
admission of exchangeable bonds. No login, cookies, hidden fields or paywall bypass
are used by this adapter.

## Bounded A-share samples (0.1.4)

`a_shares.margin_request(code, start=..., end=..., limit=2)` selects one SH/SZ
A-share over at most 31 calendar days. `block_request(trade_date, limit=2)` selects
one A-share disclosure date. Both request page 1, cap a caller's limit at 20, retain
the source's reported total/pages, and never fetch the remaining pages. Default
dates are frozen examples, not a rolling latest-session or complete-market feed.
Parsing requires the same exact query and headers, matching security/venue and
session scope, finite exact Decimal numbers and internally consistent margin
totals. Missing numbers remain failures; valid zero and signed net flows survive.
Reported block-trade amounts can differ from price times shares; retain the native
amount rather than reconstructing it. Consumers disclose or isolate that discrepancy
according to purpose; no rounding explanation is inferred.

The publisher's [margin script](https://data.eastmoney.com/newstatic/js/rzrq/stock.js)
labels balances/buy/repay/net amounts in yuan and stock-lending quantities in shares.
The source's `RZRQYECZ` is a balance difference, not a day-to-day balance change;
it remains unqualified metadata and is excluded from numeric metrics. The
[block-trade table](https://data.eastmoney.com/dzjy/dzjy_mrmx.html) scales native
`DEAL_VOLUME`/`DEAL_AMT` by 10^-4 for display in ten-thousand shares/yuan and scales
`PREMIUM_RATIO` by 100 for percent display. The parser retains API values without
these display conversions. Its vendor daily rank is not an exchange trade ID.

Session-date labels are not publication, historical knowledge or execution times.
Raw acquisition remains separately auditable. There is no assertion of the most
recent session, complete pagination, exchange-independent verification, adjusted
prices, trader identity, or a consumer's fill. Consumers qualify canonical units,
purpose, dates, freshness and historical PIT independently.

## Maintenance and checks

`upstream` points to the original project; `origin` points to this fork. Review
upstream changes on a branch and merge applicable changes with test evidence.
Do not overwrite maintained modules by regenerating them from SKILL.md at runtime.
Preserve the original license/attribution and record newly copied code's provenance.

```bash
make check
make check-upstream
```

Create a separate Python 3.10+ virtual environment and install the build pins from
`requirements-build.txt`, then install `.[upstream-test]` for the retained example
tests. The maintained library needs only its declared `requests` dependency. Existing
consumer environments need not be modified. Build outside the checkout when desired:

```bash
SOURCE_DATE_EPOCH=1793232000 make build PYTHON=/path/to/venv/bin/python DIST_DIR=/path/to/output
```

For a reproducibility check, build twice with the same source tree, build dependency
closure and `SOURCE_DATE_EPOCH`; compare the wheel SHA256 and test an installed wheel
from outside the checkout. The source archive also retains the original upstream
skill/examples; wheel imports expose only the maintained `astock` package.

`check` runs the maintained library's offline synthetic contracts. `check-upstream`
also runs the retained original tests and needs their optional spreadsheet clients
(including openpyxl). Live upstream tests remain opt-in. Report these checks
separately; a pass of new-library contracts is not a full upstream compatibility pass.

## PVC futures price snapshot (0.1.3)

`astock.futures.request("V2701")` requests exactly one dated PVC contract via Sina
HTTPS with a public Referer. `parse(raw, contract="V2701")` checks the exact
request, echoed symbol, PVC name, Dalian marker and qualified 44-field schema.
It preserves raw prices and independent native date/time labels. Missing or zero
last prices fail; previous settlement is never substituted. No JavaScript executes.

Qualification on 2026-10-30 used the publisher's
[contract page](https://finance.sina.com.cn/futures/quotes/V2701.shtml) and its
[field mapping](https://n.sinaimg.cn/finance/futures/moudler20200421.js), accounting
for the symbol prepended by the publisher before display. The DCE-authored
[contract PDF](https://www.htfc.com/wz_upload/png_upload/20240207/17072856162152a5658.pdf)
confirms CNY/tonne and 5 tonnes/lot. Contract size is not a price multiplier.
Official-host contract/guide requests timed out. Different reference tick sizes
are unresolved; tick size, volume/open-interest units, trading-day attribution,
calendar quote timestamp and publication time are outside this contract.

Default V2701 is a named observation sample, never an automatically rolled main
contract. Consumers must govern listing evidence and a conservative expiry bound
before acquisition. A vendor snapshot does not establish a physical spot price,
real-time freshness, historical PIT eligibility, or an execution price.
