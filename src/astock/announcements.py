"""Bounded Eastmoney stock-announcement metadata; source dates are not PIT clocks."""

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class Announcement:
    security_code: str
    announcement_id: str
    title: str
    notice_date: date
    display_time_text: str | None
    production_time_text: str | None


def request(code: str = "600519", page_size: int = 2) -> SourceRequest:
    if (
        not re.fullmatch(r"[0-9]{6}", code)
        or type(page_size) is not int
        or not 1 <= page_size <= 20
    ):
        raise ValueError("BOUNDED_ANNOUNCEMENT_REQUEST_REQUIRED")
    query = urlencode(
        {
            "sr": -1,
            "page_size": page_size,
            "page_index": 1,
            "ann_type": "A",
            "client_source": "web",
            "stock_list": code,
        }
    )
    return SourceRequest(
        "eastmoney",
        "announcement.index",
        "GET",
        "https://np-anotice-stock.eastmoney.com/api/security/ann?" + query,
        headers=(("Referer", f"https://data.eastmoney.com/notices/stock/{code}.html"),),
    )


def _optional_clock(value) -> str | None:
    if value is None or value == "":
        return None
    return p.text(value)  # Preserve native text; no timezone/publication inference.


def parse(
    raw: RawObservation, *, code: str = "600519", page_size: int = 2
) -> FetchResult[Announcement]:
    expected = request(code, page_size)
    failed = p.preflight(raw, expected)
    if failed is not None:
        return failed
    if raw.request.identity != expected.identity:
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        body = p.json_body(raw)
        if type(body["success"]) is not int or body["success"] != 1 or body.get("error"):
            raise ValueError("ANNOUNCEMENT_SOURCE_ERROR")
        data = body["data"]
        rows, total = data["list"], data["total_hits"]
        if (
            not isinstance(rows, list)
            or type(total) is not int
            or not 0 <= len(rows) <= page_size
            or total < len(rows)
            or (not rows and total > 0)
            or type(data["page_index"]) is not int
            or data["page_index"] != 1
            or type(data["page_size"]) is not int
            or data["page_size"] != page_size
        ):
            raise ValueError("INCONSISTENT_ANNOUNCEMENT_PAGE")
        records = []
        for row in rows:
            codes = row["codes"]
            if (
                not isinstance(codes, list)
                or not codes
                or not any(x.get("stock_code") == code for x in codes)
            ):
                raise ValueError("ANNOUNCEMENT_SECURITY_MISMATCH")
            identifier = p.text(row["art_code"])
            if not re.fullmatch(r"AN[0-9]+", identifier):
                raise ValueError("INVALID_ANNOUNCEMENT_ID")
            notice = p.text(row["notice_date"])
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} 00:00:00", notice):
                raise ValueError("INVALID_NOTICE_DATE")
            records.append(
                Announcement(
                    code,
                    identifier,
                    p.text(row["title"]),
                    date.fromisoformat(notice[:10]),
                    _optional_clock(row.get("display_time")),
                    _optional_clock(row.get("eiTime")),
                )
            )
        if len({x.announcement_id for x in records}) != len(records):
            raise ValueError("DUPLICATE_ANNOUNCEMENT_ID")
    except (ValueError, KeyError, TypeError, AttributeError):
        return FetchResult(raw, Status.FAILED, "INVALID_ANNOUNCEMENT_SCHEMA")
    return p.result(raw, records)
