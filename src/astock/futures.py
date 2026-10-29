"""One named Sina PVC futures contract; prices are not physical spot prices.

The publisher prepends the request symbol before mapping its commodity fields.
These indices address the original response, before that presentation transform.
Native date/time labels have no proven trading-day or publication-time semantics.
"""

import re
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class ContractPrice:
    contract: str
    venue: str
    name: str
    delivery_month: str
    last_native: Decimal
    open_native: Decimal
    high_native: Decimal
    low_native: Decimal
    source_date_label: date
    source_time_text: str
    unqualified_fields: tuple[tuple[int, str], ...]


def request(contract: str = "V2701") -> SourceRequest:
    if not isinstance(contract, str) or not re.fullmatch(r"V[0-9]{2}(?:0[1-9]|1[0-2])", contract):
        raise ValueError("EXPLICIT_PVC_DELIVERY_CONTRACT_REQUIRED")
    return SourceRequest(
        "sina",
        "futures.price.snapshot",
        "GET",
        "https://hq.sinajs.cn/list=nf_" + contract,
        headers=(("Referer", "https://finance.sina.com.cn/"),),
    )


def parse(raw: RawObservation, *, contract: str = "V2701") -> FetchResult[ContractPrice]:
    expected = request(contract)
    failed = p.preflight(raw, expected)
    if failed is not None:
        return failed
    if raw.request.identity != expected.identity:
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        match = re.fullmatch(
            re.escape("var hq_str_nf_" + contract) + r'="([^"\r\n]*)";\s*',
            raw.body.decode("gb18030"),
        )
        if match is None:
            raise ValueError("INVALID_CONTRACT_ENVELOPE")
        if not match[1]:
            return p.result(raw, [])
        row = match[1].split(",")
        if len(row) != 44:
            raise ValueError("UNQUALIFIED_CONTRACT_SCHEMA_VERSION")
        if row[0] != "PVC" + contract[1:] or row[15:17] != ["连", "PVC"]:
            raise ValueError("CONTRACT_IDENTITY_MISMATCH")
        values = [p.decimal(row[i]) for i in (8, 2, 3, 4)]
        last, opening, high, low = values
        if min(values) <= 0 or not low <= last <= high or not low <= opening <= high:
            # The publisher substitutes previous settlement when last is zero.
            # A missing latest price must never silently become another field.
            raise ValueError("MISSING_OR_INCONSISTENT_CONTRACT_PRICE")
        label = date.fromisoformat(row[17])
        if re.fullmatch(r"[0-9]{6}", row[1]) is None:
            raise ValueError("INVALID_CONTRACT_TIME_LABEL")
        clock = time(int(row[1][:2]), int(row[1][2:4]), int(row[1][4:]))
        if label.isoformat() != row[17] or clock.strftime("%H%M%S") != row[1]:
            raise ValueError("INVALID_CONTRACT_DATE_OR_TIME_LABEL")
        excluded = tuple(
            (i, value) for i, value in enumerate(row) if i not in {0, 1, 2, 3, 4, 8, 15, 16, 17}
        )
        item = ContractPrice(
            contract,
            "DCE",
            row[0],
            "20" + contract[1:3] + "-" + contract[3:],
            *values,
            label,
            row[1],
            excluded,
        )
        return p.result(raw, [item])
    except (ValueError, TypeError, ArithmeticError, UnicodeError):
        return FetchResult(raw, Status.FAILED, "INVALID_FUTURES_PRICE_SCHEMA")
