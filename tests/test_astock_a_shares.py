"""Synthetic scope, units, signed flows and incomplete-page evidence regressions."""

import copy
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from astock import RawObservation, Status
from astock import a_shares as source

START, END = "2001-02-01", "2001-02-02"
STAMP = datetime(2001, 2, 3, tzinfo=timezone.utc)


def margin(**changes):
    return {"SCODE": "600519", "SECUCODE": "600519.SH", "SECNAME": "Synthetic",
            "DATE": END + " 00:00:00", "RZYE": "100.125", "RQYE": "10.25",
            "RZRQYE": "110.375", "RZMRE": "2.125", "RZCHE": "3.125", "RZJME": "-1",
            "RQYL": 200, "RQMCL": 0, "RQCHL": 100, "RQJMG": -100,
            "RZRQYECZ": "89.875", **changes}


def block(**changes):
    return {"SECURITY_CODE": "000001", "SECUCODE": "000001.SZ",
            "SECURITY_NAME_ABBR": "Synthetic", "SECURITY_TYPE": "EQA",
            "SECURITY_TYPE_WEB": "1", "TRADE_DATE": END + " 00:00:00", "DAILY_RANK": 3,
            "DEAL_PRICE": "1.25", "CLOSE_PRICE": "1.30", "DEAL_VOLUME": 20000,
            "DEAL_AMT": "25000", "PREMIUM_RATIO": "-0.038461538462",
            "BUYER_NAME": "Synthetic Buyer", "SELLER_NAME": "Synthetic Seller", **changes}


def raw(kind, rows, total=None, **body_changes):
    count = len(rows) if total is None else total
    request = source.margin_request(start=START, end=END) if kind == "margin" else (
        source.block_request(END)
    )
    body = {"success": True, "code": 0,
            "result": {"data": rows, "count": count, "pages": (count + 1) // 2}, **body_changes}
    return RawObservation(request, STAMP, json.dumps(body).encode(), 200)


class AShareTests(unittest.TestCase):
    def pm(self, value):
        return source.parse_margin(value, start=START, end=END)

    def pb(self, value):
        return source.parse_blocks(value, trade_date=END)

    def test_margin_native_precision_and_signed_flows_are_preserved(self):
        result = self.pm(raw("margin", [margin()], total=1))
        self.assertEqual(result.status, Status.SUCCESS)
        row = result.records[0]
        self.assertEqual(dict(row.source_fields)["RZYE"], Decimal("100.125"))
        self.assertEqual(dict(row.source_fields)["RZJME"], Decimal(-1))
        self.assertEqual(dict(row.source_fields)["RQJMG"], Decimal(-100))
        self.assertNotIn("RZRQYECZ", dict(row.source_fields))
        self.assertFalse(hasattr(row, "publication_at"))

    def test_missing_and_invalid_values_are_not_zero(self):
        for value in (None, "NaN", "", True):
            self.assertEqual(self.pm(raw("margin", [margin(RZYE=value)])).status, Status.FAILED)
        result = self.pm(raw("margin", [margin()]))
        self.assertEqual(dict(result.records[0].source_fields)["RQMCL"], 0)

    def test_margin_inconsistent_totals_or_fractional_shares_are_not_repaired(self):
        for changes in ({"RZRQYE": 5}, {"RZJME": 1}, {"RQJMG": 100}, {"RQYL": "0.5"}):
            self.assertEqual(self.pm(raw("margin", [margin(**changes)])).status, Status.FAILED)

    def test_margin_security_date_and_order_must_match_request(self):
        for rows in ([margin(SCODE="600000")], [margin(SECUCODE="600519.SZ")],
                     [margin(DATE="2001-02-03 00:00:00")],
                     [margin(DATE=START + " 00:00:00"), margin()], [margin(), margin()]):
            self.assertEqual(self.pm(raw("margin", rows)).status, Status.FAILED)

    def test_wide_or_injectable_or_unbounded_requests_are_rejected(self):
        for kwargs in ({"code": "600519&x=1"}, {"code": "AAPL"}, {"limit": True},
                       {"limit": 21}, {"start": "2001-01-01", "end": END},
                       {"start": END, "end": START}, {"start": "2001-2-01"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                source.margin_request(**kwargs)
        with self.assertRaises(ValueError):
            source.block_request("2001-02-02')(")

    def test_blocks_keep_share_amount_and_already_fractional_premium(self):
        result = self.pb(raw("block", [block()], total=1))
        self.assertEqual(result.status, Status.SUCCESS)
        fields = dict(result.records[0].source_fields)
        self.assertEqual(fields["DEAL_VOLUME"], 20000)
        self.assertEqual(fields["DEAL_AMT"], 25000)
        self.assertEqual(fields["PREMIUM_RATIO"], Decimal("-0.038461538462"))

    def test_blocks_reject_other_assets_venue_dates_and_units(self):
        for changes in ({"SECURITY_TYPE": "BOND"}, {"SECURITY_TYPE_WEB": "2"},
                        {"SECUCODE": "000001.SH"}, {"TRADE_DATE": START + " 00:00:00"},
                        {"DEAL_AMT": "NaN"}, {"DEAL_VOLUME": "0.5"}, {"DEAL_PRICE": 0}):
            self.assertEqual(self.pb(raw("block", [block(**changes)])).status, Status.FAILED)

    def test_bounded_page_is_partial_and_count_drift_fails(self):
        result = self.pb(raw("block", [block(), block(DAILY_RANK=4)], total=68))
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual((result.records[0].reported_total, result.records[0].reported_pages),
                         (68, 34))
        self.assertEqual(self.pb(raw("block", [block()], total=68)).status, Status.FAILED)
        value = raw("block", [block()])
        body = json.loads(value.body)
        body["result"]["pages"] = 2
        self.assertEqual(self.pb(replace(value, body=json.dumps(body).encode())).status, Status.FAILED)

    def test_reported_block_amount_is_not_reconstructed_from_price_and_volume(self):
        result = self.pb(raw("block", [block(DEAL_AMT="25000.5")]))
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(dict(result.records[0].source_fields)["DEAL_AMT"], Decimal("25000.5"))

    def test_empty_transport_and_publisher_failure_remain_distinct(self):
        for kind, parse in (("margin", self.pm), ("block", self.pb)):
            empty = raw(kind, [])
            self.assertEqual(parse(empty).status, Status.EMPTY)
            for bad in (replace(empty, http_status=403), replace(empty, complete=False),
                        raw(kind, [], success=False)):
                self.assertEqual(parse(bad).status, Status.FAILED)

    def test_headers_and_request_scope_are_part_of_identity(self):
        for kind, parse in (("margin", self.pm), ("block", self.pb)):
            value = raw(kind, [])
            changed = replace(value, request=replace(value.request, headers=()))
            self.assertEqual(parse(changed).reason, "SOURCE_IDENTITY_MISMATCH")

    def test_malformed_optional_unqualified_field_cannot_block_good_units(self):
        row = copy.deepcopy(margin(RZRQYECZ="unproven"))
        self.assertEqual(self.pm(raw("margin", [row])).status, Status.SUCCESS)
