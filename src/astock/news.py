"""Sina roll-feed metadata. Channel membership confers no regulatory authority."""

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class NewsItem:
    channel: int
    title: str
    url: str
    native_id: str | None
    source_ctime_text: str | None
    source_created_at: datetime | None


def request(channel: int = 2516) -> SourceRequest:
    if type(channel) is not int or channel not in {2516, 2510}:
        raise ValueError("UNSUPPORTED_NEWS_CHANNEL")
    query = urlencode({"pageid": 153, "lid": channel, "k": "", "num": 2, "page": 1})
    return SourceRequest("sina", "news.roll." + str(channel), "GET",
                         "https://feed.mix.sina.com.cn/api/roll/get?" + query)


def parse(raw: RawObservation, channel: int = 2516) -> FetchResult[NewsItem]:
    failed = p.preflight(raw, request(channel))
    if failed is not None:
        return failed
    try:
        data = p.json_body(raw)["result"]
        if type(data["status"]["code"]) is not int or data["status"]["code"] != 0:
            return FetchResult(raw, Status.FAILED, "SOURCE_REPORTED_ERROR")
        if data["lid"] != channel or type(data["lid"]) is not int:
            return FetchResult(raw, Status.FAILED, "NEWS_CHANNEL_MISMATCH")
        rows = data["data"]
        if not isinstance(rows, list):
            raise TypeError("ROWS_NOT_LIST")
        records = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("ROW_NOT_OBJECT")
            clock = row.get("ctime")
            stamp = None
            if clock is not None:
                if not isinstance(clock, str) or not clock.isascii() or not clock.isdigit():
                    raise ValueError("INVALID_SOURCE_CTIME")
                stamp = datetime.fromtimestamp(int(clock), timezone.utc)
            native_id = row.get("docid")
            if native_id is not None:
                native_id = p.text(native_id)
            records.append(NewsItem(channel, p.text(row["title"]), p.web_url(row["url"]),
                                    native_id, clock, stamp))
        if len({x.url for x in records}) != len(records):
            return FetchResult(raw, Status.FAILED, "DUPLICATE_NEWS_URL")
    except (ValueError, KeyError, TypeError, OverflowError, OSError):
        return FetchResult(raw, Status.FAILED, "INVALID_NEWS_SCHEMA")
    return p.result(raw, records)
