# Maintained astock source library

This public fork maintains a consumer-independent Python source library alongside
the original a-stock-data skill. Its initial upstream baseline is
`simonlin1212/a-stock-data@cb57c7aba720380b48a11dd065c6db57a2c39db9` (SKILL 3.10.3).
The library has its own version, currently 0.1.0. The original skill version and
the library version are different identities.

## Scope and first adapters

`astock` owns bounded source requests, explicit source identity, raw response
evidence, parsing and clearly reported errors. Consumers own warehouse publication,
historical PIT admission, task scheduling, policies and trading decisions. The
library imports no consumer package, writes no warehouse and launches no timers.

The first adapters are:

| Capability | Actual backend | Use ceiling |
| --- | --- | --- |
| `astock.lpr` | ChinaMoney `LprHis`, HTTPS POST | Source-observed LPR rates with effective dates; no inferred publication clock |
| `astock.rss` | Configured RSS/Atom publisher; default CNBC public feed | News discovery with optional publisher-provided, timezone-aware clocks |

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
`astock.capabilities()` enumerates the two default source requests without network
access; it is an interface registry, not an admission or availability registry.
Parsing can be replayed from retained observations without network access.
Consumers should pin an exact commit or built package digest, rather than install
`main`/`latest` during a running job. No consumer-specific path is embedded here.

## Maintenance and checks

`upstream` points to the original project; `origin` points to this fork. Review
upstream changes on a branch and merge applicable changes with test evidence.
Do not overwrite maintained modules by regenerating them from SKILL.md at runtime.
Preserve the original license/attribution and record newly copied code's provenance.

```bash
make check
make check-upstream
```

`check` runs the maintained library's offline synthetic contracts. `check-upstream`
also runs the retained original tests and needs their optional spreadsheet clients
(including openpyxl). Live upstream tests remain opt-in. Report these checks
separately; a pass of new-library contracts is not a full upstream compatibility pass.
