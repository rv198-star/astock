"""Eastmoney current-vintage macro rows; report periods are not release clocks."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status

REPORTS = {
    "cpi": ("RPT_ECONOMY_CPI", ("NATIONAL_SAME", "NATIONAL_BASE", "NATIONAL_SEQUENTIAL")),
    "ppi": ("RPT_ECONOMY_PPI", ("BASE", "BASE_SAME", "BASE_ACCUMULATE")),
    "pmi": ("RPT_ECONOMY_PMI", ("MAKE_INDEX", "NMAKE_INDEX")),
    "gdp": ("RPT_ECONOMY_GDP", ("DOMESTICL_PRODUCT_BASE", "SUM_SAME")),
    "m2": ("RPT_ECONOMY_CURRENCY_SUPPLY", ("BASIC_CURRENCY", "BASIC_CURRENCY_SAME")),
}


@dataclass(frozen=True)
class MacroRow:
    series: str
    report_date_text: str
    period_text: str
    source_fields: tuple[tuple[str, Decimal], ...]
    unit_basis: str = "SOURCE_NATIVE_UNNORMALIZED"


def request(series: str, *, page: int = 1, page_size: int = 2) -> SourceRequest:
    if series not in REPORTS:
        raise ValueError("UNSUPPORTED_MACRO_SERIES")
    if any(isinstance(x, bool) or not isinstance(x, int) or x < 1 for x in (page, page_size)):
        raise ValueError("INVALID_PAGE")
    if page_size > 200:
        raise ValueError("PAGE_SIZE_OUT_OF_RANGE")
    query = urlencode({"reportName": REPORTS[series][0], "columns": "ALL", "pageSize": page_size,
                       "pageNumber": page, "sortColumns": "REPORT_DATE", "sortTypes": -1,
                       "source": "WEB"})
    return SourceRequest("eastmoney", "macro." + series, "GET",
                         "https://datacenter-web.eastmoney.com/api/data/v1/get?" + query)


def parse(raw: RawObservation, series: str, *, page: int = 1, page_size: int = 2) -> FetchResult[MacroRow]:
    failed = p.preflight(raw, request(series, page=page, page_size=page_size))
    if failed is not None:
        return failed
    try:
        data = p.json_body(raw)
        if data["success"] is not True or type(data["code"]) is not int or data["code"] != 0:
            return FetchResult(raw, Status.FAILED, "SOURCE_REPORTED_ERROR")
        rows = data["result"]["data"]
        if not isinstance(rows, list):
            raise TypeError("ROWS_NOT_LIST")
        records = []
        for row in rows:
            stamp = p.text(row["REPORT_DATE"])
            # Validation only: the vendor's period marker has no publication timezone.
            parsed = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
            if parsed.strftime("%Y-%m-%d %H:%M:%S") != stamp:
                raise ValueError("INVALID_REPORT_DATE")
            fields = tuple((key, p.decimal(row[key])) for key in REPORTS[series][1])
            records.append(MacroRow(series, stamp, p.text(row["TIME"]), fields))
        if len({x.report_date_text for x in records}) != len(records):
            return FetchResult(raw, Status.FAILED, "DUPLICATE_REPORT_PERIOD")
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return FetchResult(raw, Status.FAILED, "INVALID_MACRO_SCHEMA")
    return p.result(raw, records)
