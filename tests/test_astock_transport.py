"""Transport regression cases verify that a response cannot acquire false success."""

import socket
import unittest
from unittest.mock import MagicMock, patch

import requests

from astock import lpr
from astock.transport import fetch

PUBLIC = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))]


class TransportTests(unittest.TestCase):
    def response(self, status, blocks):
        session, response = MagicMock(), MagicMock()
        session.__enter__.return_value = session
        response.__enter__.return_value = response
        response.status_code = status
        response.iter_content.return_value = iter(blocks)
        session.request.return_value = response
        return session

    def test_tls_error_is_one_failed_request_without_http_fallback(self):
        session = self.response(200, [])
        session.request.side_effect = requests.exceptions.SSLError("synthetic")
        with (
            patch("astock.transport.socket.getaddrinfo", return_value=PUBLIC),
            patch("requests.Session", return_value=session),
        ):
            raw = fetch(lpr.request())
        self.assertEqual(raw.error, "TLS_VERIFICATION")
        self.assertEqual(session.request.call_count, 1)
        self.assertEqual(session.request.call_args.args[1], lpr.URL)
        self.assertFalse(session.trust_env)

    def test_oversized_body_and_redirect_are_explicit_failures(self):
        for status, blocks, expected in [
            (200, [b"abc", b"def"], "RESPONSE_LIMIT"),
            (302, [b"moved"], "REDIRECT_NOT_FOLLOWED"),
        ]:
            session = self.response(status, blocks)
            with (
                patch("astock.transport.socket.getaddrinfo", return_value=PUBLIC),
                patch("requests.Session", return_value=session),
            ):
                raw = fetch(lpr.request(), max_bytes=5)
            self.assertEqual(raw.error, expected)
            self.assertLessEqual(len(raw.body), 5)
            self.assertFalse(session.request.call_args.kwargs["allow_redirects"])

    def test_private_source_address_is_rejected_before_connecting(self):
        addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with (
            patch("astock.transport.socket.getaddrinfo", return_value=addresses),
            patch("requests.Session") as session,
        ):
            raw = fetch(lpr.request())
        session.assert_not_called()
        self.assertEqual(raw.error, "NONPUBLIC_SOURCE_ADDRESS")


if __name__ == "__main__":
    unittest.main()
