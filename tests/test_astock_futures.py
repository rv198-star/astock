"""Synthetic contract identity, missing-price and date-label regression cases."""

import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal

from astock import RawObservation, Status, futures

STAMP = datetime(2001, 2, 3, tzinfo=timezone.utc)


def raw(**changes):
    row = [""] * 44
    for i, value in {
        0: "PVC0103",
        1: "230000",
        2: "5101",
        3: "5120",
        4: "5090",
        8: "5105.25",
        10: "5000",
        13: "12345",
        14: "4000",
        15: "连",
        16: "PVC",
        17: "2001-02-02",
    }.items():
        row[i] = value
    for key, value in changes.items():
        row[int(key[1:])] = value
    body = ('var hq_str_nf_V0103="' + ",".join(row) + '";\n').encode("gb18030")
    return RawObservation(futures.request("V0103"), STAMP, body, 200)


class FuturesTests(unittest.TestCase):
    def parse(self, value):
        return futures.parse(value, contract="V0103")

    def test_exact_contract_price_and_labels_remain_independent(self):
        result = self.parse(raw())
        self.assertEqual(result.status, Status.SUCCESS)
        row = result.records[0]
        self.assertEqual((row.contract, row.venue, row.delivery_month), ("V0103", "DCE", "2001-03"))
        self.assertEqual(row.last_native, Decimal("5105.25"))
        self.assertEqual(row.source_date_label, date(2001, 2, 2))
        self.assertEqual(row.source_time_text, "230000")
        self.assertEqual(dict(row.unqualified_fields)[14], "4000")
        self.assertFalse(hasattr(row, "source_clock"))

    def test_no_continuous_series_or_multiple_contracts(self):
        for value in ("", "V0", "V2300", "V2313", "M2701", "v2701", "V2701,V2705", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                futures.request(value)

    def test_body_symbol_and_native_identity_must_agree(self):
        for value in (
            raw(f0="PVC0104"),
            raw(f15="郑"),
            raw(f16="豆粕"),
            replace(raw(), body=raw().body.replace(b"V0103", b"V0104")),
        ):
            with self.subTest(value=value.body):
                self.assertEqual(self.parse(value).status, Status.FAILED)

    def test_zero_last_does_not_fall_back_to_previous_settlement(self):
        for changes in (
            {"f8": "0"},
            {"f8": "NaN"},
            {"f8": "5121"},
            {"f2": "5089"},
            {"f4": "5130"},
            {"f8": "-1"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(self.parse(raw(**changes)).status, Status.FAILED)

    def test_schema_changes_and_invalid_time_fail_closed(self):
        for value in (
            raw(f1="2300"),
            raw(f1="240000"),
            raw(f17="2001-02-30"),
            replace(raw(), body=raw().body.replace(b'";\n', b',";\n')),
        ):
            with self.subTest(value=value.body):
                self.assertEqual(self.parse(value).status, Status.FAILED)

    def test_empty_and_transport_failures_are_distinct(self):
        empty = replace(raw(), body=b'var hq_str_nf_V0103="";')
        self.assertEqual(self.parse(empty).status, Status.EMPTY)
        for value in (
            replace(empty, http_status=403),
            replace(raw(), complete=False),
            replace(raw(), error="SOURCE_OPERATION_TIMEOUT"),
        ):
            self.assertEqual(self.parse(value).status, Status.FAILED)

    def test_changed_referer_cannot_reuse_request_identity(self):
        value = raw()
        value = replace(value, request=replace(value.request, headers=()))
        self.assertEqual(self.parse(value).reason, "SOURCE_IDENTITY_MISMATCH")
