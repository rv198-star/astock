"""Synthetic protocol counterexamples; no live vendor data or network requests."""

import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from astock import RawObservation, Status, bonds, capabilities, disclosures, macro, news, quotes


def observation(request, body):
    if not isinstance(body, bytes):
        body = json.dumps(body).encode()
    return RawObservation(request, datetime(2000, 1, 1, tzinfo=timezone.utc), body, 200)


def macro_body(series="cpi"):
    row = {key: 1 for key in macro.REPORTS[series][1]}
    row.update(REPORT_DATE="2000-01-01 00:00:00", TIME="synthetic period")
    return {"success": True, "code": 0, "result": {"data": [row]}}


def bond_body():
    return [{}, [10, [{"ycDefId": bonds.CURVE_ID, "ycDefName": bonds.CURVE_NAME,
                       "worktime": "2000-01-01", "seriesData": [[0, -1], [1, 2]]}]]]


def news_body(channel=2516):
    return {"result": {"status": {"code": 0}, "lid": channel, "data": [
        {"title": "Synthetic item", "url": "https://example.com/item", "ctime": "946684800"}]}}


def disclosure_body():
    return {"totalAnnouncement": 1, "announcements": [{"secCode": "600000", "orgId": "synthetic-org",
            "announcementId": "synthetic-id", "announcementTitle": "Synthetic disclosure",
            "announcementTime": 946684800123,
            "adjunctUrl": "finalpage/2000-01-01/synthetic.PDF"}]}


def quote_body(provider):
    if provider == "eastmoney":
        return {"rc": 0, "data": {"f57": "600519", "f58": "Synthetic", "f43": 2,
                                   "f46": 1, "f44": 3, "f45": 0}}
    if provider == "tencent":
        fields = [""] * 35
        for index, value in {1: "Synthetic", 2: "600519", 3: "2", 5: "1",
                             30: "20000101150000", 33: "3", 34: "0"}.items():
            fields[index] = value
        return ('v_sh600519="' + "~".join(fields) + '";\n').encode()
    fields = [""] * 32
    for index, value in {0: "Synthetic", 1: "1", 3: "2", 4: "3", 5: "0",
                         30: "2000-01-01", 31: "15:00:00"}.items():
        fields[index] = value
    return ('var hq_str_sh600519="' + ",".join(fields) + '";\n').encode()


class ExtendedSourceTests(unittest.TestCase):
    def test_capabilities_are_offline_unique_and_complete(self):
        values = capabilities()
        self.assertEqual(len(values), 15)
        self.assertEqual(len({x.identity for x in values}), 15)

    def test_all_macro_series_preserve_period_and_native_decimal_fields(self):
        for series in macro.REPORTS:
            with self.subTest(series=series):
                result = macro.parse(observation(macro.request(series), macro_body(series)), series)
                self.assertEqual(result.status, Status.SUCCESS)
                row = result.records[0]
                self.assertEqual(row.report_date_text, "2000-01-01 00:00:00")
                self.assertTrue(all(isinstance(value, Decimal) for _, value in row.source_fields))
                self.assertEqual(row.unit_basis, "SOURCE_NATIVE_UNNORMALIZED")

    def test_macro_error_null_and_duplicate_are_not_empty_success(self):
        body = macro_body()
        for mutate in (lambda b: b.update(success=False),
                       lambda b: b["result"].update(data=None),
                       lambda b: b["result"]["data"].append(b["result"]["data"][0])):
            item = json.loads(json.dumps(body))
            mutate(item)
            self.assertEqual(macro.parse(observation(macro.request("cpi"), item), "cpi").status,
                             Status.FAILED)
        body["result"]["data"] = []
        self.assertEqual(macro.parse(observation(macro.request("cpi"), body), "cpi").status,
                         Status.EMPTY)

    def test_macro_bad_numeric_and_date_fail_closed(self):
        for value in (None, True, "NaN", "Infinity", "--"):
            body = macro_body()
            body["result"]["data"][0]["NATIONAL_SAME"] = value
            self.assertEqual(macro.parse(observation(macro.request("cpi"), body), "cpi").status,
                             Status.FAILED)
        body = macro_body()
        body["result"]["data"][0]["REPORT_DATE"] = "2000-02-31 00:00:00"
        self.assertEqual(macro.parse(observation(macro.request("cpi"), body), "cpi").status,
                         Status.FAILED)

    def test_macro_wrong_series_and_page_are_identity_errors(self):
        raw = observation(macro.request("ppi"), macro_body())
        self.assertEqual(macro.parse(raw, "cpi").reason, "SOURCE_IDENTITY_MISMATCH")
        raw = observation(macro.request("cpi", page=2), macro_body())
        self.assertEqual(macro.parse(raw, "cpi").reason, "SOURCE_IDENTITY_MISMATCH")
        for size in (True, 0, 201):
            with self.assertRaises(ValueError):
                macro.request("cpi", page_size=size)

    def test_curve_retains_identity_native_values_and_negative_yield(self):
        result = bonds.parse(observation(bonds.request(), bond_body()))
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.records[0].yield_native, Decimal(-1))
        self.assertEqual(result.records[0].curve_id, bonds.CURVE_ID)

    def test_curve_wrong_identity_malformed_point_and_duplicate_fail(self):
        for key, value in (("ycDefId", "another-curve"), ("ycDefName", "another-name"),
                           ("worktime", "2000-02-31"), ("seriesData", [[1, True]]),
                           ("seriesData", [[1, 2], [1, 3]]), ("seriesData", [])):
            body = bond_body()
            body[1][1][0][key] = value
            self.assertEqual(bonds.parse(observation(bonds.request(), body)).status, Status.FAILED)

    def test_news_keeps_native_creation_clock_and_missing_id(self):
        for channel in (2510, 2516):
            result = news.parse(observation(news.request(channel), news_body(channel)), channel)
            self.assertEqual(result.status, Status.SUCCESS)
            self.assertEqual(result.records[0].source_created_at.year, 2000)
            self.assertIsNone(result.records[0].native_id)
        body = news_body()
        del body["result"]["data"][0]["ctime"]
        result = news.parse(observation(news.request(), body))
        self.assertIsNone(result.records[0].source_created_at)

    def test_news_channel_error_and_invalid_items_are_not_success(self):
        body = news_body(2510)
        self.assertEqual(news.parse(observation(news.request(), body)).reason,
                         "NEWS_CHANNEL_MISMATCH")
        for key, value in (("title", ""), ("url", "javascript:alert(1)"), ("ctime", True),
                           ("ctime", "invalid")):
            body = news_body()
            body["result"]["data"][0][key] = value
            self.assertEqual(news.parse(observation(news.request(), body)).status, Status.FAILED)
        body = news_body()
        body["result"]["data"] = [1]
        self.assertEqual(news.parse(observation(news.request(), body)).status, Status.FAILED)

    def test_disclosure_preserves_milliseconds_even_after_acquisition(self):
        body = disclosure_body()
        result = disclosures.parse(observation(disclosures.request(), body))
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.records[0].source_timestamp_ms, 946684800123)
        self.assertEqual(result.observation.acquired_at.year, 2000)

    def test_disclosure_missing_identity_timestamp_or_unsafe_attachment_rejected(self):
        for key, value in (("secCode", "60000"), ("orgId", ""), ("announcementId", ""),
                           ("announcementTime", True), ("announcementTime", "946684800123"),
                           ("adjunctUrl", "https://evil.example/file.PDF"),
                           ("adjunctUrl", "finalpage/2000-01-01/../secret"),
                           ("adjunctUrl", "//evil.example/file.PDF")):
            body = disclosure_body()
            body["announcements"][0][key] = value
            self.assertEqual(disclosures.parse(observation(disclosures.request(), body)).status,
                             Status.FAILED)

    def test_empty_disclosure_requires_consistent_source_count(self):
        for total, status in ((0, Status.EMPTY), (1, Status.FAILED), (True, Status.FAILED)):
            body = {"totalAnnouncement": total, "announcements": []}
            self.assertEqual(disclosures.parse(observation(disclosures.request(), body)).status,
                             status)

    def test_source_error_codes_require_explicit_integer_success(self):
        body = news_body()
        body["result"]["status"]["code"] = False
        self.assertEqual(news.parse(observation(news.request(), body)).status, Status.FAILED)
        body = macro_body()
        body["code"] = False
        self.assertEqual(macro.parse(observation(macro.request("cpi"), body), "cpi").status,
                         Status.FAILED)
        body = quote_body("eastmoney")
        body["rc"] = False
        self.assertEqual(quotes.parse(observation(quotes.request("eastmoney"), body)).status,
                         Status.FAILED)

    def test_three_quote_contracts_have_explicit_unknown_adjustment(self):
        for provider in ("tencent", "sina", "eastmoney"):
            result = quotes.parse(observation(quotes.request(provider), quote_body(provider)))
            self.assertEqual(result.status, Status.SUCCESS)
            self.assertEqual(result.records[0].last_native, Decimal(2))
            self.assertEqual(result.records[0].adjustment_basis, "UNSPECIFIED_SOURCE_QUOTE")
            if provider == "eastmoney":
                self.assertIsNone(result.records[0].source_clock)
            else:
                self.assertEqual(result.records[0].source_clock.utcoffset().total_seconds(), 28800)

    def test_quote_wrong_security_clock_missing_price_and_bad_ohlc_fail(self):
        for provider in ("tencent", "sina"):
            raw = quote_body(provider).replace(b"sh600519", b"sh600000")
            self.assertEqual(quotes.parse(observation(quotes.request(provider), raw)).status,
                             Status.FAILED)
            raw = quote_body(provider).replace(b"2000", b"9999", 1)
            # A syntactically valid future source clock is retained, not replaced by acquisition.
            result = quotes.parse(observation(quotes.request(provider), raw))
            self.assertEqual(result.records[0].source_clock.year, 9999)
        for key, value in (("f57", "600000"), ("f43", None), ("f43", True), ("f43", 10)):
            body = quote_body("eastmoney")
            body["data"][key] = value
            self.assertEqual(quotes.parse(observation(quotes.request("eastmoney"), body)).status,
                             Status.FAILED)

    def test_failures_preserve_raw_body_and_never_become_empty(self):
        cases = [(bonds.request(), bonds.parse), (disclosures.request(), disclosures.parse),
                 (news.request(), news.parse), (quotes.request("sina"), quotes.parse),
                 (macro.request("cpi"), lambda raw: macro.parse(raw, "cpi"))]
        for request, parse in cases:
            raw = replace(observation(request, b"partial evidence"), complete=False)
            result = parse(raw)
            self.assertEqual(result.status, Status.FAILED)
            self.assertIs(result.observation, raw)
            self.assertEqual(result.records, ())
            self.assertEqual(parse(observation(request, b"<html>challenge</html>")).status,
                             Status.FAILED)


if __name__ == "__main__":
    unittest.main()
