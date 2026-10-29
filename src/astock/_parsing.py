"""Small validation helpers; source-native units are never silently normalized."""

import json
from decimal import Decimal
from urllib.parse import urlsplit

from .contracts import FetchResult, RawObservation, SourceRequest, Status, transport_failure


def preflight(raw: RawObservation, expected: SourceRequest) -> FetchResult | None:
    failed = transport_failure(raw)
    if failed is not None:
        return failed
    actual = raw.request
    if (actual.provider, actual.capability, actual.method, actual.url, actual.body) != (
        expected.provider, expected.capability, expected.method, expected.url, expected.body
    ):
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    return None


def decimal(value) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise TypeError("INVALID_NUMERIC_VALUE")
    result = Decimal(value)
    if not result.is_finite():
        raise ValueError("NONFINITE_VALUE")
    return result


def text(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("MISSING_TEXT")
    return value.strip()


def web_url(value) -> str:
    value = text(value)
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise ValueError("INVALID_RECORD_URL")
    return value


def json_body(raw: RawObservation):
    return json.loads(raw.body, parse_float=Decimal)


def result(raw: RawObservation, records: list) -> FetchResult:
    return FetchResult(raw, Status.SUCCESS if records else Status.EMPTY,
                       "SOURCE_RECORDS" if records else "SOURCE_EMPTY", tuple(records))
