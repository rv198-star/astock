"""ChinaMoney LPR observations. Effective dates are not publication clocks."""

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from .contracts import FetchResult, RawObservation, SourceRequest, Status, transport_failure

URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprHis"


@dataclass(frozen=True)
class LprRate:
    effective_date: date
    one_year_percent: Decimal
    five_year_percent: Decimal


def request(page_size: int = 2) -> SourceRequest:
    if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 200:
        raise ValueError("PAGE_SIZE_OUT_OF_RANGE")
    return SourceRequest(
        "chinamoney",
        "lpr.history",
        "POST",
        URL,
        json.dumps({"pageNum": 1, "pageSize": page_size}).encode(),
        (("Content-Type", "application/json"), ("Referer", "https://www.chinamoney.com.cn/")),
    )


def parse(raw: RawObservation) -> FetchResult[LprRate]:
    failure = transport_failure(raw)
    if failure is not None:
        return failure
    if (raw.request.provider, raw.request.capability, raw.request.method, raw.request.url) != (
        "chinamoney",
        "lpr.history",
        "POST",
        URL,
    ):
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        data = json.loads(raw.body, parse_float=Decimal)
        if str(data["head"]["rep_code"]) != "200":
            return FetchResult(raw, Status.FAILED, "SOURCE_REPORTED_ERROR")
        rows = data["records"]
        if not isinstance(rows, list):
            raise TypeError("RECORDS_NOT_LIST")
        records = []
        for row in rows:
            stamp = row["showDateCN"]
            if not isinstance(stamp, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
                raise ValueError("INVALID_EFFECTIVE_DATE")
            if any(isinstance(row[k], bool) for k in ("1Y", "5Y")):
                raise ValueError("BOOLEAN_RATE")
            rates = [Decimal(row[k]) for k in ("1Y", "5Y")]
            if not all(x.is_finite() for x in rates):
                raise ValueError("NONFINITE_RATE")
            records.append(LprRate(date.fromisoformat(stamp), *rates))
        if len({x.effective_date for x in records}) != len(records):
            return FetchResult(raw, Status.FAILED, "DUPLICATE_EFFECTIVE_DATE")
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return FetchResult(raw, Status.FAILED, "INVALID_LPR_SCHEMA")
    return FetchResult(
        raw,
        Status.SUCCESS if records else Status.EMPTY,
        "SOURCE_RECORDS" if records else "SOURCE_EMPTY",
        tuple(records),
    )
