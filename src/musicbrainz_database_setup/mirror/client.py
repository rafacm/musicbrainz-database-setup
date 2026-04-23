from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx

USER_AGENT = "musicbrainz-database-setup/0.1 (+https://github.com/)"
DEFAULT_TIMEOUT = httpx.Timeout(30.0, read=120.0)


@contextmanager
def http_client(
    *,
    timeout: httpx.Timeout | None = None,
    follow_redirects: bool = True,
) -> Iterator[httpx.Client]:
    with httpx.Client(
        timeout=timeout or DEFAULT_TIMEOUT,
        follow_redirects=follow_redirects,
        headers={"User-Agent": USER_AGENT},
        http2=False,
    ) as client:
        yield client
