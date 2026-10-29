"""Source acquisition and parsing, independent of warehouse or trading consumers."""

from .contracts import FetchResult, RawObservation, SourceRequest, Status

__all__ = ["FetchResult", "RawObservation", "SourceRequest", "Status", "capabilities"]
__version__ = "0.1.1"


def capabilities() -> tuple[SourceRequest, ...]:
    """Enumerate supported default requests; this grants no consumer admission."""
    from . import bonds, disclosures, funds, lpr, macro, news, quotes, rss

    requests = [lpr.request(), rss.request(), bonds.request(), disclosures.request(), funds.request()]
    requests.extend(macro.request(series) for series in sorted(macro.REPORTS))
    requests.extend(news.request(channel) for channel in (2510, 2516))
    requests.extend(quotes.request(provider) for provider in ("tencent", "sina", "eastmoney"))
    return tuple(sorted(requests, key=lambda value: (value.provider, value.capability)))
