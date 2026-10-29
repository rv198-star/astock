"""RSS/Atom news discovery; optional publication clocks are never inferred."""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

from .contracts import FetchResult, RawObservation, SourceRequest, Status, transport_failure

CNBC_URL = "https://www.cnbc.com/id/100003114/device/rss/rss.html"
ATOM = "{http://www.w3.org/2005/Atom}"


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str
    native_id: str | None
    published_text: str | None
    published_at: datetime | None


def request(provider: str = "cnbc", url: str = CNBC_URL) -> SourceRequest:
    return SourceRequest(provider, "news.rss", "GET", url)


def _clock(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            value = parsedate_to_datetime(text)
        except (ValueError, TypeError, OverflowError):
            return None
    return value if value.tzinfo is not None and value.utcoffset() is not None else None


def parse(raw: RawObservation) -> FetchResult[NewsItem]:
    failure = transport_failure(raw)
    if failure is not None:
        return failure
    if raw.request.capability != "news.rss" or raw.request.method != "GET":
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        root = ET.fromstring(raw.body)
        if root.tag == "rss" and root.find("channel") is not None:
            entries, prefix = root.findall("./channel/item"), ""
        elif root.tag == ATOM + "feed":
            entries, prefix = root.findall(ATOM + "entry"), ATOM
        else:
            return FetchResult(raw, Status.FAILED, "INVALID_FEED_ROOT")
        records = []
        for entry in entries:
            title = "".join(entry.find(prefix + "title").itertext()).strip()
            links = entry.findall(prefix + "link")
            link = next(
                (
                    x.attrib.get("href", "") if prefix else x.text or ""
                    for x in links
                    if not prefix or x.attrib.get("rel", "alternate") == "alternate"
                ),
                "",
            ).strip()
            if (
                not title
                or urlsplit(link).scheme not in {"https", "http"}
                or not urlsplit(link).hostname
            ):
                raise ValueError("INVALID_FEED_ITEM")
            stamp = (
                entry.findtext(prefix + ("published" if prefix else "pubDate")) or ""
            ).strip() or None
            native = (entry.findtext(prefix + ("id" if prefix else "guid")) or "").strip() or None
            records.append(NewsItem(title, link, native, stamp, _clock(stamp)))
    except (ET.ParseError, ValueError, AttributeError):
        return FetchResult(raw, Status.FAILED, "INVALID_FEED_SCHEMA")
    return FetchResult(
        raw,
        Status.SUCCESS if records else Status.EMPTY,
        "SOURCE_RECORDS" if records else "SOURCE_EMPTY",
        tuple(records),
    )
