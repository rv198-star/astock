"""Finite Eastmoney A-share samples with explicit dates and source-native numbers.

Default dates are frozen examples, never a promise of latest-session coverage.
No pagination, display-unit conversion, missing-to-zero, or vendor fallback occurs.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status

MARGIN_AMOUNTS = ("RZYE", "RQYE", "RZRQYE", "RZMRE", "RZCHE", "RZJME")
MARGIN_SHARES = ("RQYL", "RQMCL", "RQCHL", "RQJMG")
MARGIN_FIELDS = MARGIN_AMOUNTS + MARGIN_SHARES
BLOCK_FIELDS = ("DEAL_PRICE", "CLOSE_PRICE", "DEAL_VOLUME", "DEAL_AMT", "PREMIUM_RATIO")


@dataclass(frozen=True)
class MarginBalance:
    security: str
    name: str
    session_date: date
    source_fields: tuple[tuple[str, Decimal], ...]
    unqualified_fields: tuple[tuple[str, str], ...]
    reported_total: int
    reported_pages: int


@dataclass(frozen=True)
class BlockTrade:
    security: str
    name: str
    session_date: date
    source_rank: int
    buyer: str
    seller: str
    source_fields: tuple[tuple[str, Decimal], ...]
    reported_total: int
    reported_pages: int


def _date(value: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("ISO_SESSION_DATE_REQUIRED")
    return date.fromisoformat(value)


def _security(code: str, secucode: str) -> str:
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise ValueError("A_SHARE_SECURITY_REQUIRED")
    venue = "SH" if code.startswith(("60", "68")) else (
        "SZ" if code.startswith(("00", "30")) else (
            "BJ" if code.startswith(("4", "8", "92")) else None
        )
    )
    if venue is None or secucode != code + "." + venue:
        raise ValueError("A_SHARE_SECURITY_IDENTITY_MISMATCH")
    return venue.lower() + code


def _request(capability: str, report: str, scope: str, sort: str, limit: int) -> SourceRequest:
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("SAMPLE_LIMIT_1_TO_20_REQUIRED")
    query = urlencode({
        "reportName": report, "columns": "ALL", "pageNumber": "1", "pageSize": str(limit),
        "sortColumns": sort, "sortTypes": "-1" if sort == "DATE" else "1",
        "source": "WEB", "client": "WEB", "filter": scope,
    })
    return SourceRequest("eastmoney", capability, "GET",
                         "https://datacenter-web.eastmoney.com/api/data/v1/get?" + query,
                         headers=(("Referer", "https://data.eastmoney.com/"),))


def margin_request(code: str = "600519", *, start: str = "2026-10-26",
                   end: str = "2026-10-29", limit: int = 2) -> SourceRequest:
    if not isinstance(code, str) or not re.fullmatch(r"(?:60|68|00|30)[0-9]{4}", code):
        raise ValueError("SINGLE_SH_OR_SZ_A_SHARE_REQUIRED")
    if not 0 <= (_date(end) - _date(start)).days <= 30:
        raise ValueError("MAXIMUM_31_CALENDAR_DAY_WINDOW_REQUIRED")
    scope = f'(SCODE="{code}")(DATE>=\'{start}\')(DATE<=\'{end}\')'
    return _request("margin.single_security.bounded", "RPTA_WEB_RZRQ_GGMX", scope, "DATE", limit)


def block_request(trade_date: str = "2026-10-29", *, limit: int = 2) -> SourceRequest:
    _date(trade_date)
    scope = f'(SECURITY_TYPE_WEB="1")(TRADE_DATE=\'{trade_date}\')'
    return _request("block_trades.a_share.bounded", "RPT_DATA_BLOCKTRADE", scope,
                    "SECURITY_CODE", limit)


def _rows(raw: RawObservation, expected: SourceRequest, limit: int):
    if raw.request.identity != expected.identity:
        raise ValueError("SOURCE_IDENTITY_MISMATCH")
    body = p.json_body(raw)
    if body["success"] is not True or type(body["code"]) is not int or body["code"] != 0:
        raise ValueError("SOURCE_REPORTED_ERROR")
    result = body["result"]
    rows, total, pages = result["data"], result["count"], result["pages"]
    if (not isinstance(rows, list) or type(total) is not int or total < 0
            or type(pages) is not int or pages != (total + limit - 1) // limit
            or len(rows) != min(total, limit)):
        raise ValueError("INCONSISTENT_BOUNDED_PAGE")
    return rows, total, pages


def _session(value: str) -> date:
    stamp = datetime.strptime(p.text(value), "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
    if stamp.strftime("%Y-%m-%d %H:%M:%S") != value or stamp.time().isoformat() != "00:00:00":
        raise ValueError("SESSION_DATE_LABEL_REQUIRED")
    return stamp.date()


def parse_margin(raw: RawObservation, *, code: str = "600519", start: str = "2026-10-26",
                 end: str = "2026-10-29", limit: int = 2) -> FetchResult[MarginBalance]:
    expected = margin_request(code, start=start, end=end, limit=limit)
    failed = p.preflight(raw, expected)
    if failed is not None:
        return failed
    try:
        rows, total, pages = _rows(raw, expected, limit)
        records = []
        for row in rows:
            if row["SCODE"] != code:
                raise ValueError("MARGIN_SECURITY_SCOPE_MISMATCH")
            security = _security(row["SCODE"], row["SECUCODE"])
            session = _session(row["DATE"])
            if not _date(start) <= session <= _date(end):
                raise ValueError("SESSION_OUTSIDE_REQUEST_WINDOW")
            fields = tuple((key, p.decimal(row[key])) for key in MARGIN_FIELDS)
            values = dict(fields)
            if any(value < 0 for key, value in fields if key not in {"RZJME", "RQJMG"}):
                raise ValueError("NEGATIVE_MARGIN_BALANCE_OR_GROSS_FLOW")
            if any(values[k] != values[k].to_integral_value() for k in MARGIN_SHARES):
                raise ValueError("NONINTEGRAL_MARGIN_SHARES")
            # Preserve the vendor's numbers: inconsistent totals are never repaired.
            if (values["RZRQYE"] != values["RZYE"] + values["RQYE"]
                    or values["RZJME"] != values["RZMRE"] - values["RZCHE"]
                    or values["RQJMG"] != values["RQMCL"] - values["RQCHL"]):
                raise ValueError("INCONSISTENT_MARGIN_TOTALS")
            unqualified = (("RZRQYECZ", str(row["RZRQYECZ"])),) if (
                row.get("RZRQYECZ") is not None
            ) else ()
            records.append(MarginBalance(security, p.text(row["SECNAME"]), session,
                                         fields, unqualified, total, pages))
        sessions = [row.session_date for row in records]
        if len(set(sessions)) != len(sessions) or sessions != sorted(sessions, reverse=True):
            raise ValueError("DUPLICATE_OR_UNORDERED_MARGIN_SESSION")
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        reason = str(exc) if str(exc) in {"SOURCE_IDENTITY_MISMATCH", "SOURCE_REPORTED_ERROR"} else (
            "INVALID_MARGIN_SCHEMA"
        )
        return FetchResult(raw, Status.FAILED, reason)
    return p.result(raw, records)


def parse_blocks(raw: RawObservation, *, trade_date: str = "2026-10-29",
                 limit: int = 2) -> FetchResult[BlockTrade]:
    expected = block_request(trade_date, limit=limit)
    failed = p.preflight(raw, expected)
    if failed is not None:
        return failed
    try:
        rows, total, pages = _rows(raw, expected, limit)
        records = []
        for row in rows:
            if row["SECURITY_TYPE_WEB"] != "1" or row["SECURITY_TYPE"] != "EQA":
                raise ValueError("A_SHARE_BLOCK_TRADE_REQUIRED")
            security = _security(row["SECURITY_CODE"], row["SECUCODE"])
            session = _session(row["TRADE_DATE"])
            if session != _date(trade_date):
                raise ValueError("SESSION_OUTSIDE_REQUEST_WINDOW")
            fields = tuple((key, p.decimal(row[key])) for key in BLOCK_FIELDS)
            values = dict(fields)
            if (any(values[k] <= 0 for k in BLOCK_FIELDS[:-1])
                    or values["DEAL_VOLUME"] != values["DEAL_VOLUME"].to_integral_value()
                    or values["PREMIUM_RATIO"] <= -1):
                raise ValueError("INVALID_BLOCK_TRADE_NUMBERS")
            rank = row["DAILY_RANK"]
            if type(rank) is not int or rank < 1:
                raise ValueError("INVALID_VENDOR_ROW_RANK")
            records.append(BlockTrade(security, p.text(row["SECURITY_NAME_ABBR"]), session,
                                      rank, p.text(row["BUYER_NAME"]), p.text(row["SELLER_NAME"]),
                                      fields, total, pages))
        if len({(x.security, x.source_rank) for x in records}) != len(records):
            raise ValueError("DUPLICATE_VENDOR_BLOCK_ROW")
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        reason = str(exc) if str(exc) in {"SOURCE_IDENTITY_MISMATCH", "SOURCE_REPORTED_ERROR"} else (
            "INVALID_BLOCK_TRADE_SCHEMA"
        )
        return FetchResult(raw, Status.FAILED, reason)
    return p.result(raw, records)
