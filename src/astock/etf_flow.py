"""One ETF's vendor-classified trading flows; not fund creations/redemptions."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status

AMOUNTS = ("f62", "f66", "f72", "f78", "f84")
PERCENTAGES = ("f184", "f69", "f75", "f81", "f87")


@dataclass(frozen=True)
class TradingFlow:
    security: str
    name: str
    amounts_native: tuple[tuple[str, Decimal], ...]
    percentages_native: tuple[tuple[str, Decimal], ...]
    source_timestamp_seconds: int


def request(security: str = "sh510300") -> SourceRequest:
    if not re.fullmatch(r"(?:sh(?:51|58)[0-9]{4}|sz15[0-9]{4})", security):
        raise ValueError("SINGLE_MAINLAND_ETF_REQUIRED")
    secid = ("1." if security.startswith("sh") else "0.") + security[2:]
    fields = "f12,f13,f14,f62,f184,f66,f69,f72,f75,f78,f81,f84,f87,f124"
    query = urlencode({"fltt": 2, "invt": 2, "secids": secid, "fields": fields})
    return SourceRequest(
        "eastmoney",
        "etf.trading_flow.snapshot",
        "GET",
        "https://push2.eastmoney.com/api/qt/ulist.np/get?" + query,
        headers=(("Referer", f"https://data.eastmoney.com/zjlx/{security[2:]}.html"),),
    )


def parse(raw: RawObservation, *, security: str = "sh510300") -> FetchResult[TradingFlow]:
    expected = request(security)
    failed = p.preflight(raw, expected)
    if failed is not None:
        return failed
    if raw.request.identity != expected.identity:
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        body = p.json_body(raw)
        if type(body["rc"]) is not int or body["rc"] != 0:
            raise ValueError("FLOW_SOURCE_ERROR")
        data = body["data"]
        rows, total = data["diff"], data["total"]
        if (
            not isinstance(rows, list)
            or type(total) is not int
            or total != len(rows)
            or not 0 <= len(rows) <= 1
        ):
            raise ValueError("INCONSISTENT_SINGLE_ETF_COUNT")
        records = []
        for row in rows:
            venue = 1 if security.startswith("sh") else 0
            if row["f12"] != security[2:] or type(row["f13"]) is not int or row["f13"] != venue:
                raise ValueError("ETF_IDENTITY_MISMATCH")
            clock = row["f124"]
            if type(clock) is not int or clock <= 0:
                raise ValueError("INVALID_SOURCE_EPOCH_SECONDS")
            datetime.fromtimestamp(clock, tz=timezone.utc)
            amounts = tuple((key, p.decimal(row[key])) for key in AMOUNTS)
            percentages = tuple((key, p.decimal(row[key])) for key in PERCENTAGES)
            if any(abs(value) > 100 for _, value in percentages):
                raise ValueError("INVALID_FLOW_PERCENTAGE")
            records.append(TradingFlow(security, p.text(row["f14"]), amounts, percentages, clock))
    except (ValueError, KeyError, TypeError, ArithmeticError, OverflowError, OSError):
        return FetchResult(raw, Status.FAILED, "INVALID_ETF_TRADING_FLOW_SCHEMA")
    return p.result(raw, records)
