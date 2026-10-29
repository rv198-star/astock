"""CNINFO index metadata only. The source timestamp is retained at millisecond precision."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlencode, urlsplit

from . import _parsing as p
from .contracts import FetchResult, RawObservation, SourceRequest, Status


@dataclass(frozen=True)
class Disclosure:
    security_code: str
    organization_id: str
    announcement_id: str
    title: str
    source_timestamp_ms: int
    attachment_path: str


def request() -> SourceRequest:
    fields = {"pageNum": 1, "pageSize": 2, "column": "sse", "tabName": "fulltext",
              "stock": "", "searchkey": "年度报告", "plate": "", "seDate": ""}
    return SourceRequest("cninfo", "disclosure.index", "POST",
                         "https://www.cninfo.com.cn/new/hisAnnouncement/query",
                         urlencode(fields).encode(),
                         (("Content-Type", "application/x-www-form-urlencoded"),
                          ("Referer", "https://www.cninfo.com.cn/")))


def parse(raw: RawObservation) -> FetchResult[Disclosure]:
    failed = p.preflight(raw, request())
    if failed is not None:
        return failed
    try:
        data = p.json_body(raw)
        rows = data["announcements"]
        if not isinstance(rows, list):
            raise TypeError("ANNOUNCEMENTS_NOT_LIST")
        total = data["totalAnnouncement"]
        if type(total) is not int or total < len(rows) or (not rows and total > 0):
            raise ValueError("INCONSISTENT_DISCLOSURE_COUNT")
        records = []
        for row in rows:
            code = p.text(row["secCode"])
            if not re.fullmatch(r"[0-9]{6}", code):
                raise ValueError("INVALID_SECURITY_CODE")
            clock = row["announcementTime"]
            if type(clock) is not int or clock <= 0:
                raise ValueError("INVALID_SOURCE_TIMESTAMP_MS")
            path = p.text(row["adjunctUrl"])
            url = urlsplit(path)
            if (url.scheme or url.netloc or url.query or url.fragment or "\\" in path
                    or path.startswith("/") or ".." in PurePosixPath(path).parts
                    or not re.fullmatch(r"finalpage/[0-9-]+/[A-Za-z0-9._-]+", path)):
                raise ValueError("UNSAFE_ATTACHMENT_PATH")
            records.append(Disclosure(code, p.text(row["orgId"]), p.text(row["announcementId"]),
                                      p.text(row["announcementTitle"]), clock, path))
        if len({x.announcement_id for x in records}) != len(records):
            return FetchResult(raw, Status.FAILED, "DUPLICATE_ANNOUNCEMENT_ID")
    except (ValueError, KeyError, TypeError):
        return FetchResult(raw, Status.FAILED, "INVALID_DISCLOSURE_SCHEMA")
    return p.result(raw, records)
