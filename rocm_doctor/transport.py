from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .schemas import RetryPolicy


@dataclass
class HTTPResult:
    ok: bool
    payload: Any = None
    error: str = ""
    status_code: int | None = None
    attempts: int = 1
    raw: str = ""


def request_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: float = 1.5,
    headers: dict[str, str] | None = None,
    retry: RetryPolicy | None = None,
) -> HTTPResult:
    policy = retry or RetryPolicy()
    attempts = max(1, int(policy.max_attempts))
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    last = HTTPResult(ok=False, error="request was not attempted", attempts=0)
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError as exc:
                    last = HTTPResult(
                        ok=False,
                        payload=raw[:500],
                        error=f"invalid JSON response: {exc}",
                        status_code=response.status,
                        attempts=attempt,
                        raw=raw[:500],
                    )
                    if policy.retry_on_invalid_json and attempt < attempts:
                        _sleep(policy)
                        continue
                    return last
                if response.status >= 400:
                    last = HTTPResult(
                        ok=False,
                        payload=parsed,
                        error=f"HTTP {response.status}",
                        status_code=response.status,
                        attempts=attempt,
                        raw=raw[:500],
                    )
                    if response.status in policy.retry_status_codes and attempt < attempts:
                        _sleep(policy)
                        continue
                    return last
                return HTTPResult(
                    ok=True,
                    payload=parsed,
                    status_code=response.status,
                    attempts=attempt,
                    raw=raw[:500],
                )
        except urllib.error.HTTPError as exc:
            raw = _read_error_body(exc)
            last = HTTPResult(
                ok=False,
                payload=raw[:500],
                error=f"HTTP {exc.code}",
                status_code=exc.code,
                attempts=attempt,
                raw=raw[:500],
            )
            if exc.code in policy.retry_status_codes and attempt < attempts:
                _sleep(policy)
                continue
            return last
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = HTTPResult(ok=False, error=str(exc), attempts=attempt)
            if policy.retry_on_timeout and attempt < attempts:
                _sleep(policy)
                continue
            return last
    return last


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _sleep(policy: RetryPolicy) -> None:
    if policy.backoff_seconds > 0:
        time.sleep(policy.backoff_seconds)
