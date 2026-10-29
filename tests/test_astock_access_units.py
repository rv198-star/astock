"""Synthetic access, identity, partial-coverage and monetary parsing contracts."""

import copy
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from astock import RawObservation, Status, announcements, convertibles, etf_flow

NOW = datetime(2001, 2, 3, tzinfo=timezone.utc)


def raw(module, body):
    return RawObservation(module.request(), NOW, json.dumps(body).encode(), 200)


def announcement_body():
    row = {
        "art_code": "AN200102010001",
        "title": "Synthetic notice",
        "notice_date": "2001-02-02 00:00:00",
        "display_time": "2001-02-01 20:01:02:123",
        "eiTime": "2001-02-01 20:02:00:000",
        "codes": [{"stock_code": "600519"}],
    }
    return {
        "success": 1,
        "error": "",
        "data": {"list": [row], "total_hits": 17, "page_index": 1, "page_size": 2},
    }


def flow_body():
    row = {
        "f12": "510300",
        "f13": 1,
        "f14": "Synthetic ETF",
        "f124": 981072000,
        "f62": "125.25",
        "f66": "-20.5",
        "f72": "145.75",
        "f78": "-100",
        "f84": "-25.25",
        "f184": "1.25",
        "f69": "-0.205",
        "f75": "1.455",
        "f81": "-1",
        "f87": "-0.25",
    }
    return {"rc": 0, "data": {"total": 1, "diff": [row]}}


def guest_body():
    row = {
        "bond_id": "123001",
        "bond_nm": "Synthetic bond",
        "btype": "C",
        "stock_id": "300001",
        "price": "111.123",
        "convert_price": "9.50",
        "sprice": "10.55",
        "last_time": "15:00:01",
        "list_dt": "2001-01-01",
    }
    return {
        "code": 200,
        "msg": "",
        "data": [row],
        "info": {"date": "2001-02-03"},
        "prompt": "Anonymous subset; full coverage requires login",
    }


class AnnouncementTests(unittest.TestCase):
    def test_current_path_identity_dates_and_millisecond_text_preserved(self):
        response = raw(announcements, announcement_body())
        parsed = announcements.parse(response)
        self.assertEqual(parsed.status, Status.SUCCESS)
        row = parsed.records[0]
        self.assertIn("/security/ann?", response.request.url)
        self.assertEqual(row.security_code, "600519")
        self.assertEqual(str(row.notice_date), "2001-02-02")
        self.assertEqual(row.display_time_text, "2001-02-01 20:01:02:123")
        self.assertFalse(hasattr(row, "published_at"))

    def test_wrong_security_count_page_or_business_error_fails(self):
        for change in ("code", "count", "page", "error", "duplicate", "date"):
            body = announcement_body()
            if change == "code":
                body["data"]["list"][0]["codes"] = [{"stock_code": "600000"}]
            if change == "count":
                body["data"]["total_hits"] = 0
            if change == "page":
                body["data"]["page_index"] = True
            if change == "error":
                body["success"] = 0
            if change == "duplicate":
                body["data"]["list"] *= 2
            if change == "date":
                body["data"]["list"][0]["notice_date"] = "2001-02-30 00:00:00"
            with self.subTest(change=change):
                self.assertEqual(
                    announcements.parse(raw(announcements, body)).status, Status.FAILED
                )

    def test_explicit_empty_and_optional_clock_are_separate(self):
        body = announcement_body()
        body["data"].update(list=[], total_hits=0)
        self.assertEqual(announcements.parse(raw(announcements, body)).status, Status.EMPTY)
        body = announcement_body()
        del body["data"]["list"][0]["display_time"]
        self.assertIsNone(
            announcements.parse(raw(announcements, body)).records[0].display_time_text
        )


class TradingFlowTests(unittest.TestCase):
    def test_signed_exact_native_values_and_one_security(self):
        parsed = etf_flow.parse(raw(etf_flow, flow_body()))
        self.assertEqual(parsed.status, Status.SUCCESS)
        row = parsed.records[0]
        self.assertEqual(row.security, "sh510300")
        self.assertEqual(dict(row.amounts_native)["f66"], Decimal("-20.5"))
        self.assertEqual(dict(row.percentages_native)["f184"], Decimal("1.25"))
        self.assertFalse(hasattr(row, "subscription_flow"))
        self.assertIn("secids=1.510300", etf_flow.request().url)

    def test_wrong_code_venue_count_or_epoch_unit_fails(self):
        for change in ("code", "venue", "count", "epoch"):
            body = flow_body()
            if change == "code":
                body["data"]["diff"][0]["f12"] = "510301"
            if change == "venue":
                body["data"]["diff"][0]["f13"] = True
            if change == "count":
                body["data"]["total"] = 2
            if change == "epoch":
                body["data"]["diff"][0]["f124"] *= 1000
            self.assertEqual(etf_flow.parse(raw(etf_flow, body)).status, Status.FAILED)

    def test_missing_nonfinite_or_sentinel_values_never_become_zero(self):
        for value in (None, True, "--", "broken", "NaN", "Infinity"):
            body = flow_body()
            body["data"]["diff"][0]["f62"] = value
            with self.subTest(value=value):
                self.assertEqual(etf_flow.parse(raw(etf_flow, body)).status, Status.FAILED)
        body = flow_body()
        body["data"]["diff"][0]["f184"] = "100.01"
        self.assertEqual(etf_flow.parse(raw(etf_flow, body)).status, Status.FAILED)

    def test_explicit_empty_requires_consistent_source_count(self):
        self.assertEqual(
            etf_flow.parse(raw(etf_flow, {"rc": 0, "data": {"total": 0, "diff": []}})).status,
            Status.EMPTY,
        )
        self.assertEqual(
            etf_flow.parse(raw(etf_flow, {"rc": 1, "data": None})).status, Status.FAILED
        )


class GuestBondTests(unittest.TestCase):
    def test_partial_coverage_and_date_context_do_not_create_a_quote_datetime(self):
        parsed = convertibles.parse(raw(convertibles, guest_body()))
        self.assertEqual(parsed.status, Status.SUCCESS)
        row = parsed.records[0]
        self.assertEqual(row.price_native, Decimal("111.123"))
        self.assertEqual(row.last_time_text, "15:00:01")
        self.assertEqual(str(row.source_context_date), "2001-02-03")
        self.assertIn("requires login", row.guest_prompt)
        self.assertFalse(hasattr(row, "quote_at"))

    def test_missing_time_or_listing_is_preserved_as_unknown(self):
        body = guest_body()
        body["data"][0].update(last_time=None, list_dt=None)
        row = convertibles.parse(raw(convertibles, body)).records[0]
        self.assertIsNone(row.last_time_text)
        self.assertIsNone(row.listing_date)

    def test_convertible_and_exchangeable_types_remain_distinct(self):
        body = guest_body()
        row = copy.deepcopy(body["data"][0])
        row.update(bond_id="132001", btype="E")
        body["data"].append(row)
        result = convertibles.parse(raw(convertibles, body))
        self.assertEqual([x.bond_type for x in result.records], ["C", "E"])

    def test_invalid_clock_type_duplicate_or_guest_scope_fails(self):
        for change in ("clock", "kind", "duplicate", "bound", "business_error"):
            body = guest_body()
            if change == "clock":
                body["data"][0]["last_time"] = "25:00:00"
            if change == "kind":
                body["data"][0]["btype"] = "STOCK"
            if change == "duplicate":
                body["data"] *= 2
            if change == "bound":
                body["data"] *= 31
            if change == "business_error":
                body["code"] = 401
            self.assertEqual(convertibles.parse(raw(convertibles, body)).status, Status.FAILED)

    def test_bad_monetary_values_fail_and_valid_empty_is_explicit(self):
        for value in (None, True, "broken", "NaN", "0", "-1"):
            body = guest_body()
            body["data"][0]["convert_price"] = value
            self.assertEqual(convertibles.parse(raw(convertibles, body)).status, Status.FAILED)
        body = guest_body()
        body["data"] = []
        self.assertEqual(convertibles.parse(raw(convertibles, body)).status, Status.EMPTY)


class AccessIdentityTests(unittest.TestCase):
    def test_changed_headers_legacy_routes_or_transport_never_succeed(self):
        for module, body in (
            (announcements, announcement_body()),
            (etf_flow, flow_body()),
            (convertibles, guest_body()),
        ):
            response = raw(module, body)
            for changed in (
                replace(response, body=b""),
                replace(response, complete=False),
                replace(response, http_status=429),
                replace(response, request=replace(response.request, headers=())),
                replace(response, request=replace(response.request, url="https://example.org/old")),
            ):
                self.assertEqual(module.parse(changed).status, Status.FAILED)

    def test_request_budget_and_identity_scope_are_explicit(self):
        with self.assertRaises(ValueError):
            announcements.request(page_size=10000)
        with self.assertRaises(ValueError):
            announcements.request(code="600519&x=1")
        with self.assertRaises(ValueError):
            etf_flow.request("sh600519")
        with self.assertRaises(ValueError):
            etf_flow.request("all")


if __name__ == "__main__":
    unittest.main()
