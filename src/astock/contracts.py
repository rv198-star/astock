"""Evidence contracts. Acquisition clocks confer no historical PIT admission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar
from urllib.parse import urlsplit

T = TypeVar("T")


class Status(str, Enum):
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    FAILED = "FAILED"


@dataclass(frozen=True)
class SourceRequest:
    provider: str
    capability: str
    method: str
    url: str
    body: bytes = b""
    headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self):
        url = urlsplit(self.url)
        if (
            not self.provider
            or not self.capability
            or self.method not in {"GET", "POST"}
            or url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.fragment
        ):
            raise ValueError("INVALID_SOURCE_REQUEST")

    @property
    def identity(self) -> str:
        value = {
            "provider": self.provider,
            "capability": self.capability,
            "method": self.method,
            "url": self.url,
            "body_sha256": hashlib.sha256(self.body).hexdigest(),
            "headers": sorted(self.headers),
        }
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class RawObservation:
    request: SourceRequest
    acquired_at: datetime
    body: bytes
    http_status: int | None
    complete: bool = True
    error: str | None = None

    def __post_init__(self):
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise ValueError("ACQUISITION_CLOCK_REQUIRES_TIMEZONE")

    @property
    def body_sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()


@dataclass(frozen=True)
class FetchResult(Generic[T]):
    observation: RawObservation
    status: Status
    reason: str
    records: tuple[T, ...] = ()

    def __post_init__(self):
        if not isinstance(self.status, Status) or not self.reason:
            raise ValueError("EXPLICIT_RESULT_STATUS_REQUIRED")
        if (self.status == Status.SUCCESS) != bool(self.records):
            raise ValueError("SUCCESS_REQUIRES_NONEMPTY_RECORDS")
        if self.status != Status.FAILED and (
            self.observation.error
            or not self.observation.complete
            or self.observation.http_status != 200
        ):
            raise ValueError("FAILED_TRANSPORT_CANNOT_SUCCEED")


def transport_failure(raw: RawObservation) -> FetchResult | None:
    if raw.error:
        return FetchResult(raw, Status.FAILED, raw.error)
    if not raw.complete:
        return FetchResult(raw, Status.FAILED, "INCOMPLETE_RESPONSE")
    if raw.http_status != 200:
        return FetchResult(raw, Status.FAILED, "HTTP_STATUS")
    return None
