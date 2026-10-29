"""Bounded Eastmoney fund NAV, with request-bound identity and native values.

NAV dates are valuation dates, not publication clocks. The response does not
normally echo the fund code: retain that limitation instead of inventing proof.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class FundNav:
    fund_code: str
    valuation_date: date
    unit_nav_native: Decimal
    accumulated_nav_native: Decimal
    daily_change_percent: Decimal
    subscription_status: str
    redemption_status: str
    dividend_text: str
    identity_basis: str = "REQUEST_BOUND_NO_RESPONSE_ECHO"
    unit_basis: str = "SOURCE_NAV_CURRENCY_REQUIRES_FUND_METADATA"


def request(fund_code: str = "000001", *, page: int = 1, page_size: int = 2) -> SourceRequest:
    if not re.fullmatch(r"[0-9]{6}", fund_code):
        raise ValueError("INVALID_FUND_CODE")
    if any(type(x) is not int or x < 1 for x in (page, page_size)) or page_size > 100:
        raise ValueError("INVALID_FUND_PAGE")
    params = {
        "fundCode": fund_code,
        "pageIndex": page,
        "pageSize": page_size,
        "startDate": "",
        "endDate": "",
    }
    return SourceRequest(
        "eastmoney",
        "fund.nav",
        "GET",
        "https://api.fund.eastmoney.com/f10/lsjz?" + urlencode(params),
        headers=(("Referer", "https://fund.eastmoney.com/"),),
    )


def parse(
    raw: RawObservation, fund_code: str = "000001", *, page: int = 1, page_size: int = 2
) -> FetchResult[FundNav]:
    failed = p.preflight(raw, request(fund_code, page=page, page_size=page_size))
    if failed is not None:
        return failed
    if raw.request.identity != request(fund_code, page=page, page_size=page_size).identity:
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        data = p.json_body(raw)
        if type(data["ErrCode"]) is not int or data["ErrCode"] != 0:
            return FetchResult(raw, Status.FAILED, "SOURCE_REPORTED_ERROR")
        if (
            type(data["PageIndex"]) is not int
            or type(data["PageSize"]) is not int
            or data["PageIndex"] != page
            or data["PageSize"] != page_size
        ):
            return FetchResult(raw, Status.FAILED, "SOURCE_PAGE_MISMATCH")
        if type(data["TotalCount"]) is not int or data["TotalCount"] < 0:
            raise ValueError("INVALID_FUND_TOTAL")
        block = data["Data"]
        if "FundCode" in block and block["FundCode"] != fund_code:
            return FetchResult(raw, Status.FAILED, "SOURCE_FUND_IDENTITY_MISMATCH")
        rows = block["LSJZList"]
        if not isinstance(rows, list) or len(rows) > page_size:
            raise ValueError("INVALID_FUND_ROWS")
        if len(rows) != min(page_size, max(0, data["TotalCount"] - (page - 1) * page_size)):
            return FetchResult(raw, Status.FAILED, "SOURCE_INCOMPLETE_FUND_PAGE")
        records = []
        for row in rows:
            stamp = p.text(row["FSRQ"])
            day = date.fromisoformat(stamp)
            if day.isoformat() != stamp:
                raise ValueError("INVALID_NAV_DATE")
            nav, acc = p.decimal(row["DWJZ"]), p.decimal(row["LJJZ"])
            if nav < 0 or acc < 0 or not isinstance(row["FHFCBZ"], str):
                raise ValueError("INVALID_NAV_VALUE")
            records.append(
                FundNav(
                    fund_code,
                    day,
                    nav,
                    acc,
                    p.decimal(row["JZZZL"]),
                    p.text(row["SGZT"]),
                    p.text(row["SHZT"]),
                    row["FHFCBZ"],
                )
            )
        if len({x.valuation_date for x in records}) != len(records):
            raise ValueError("DUPLICATE_VALUATION_DATE")
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return FetchResult(raw, Status.FAILED, "INVALID_FUND_NAV_SCHEMA")
    return p.result(raw, records)
