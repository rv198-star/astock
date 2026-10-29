"""Synthetic NAV identity/schema contracts; no market payloads or network."""

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from astock import RawObservation, Status, capabilities, funds


def entry(**changes):
    return {
        "FSRQ": "2001-02-03",
        "DWJZ": "1.0023",
        "LJJZ": "2.5000",
        "JZZZL": "-0.17",
        "SGZT": "OPEN",
        "SHZT": "CLOSED",
        "FHFCBZ": "",
        **changes,
    }


def envelope(rows, **changes):
    return {
        "ErrCode": 0,
        "PageIndex": 1,
        "PageSize": 2,
        "TotalCount": len(rows),
        "Data": {"LSJZList": rows},
        **changes,
    }


def raw(data):
    return RawObservation(
        funds.request(), datetime(2001, 2, 4, tzinfo=timezone.utc), json.dumps(data).encode(), 200
    )


class FundNavTests(unittest.TestCase):
    def test_native_values_and_request_bound_identity_are_explicit(self):
        value = funds.parse(raw(envelope([entry()])))
        self.assertEqual(value.status, Status.SUCCESS)
        item = value.records[0]
        self.assertEqual(item.fund_code, "000001")
        self.assertEqual(item.unit_nav_native, Decimal("1.0023"))
        self.assertEqual(item.daily_change_percent, Decimal("-0.17"))
        self.assertEqual(item.subscription_status, "OPEN")
        self.assertEqual(item.redemption_status, "CLOSED")
        self.assertEqual(item.identity_basis, "REQUEST_BOUND_NO_RESPONSE_ECHO")
        self.assertFalse(hasattr(item, "published_at"))
        self.assertEqual(str(item.valuation_date), "2001-02-03")

    def test_valid_empty_is_distinct_from_error_or_missing_payload(self):
        self.assertEqual(funds.parse(raw(envelope([]))).status, Status.EMPTY)
        for body in ({}, envelope([], ErrCode=1), envelope([], TotalCount=5)):
            self.assertEqual(funds.parse(raw(body)).status, Status.FAILED)

    def test_missing_invalid_or_zero_filled_numbers_cannot_succeed(self):
        for changes in (
            {"DWJZ": "--"},
            {"DWJZ": None},
            {"DWJZ": True},
            {"DWJZ": "NaN"},
            {"DWJZ": "-1"},
            {"JZZZL": ""},
            {"SGZT": ""},
            {"FSRQ": "2001-02-30"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    funds.parse(raw(envelope([entry(**changes)]))).status, Status.FAILED
                )

    def test_changed_fund_page_headers_or_backend_fail_identity(self):
        observation = raw(envelope([entry()]))
        for request in (
            funds.request("000002"),
            funds.request(page=2),
            replace(observation.request, headers=()),
            replace(observation.request, provider="other"),
        ):
            self.assertEqual(
                funds.parse(replace(observation, request=request)).status, Status.FAILED
            )

    def test_reported_identity_and_pagination_conflicts_fail(self):
        for value in (
            envelope([entry()], PageIndex=2),
            envelope([entry()], PageIndex=True),
            envelope([entry()], Data={"FundCode": "000002", "LSJZList": [entry()]}),
            envelope([entry(), entry()]),
        ):
            self.assertEqual(funds.parse(raw(value)).status, Status.FAILED)

    def test_tls_empty_body_and_truncation_are_failures(self):
        observation = raw(envelope([]))
        for changed in (
            replace(observation, error="TLS_VERIFICATION"),
            replace(observation, body=b""),
            replace(observation, complete=False),
        ):
            self.assertEqual(funds.parse(changed).status, Status.FAILED)

    def test_request_stays_bounded_without_ambient_source_selection(self):
        self.assertIn(funds.request(), capabilities())
        self.assertEqual(len(capabilities()), 18)
        for args in (
            {"fund_code": "000001&extra=1"},
            {"page_size": 0},
            {"page_size": 101},
            {"page": True},
        ):
            with self.assertRaises(ValueError):
                funds.request(**args)


if __name__ == "__main__":
    unittest.main()
