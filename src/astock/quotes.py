"""Single-security native quote diagnostics; no adjustment or suspension inference."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class Quote:
    security: str
    name: str
    last_native: Decimal
    open_native: Decimal
    high_native: Decimal
    low_native: Decimal
    source_clock_text: str | None
    source_clock: datetime | None
    unit_basis: str = "SOURCE_NATIVE_UNNORMALIZED"
    adjustment_basis: str = "UNSPECIFIED_SOURCE_QUOTE"


def request(provider: str, security: str = "sh600519") -> SourceRequest:
    if not isinstance(security, str) or not re.fullmatch(r"(?:sh|sz|bj)[0-9]{6}", security):
        raise ValueError("EXPLICIT_SECURITY_VENUE_REQUIRED")
    headers = ()
    if provider == "tencent":
        url = "https://qt.gtimg.cn/q=" + security
    elif provider == "sina":
        url = "https://hq.sinajs.cn/list=" + security
        headers = (("Referer", "https://finance.sina.com.cn/"),)
    elif provider == "eastmoney":
        if security.startswith("bj"):
            raise ValueError("UNSUPPORTED_QUOTE_VENUE")
        query = urlencode({"secid": ("1." if security.startswith("sh") else "0.") + security[2:],
                           "fields": "f43,f44,f45,f46,f47,f48,f57,f58,f60", "fltt": 2})
        url = "https://push2.eastmoney.com/api/qt/stock/get?" + query
    else:
        raise ValueError("UNSUPPORTED_QUOTE_PROVIDER")
    return SourceRequest(provider, "quote.snapshot", "GET", url, headers=headers)


def parse(raw: RawObservation, security: str = "sh600519") -> FetchResult[Quote]:
    if raw.request.provider not in {"tencent", "sina", "eastmoney"}:
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    failed = p.preflight(raw, request(raw.request.provider, security))
    if failed is not None:
        return failed
    try:
        provider = raw.request.provider
        clock, clock_text = None, None
        if provider == "eastmoney":
            data = p.json_body(raw)
            if type(data["rc"]) is not int or data["rc"] != 0:
                return FetchResult(raw, Status.FAILED, "SOURCE_REPORTED_ERROR")
            row = data["data"]
            if row["f57"] != security[2:]:
                return FetchResult(raw, Status.FAILED, "SECURITY_IDENTITY_MISMATCH")
            name = p.text(row["f58"])
            values = [p.decimal(row[key]) for key in ("f43", "f46", "f44", "f45")]
        else:
            body = raw.body.decode("gb18030")
            prefix = "v_" if provider == "tencent" else "var hq_str_"
            match = re.fullmatch(re.escape(prefix + security) + r'="([^"\r\n]*)";\s*', body)
            if match is None:
                raise ValueError("INVALID_QUOTE_ENVELOPE")
            row = match[1].split("~" if provider == "tencent" else ",")
            if provider == "tencent":
                if row[2] != security[2:]:
                    return FetchResult(raw, Status.FAILED, "SECURITY_IDENTITY_MISMATCH")
                name = p.text(row[1])
                values = [p.decimal(row[i]) for i in (3, 5, 33, 34)]
                clock_text, pattern = row[30], "%Y%m%d%H%M%S"
            else:
                name = p.text(row[0])
                values = [p.decimal(row[i]) for i in (3, 1, 4, 5)]
                clock_text, pattern = row[30] + " " + row[31], "%Y-%m-%d %H:%M:%S"
            clock = datetime.strptime(clock_text, pattern).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
            if clock.strftime(pattern) != clock_text:
                raise ValueError("INVALID_SOURCE_CLOCK")
        last, opening, high, low = values
        if min(values) < 0 or low > high or not low <= last <= high or not low <= opening <= high:
            raise ValueError("INCONSISTENT_QUOTE_PRICES")
        return p.result(raw, [Quote(security, name, *values, clock_text, clock)])
    except (ValueError, KeyError, TypeError, IndexError, InvalidOperation, UnicodeError):
        return FetchResult(raw, Status.FAILED, "INVALID_QUOTE_SCHEMA")
