"""Source acquisition and parsing, independent of warehouse or trading consumers."""

from .contracts import FetchResult, RawObservation, SourceRequest, Status

__all__ = ["FetchResult", "RawObservation", "SourceRequest", "Status", "capabilities"]
__version__ = "0.1.0"


def capabilities() -> tuple[SourceRequest, ...]:
    """Enumerate supported default requests; this grants no consumer admission."""
    from . import lpr, rss

    return tuple(sorted((lpr.request(), rss.request()), key=lambda value: value.provider))
