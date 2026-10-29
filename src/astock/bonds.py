"""One identified ChinaBond treasury curve; observation date is not publication time."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status

CURVE_ID = "2c9081e50a2f9606010a3068cae70001"
CURVE_NAME = "中债国债收益率曲线(到期)"


@dataclass(frozen=True)
class CurvePoint:
    curve_id: str
    curve_name: str
    source_date: date
    maturity_native: Decimal
    yield_native: Decimal
    unit_basis: str = "SOURCE_NATIVE_UNNORMALIZED"


def request() -> SourceRequest:
    fields = {"xyzSelect": "txy", "workTime": "", "dxbj": "0", "qxll": "0", "yqqxN": "N",
              "yqqxK": "K", "wrjxCBFlag": "0", "locale": "zh_CN"}
    return SourceRequest("chinabond", "treasury.curve", "POST",
                         "https://yield.chinabond.com.cn/cbweb-mn/yc/inityc",
                         urlencode(fields).encode(),
                         (("Content-Type", "application/x-www-form-urlencoded"),
                          ("Referer", "https://yield.chinabond.com.cn/cbweb-mn/yield_main?locale=zh_CN"),
                          ("X-Requested-With", "XMLHttpRequest")))


def parse(raw: RawObservation) -> FetchResult[CurvePoint]:
    failed = p.preflight(raw, request())
    if failed is not None:
        return failed
    try:
        data = p.json_body(raw)
        if not isinstance(data, list) or len(data) != 2 or not isinstance(data[0], dict):
            raise ValueError("INVALID_CURVE_ENVELOPE")
        curves = data[1][1]
        if not isinstance(curves, list):
            raise TypeError("CURVES_NOT_LIST")
        records = []
        for curve in curves:
            if curve["ycDefId"] != CURVE_ID or curve["ycDefName"] != CURVE_NAME:
                return FetchResult(raw, Status.FAILED, "CURVE_IDENTITY_MISMATCH")
            stamp = date.fromisoformat(curve["worktime"])
            if stamp.isoformat() != curve["worktime"]:
                raise ValueError("INVALID_CURVE_DATE")
            points = curve["seriesData"]
            if not isinstance(points, list) or not points:
                raise ValueError("MISSING_CURVE_POINTS")
            for point in points:
                if not isinstance(point, list) or len(point) != 2:
                    raise ValueError("INVALID_CURVE_POINT")
                maturity, value = map(p.decimal, point)
                if maturity < 0:
                    raise ValueError("NEGATIVE_MATURITY")
                records.append(CurvePoint(CURVE_ID, CURVE_NAME, stamp, maturity, value))
        if len({(x.source_date, x.maturity_native) for x in records}) != len(records):
            return FetchResult(raw, Status.FAILED, "DUPLICATE_CURVE_POINT")
    except (ValueError, KeyError, TypeError, IndexError, InvalidOperation):
        return FetchResult(raw, Status.FAILED, "INVALID_CURVE_SCHEMA")
    return p.result(raw, records)
