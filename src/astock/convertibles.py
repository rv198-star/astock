"""Jisilu's anonymous partial list. Login-only coverage is never inferred."""

import re
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class GuestBond:
    bond_code: str
    name: str
    bond_type: str
    stock_code: str
    price_native: Decimal
    conversion_price_native: Decimal
    stock_price_native: Decimal
    last_time_text: str | None
    listing_date: date | None
    source_context_date: date
    guest_prompt: str


def request() -> SourceRequest:
    return SourceRequest(
        "jisilu",
        "convertible.list",
        "GET",
        "https://www.jisilu.cn/webapi/cb/list/",
        headers=(
            ("Referer", "https://www.jisilu.cn/web/data/cb/"),
            ("Columns", "1,2,3"),
            ("Init", "1"),
        ),
    )


def parse(raw: RawObservation) -> FetchResult[GuestBond]:
    expected = request()
    failed = p.preflight(raw, expected)
    if failed is not None:
        return failed
    if raw.request.identity != expected.identity:
        return FetchResult(raw, Status.FAILED, "SOURCE_IDENTITY_MISMATCH")
    try:
        body = p.json_body(raw)
        if type(body["code"]) is not int or body["code"] != 200:
            raise ValueError("GUEST_SOURCE_ERROR")
        rows = body["data"]
        if not isinstance(rows, list) or len(rows) > 30:
            raise ValueError("GUEST_LIST_BOUND_EXCEEDED")
        context_date = date.fromisoformat(p.text(body["info"]["date"]))
        prompt = p.text(body["prompt"])
        records = []
        for row in rows:
            bond, stock = p.text(row["bond_id"]), p.text(row["stock_id"])
            if (
                not re.fullmatch(r"(?:11|12|13)[0-9]{4}", bond)
                or not re.fullmatch(r"[036][0-9]{5}", stock)
                or row["btype"] not in {"C", "E"}
            ):
                raise ValueError("INVALID_BOND_IDENTITY")
            prices = [p.decimal(row[key]) for key in ("price", "convert_price", "sprice")]
            if any(value <= 0 for value in prices):
                raise ValueError("INVALID_REFERENCE_PRICE")
            clock = row["last_time"]
            if clock is not None:
                clock = p.text(clock)
                if not re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}", clock):
                    raise ValueError("INVALID_SOURCE_TIME")
                time.fromisoformat(clock)
            listing = row["list_dt"]
            listed = date.fromisoformat(p.text(listing)) if listing is not None else None
            records.append(
                GuestBond(
                    bond,
                    p.text(row["bond_nm"]),
                    row["btype"],
                    stock,
                    *prices,
                    clock,
                    listed,
                    context_date,
                    prompt,
                )
            )
        if len({x.bond_code for x in records}) != len(records):
            raise ValueError("DUPLICATE_BOND_CODE")
    except (ValueError, KeyError, TypeError, ArithmeticError):
        return FetchResult(raw, Status.FAILED, "INVALID_GUEST_BOND_SCHEMA")
    return p.result(raw, records)
