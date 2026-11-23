"""Small JSON-over-HTTPS client with retries, standard library only."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

USER_AGENT = "Mozilla/5.0 (compatible; portfolio-research)"
RETRY_STATUS = {429, 500, 502, 503, 504}

Opener = Callable[..., Any]


def fetch_json(
    url: str,
    *,
    timeout: float = 20.0,
    retries: int = 3,
    backoff: float = 2.0,
    opener: Opener = urllib.request.urlopen,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """GET ``url`` and decode JSON, retrying on rate limits, server errors and timeouts.

    Waits ``backoff``, ``2 * backoff``, ... seconds between attempts. Errors that a retry
    cannot fix (404, 401, invalid JSON) are raised at once.

    Parameters
    ----------
    url : str
        HTTPS URL.
    timeout : float, default 20
        Seconds per attempt.
    retries : int, default 3
        Extra attempts after the first.
    backoff : float, default 2
        Base wait in seconds.
    opener, sleep
        Injected for tests; default to the standard library.

    Returns
    -------
    Any
        The decoded JSON.

    Raises
    ------
    ConnectionError
        When every attempt failed, with the last reason.
    ValueError
        If the body is not JSON.

    """
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    last_error = ""
    for attempt in range(retries + 1):
        try:
            with opener(request, timeout=timeout) as response:
                body = response.read()
            return json.loads(body)
        except urllib.error.HTTPError as error:
            error.close()  # the error carries the open response; release the socket
            if error.code not in RETRY_STATUS:
                raise ConnectionError(f"HTTP {error.code} from {url}") from error
            last_error = f"HTTP {error.code}"
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = str(getattr(error, "reason", error))
        except json.JSONDecodeError as error:
            raise ValueError(f"response from {url} is not JSON") from error
        if attempt < retries:
            sleep(backoff * 2**attempt)
    raise ConnectionError(f"{last_error} after {retries + 1} attempts: {url}")
