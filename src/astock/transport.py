"""One bounded HTTPS request: no retries, redirects, proxy inheritance or fallback."""

import ipaddress
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from .contracts import RawObservation, SourceRequest


def fetch(request: SourceRequest, *, max_bytes: int = 262144) -> RawObservation:
    import requests

    if max_bytes < 1:
        raise ValueError("POSITIVE_RESPONSE_LIMIT_REQUIRED")
    body = b""
    status = None
    error = None
    complete = True
    started = time.monotonic()
    try:
        url = urlsplit(request.url)
        addresses = socket.getaddrinfo(url.hostname, url.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
            raise ValueError("NONPUBLIC_SOURCE_ADDRESS")
        with requests.Session() as session:
            session.trust_env = False
            headers = {"User-Agent": "astock-sources/0.1", "Accept": "*/*"}
            headers.update(request.headers)
            with session.request(
                request.method,
                request.url,
                data=request.body or None,
                headers=headers,
                timeout=(3, 5),
                allow_redirects=False,
                stream=True,
            ) as response:
                status = response.status_code
                if status != 200:
                    error = "REDIRECT_NOT_FOLLOWED" if 300 <= status < 400 else "HTTP_STATUS"
                for block in response.iter_content(16384):
                    if len(body) + len(block) > max_bytes:
                        body += block[: max_bytes - len(body)]
                        complete, error = False, "RESPONSE_LIMIT"
                        break
                    body += block
                    if time.monotonic() - started > 12:
                        complete, error = False, "BODY_TIME_LIMIT"
                        break
    except requests.exceptions.SSLError:
        complete, error = False, "TLS_VERIFICATION"
    except requests.exceptions.Timeout:
        complete, error = False, "REQUEST_TIMEOUT"
    except requests.exceptions.RequestException:
        complete, error = False, "REQUEST_FAILED"
    except (OSError, ValueError) as exc:
        complete = False
        error = str(exc) if isinstance(exc, ValueError) else "SOURCE_ADDRESS_ERROR"
    return RawObservation(request, datetime.now(timezone.utc), body, status, complete, error)
