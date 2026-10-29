# Maintained astock source library

This public fork maintains a consumer-independent Python source library alongside
the original a-stock-data skill. Its initial upstream baseline is
`simonlin1212/a-stock-data@cb57c7aba720380b48a11dd065c6db57a2c39db9` (SKILL 3.10.3).
The library has its own version, currently 0.1.1. The original skill version and
the library version are different identities.

## Scope and adapters

`astock` owns bounded source requests, explicit source identity, raw response
evidence, parsing and clearly reported errors. Consumers own warehouse publication,
historical PIT admission, task scheduling, policies and trading decisions. The
library imports no consumer package, writes no warehouse and launches no timers.

The maintained contracts enumerate 15 default requests across these adapters:

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
`astock.capabilities()` enumerates the 15 default source requests without network
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
