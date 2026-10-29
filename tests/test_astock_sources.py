"""Synthetic source-contract regressions; no network or real financial payloads."""

import hashlib
import json
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from astock import FetchResult, RawObservation, Status, lpr, rss

NOW = datetime(2001, 2, 3, 4, 5, tzinfo=timezone.utc)


def observation(request, body):
    return RawObservation(request, NOW, body, 200)


def rates(rows):
    return json.dumps({"head": {"rep_code": "200"}, "records": rows}).encode()


def row(**overrides):
    return {"showDateCN": "2001-01-20", "1Y": "1.25", "5Y": "2.75", **overrides}


class EvidenceTests(unittest.TestCase):
    def test_request_identity_covers_source_body_and_headers(self):
        request = lpr.request()
        for changed in [
            lpr.request(3),
            replace(request, provider="another-vendor"),
            replace(request, headers=(("Accept", "application/json"),)),
        ]:
            self.assertNotEqual(request.identity, changed.identity)

    def test_raw_identity_and_acquisition_clock_remain_available(self):
        raw = observation(lpr.request(), rates([row()]))
        result = lpr.parse(raw)
        self.assertIs(result.observation, raw)
        self.assertEqual(raw.body_sha256, hashlib.sha256(raw.body).hexdigest())
        self.assertEqual(raw.acquired_at, NOW)
        with self.assertRaisesRegex(ValueError, "TIMEZONE"):
            replace(raw, acquired_at=NOW.replace(tzinfo=None))

    def test_failure_or_empty_cannot_be_labelled_nonempty_success(self):
        raw = observation(lpr.request(), b"")
        with self.assertRaisesRegex(ValueError, "NONEMPTY"):
            FetchResult(raw, Status.SUCCESS, "incorrect")
        with self.assertRaisesRegex(ValueError, "TRANSPORT"):
            FetchResult(replace(raw, error="TLS_VERIFICATION"), Status.EMPTY, "incorrect")


class LprTests(unittest.TestCase):
    def parse(self, rows):
        return lpr.parse(observation(lpr.request(), rates(rows)))

    def test_rates_keep_exact_percent_units_and_effective_date(self):
        result = self.parse([row()])
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertEqual(result.records[0].one_year_percent, Decimal("1.25"))
        self.assertEqual(str(result.records[0].effective_date), "2001-01-20")
        self.assertFalse(hasattr(result.records[0], "knowledge_cutoff"))

    def test_explicit_empty_is_distinct_from_missing_or_failed_payload(self):
        self.assertEqual(self.parse([]).status, Status.EMPTY)
        for body in [
            b"{}",
            b"",
            b"<html>Access denied</html>",
            b'{"head":{"rep_code":"500"},"records":[]}',
        ]:
            self.assertEqual(lpr.parse(observation(lpr.request(), body)).status, Status.FAILED)

    def test_missing_invalid_nonfinite_boolean_or_duplicate_observation_fails(self):
        for rows in [
            [row(**{"1Y": None})],
            [row(**{"1Y": "NaN"})],
            [row(**{"1Y": True})],
            [row(showDateCN="2001-02-30")],
            [row(), row()],
            [row(), row(**{"5Y": "broken"})],
        ]:
            with self.subTest(rows=rows):
                result = self.parse(rows)
                self.assertEqual(result.status, Status.FAILED)
                self.assertEqual(result.records, ())

    def test_wrong_source_and_transport_failure_are_never_substituted(self):
        raw = observation(lpr.request(), rates([row()]))
        for changed in [
            replace(raw, request=replace(raw.request, provider="eastmoney")),
            replace(raw, complete=False),
            replace(raw, http_status=403),
            replace(raw, error="REQUEST_TIMEOUT"),
        ]:
            self.assertEqual(lpr.parse(changed).status, Status.FAILED)


class RssTests(unittest.TestCase):
    def parse(self, body):
        return rss.parse(observation(rss.request(), body))

    def test_unknown_publication_time_is_not_acquisition_time(self):
        result = self.parse(
            b"<rss><channel><item><title>Example</title>"
            b"<link>https://example.org/item</link></item></channel></rss>"
        )
        self.assertEqual(result.status, Status.SUCCESS)
        self.assertIsNone(result.records[0].published_at)
        self.assertIsNone(result.records[0].native_id)
        self.assertEqual(result.observation.acquired_at, NOW)

    def test_rss_and_atom_explicit_offset_times_are_preserved(self):
        bodies = [
            b"""<rss><channel><item><title>Example</title><link>https://example.org/1</link>
                <pubDate>Fri, 02 Feb 2001 01:02:03 GMT</pubDate></item></channel></rss>""",
            b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Example</title>
                <link href="https://example.org/1"/><published>2001-02-02T01:02:03Z</published>
                </entry></feed>""",
        ]
        for body in bodies:
            result = self.parse(body)
            self.assertEqual(result.status, Status.SUCCESS)
            self.assertEqual(
                result.records[0].published_at, datetime(2001, 2, 2, 1, 2, 3, tzinfo=timezone.utc)
            )

    def test_naive_or_unrecognized_time_stays_unknown_with_original_text(self):
        for stamp in ["yesterday", "2001-02-02T01:02:03"]:
            body = (
                "<rss><channel><item><title>Example</title><link>https://example.org/1</link>"
                f"<pubDate>{stamp}</pubDate></item></channel></rss>"
            ).encode()
            result = self.parse(body)
            self.assertIsNone(result.records[0].published_at)
            self.assertEqual(result.records[0].published_text, stamp)

    def test_empty_feed_is_distinct_from_html_truncation_and_bad_items(self):
        self.assertEqual(self.parse(b"<rss><channel/></rss>").status, Status.EMPTY)
        for body in [
            b"<html><title>Login</title></html>",
            b"<rss>",
            b"<rss><channel><item><title>Missing link</title></item></channel></rss>",
        ]:
            self.assertEqual(self.parse(body).status, Status.FAILED)
        raw = observation(rss.request(), b"<rss><channel/></rss>")
        self.assertEqual(rss.parse(replace(raw, complete=False)).status, Status.FAILED)


if __name__ == "__main__":
    unittest.main()
