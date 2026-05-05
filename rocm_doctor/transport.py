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
                content_type = response.headers.get("Content-Type", "")
                try:
                    parsed = _parse_response(raw, content_type)
                except (json.JSONDecodeError, ValueError) as exc:
                    last = HTTPResult(
                        ok=False,
                        payload=raw[:500],
                        error=f"invalid response: {exc}",
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


def _parse_response(raw: str, content_type: str) -> Any:
    if "text/event-stream" in content_type or raw.lstrip().startswith("data:"):
        return _parse_openai_stream(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON response: {exc}") from exc


def _parse_openai_stream(raw: str) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            continue
        if not stripped.startswith("data:"):
            continue
        data = stripped.removeprefix("data:").strip()
        if data == "[DONE]":
            break
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid streaming JSON chunk: {exc}") from exc
        if isinstance(chunk, dict):
            chunks.append(chunk)
    if not chunks:
        raise ValueError("streaming response did not contain JSON chunks")

    content_parts: list[str] = []
    tool_calls: list[Any] = []
    role = "assistant"
    finish_reason: str | None = None
    first = chunks[0]
    last = chunks[-1]
    for chunk in chunks:
        choices = chunk.get("choices", [])
        if not choices:
            continue
        choice = choices[0]
        delta = choice.get("delta") or choice.get("message") or {}
        if isinstance(delta, dict):
            if delta.get("role"):
                role = str(delta["role"])
            if delta.get("content") is not None:
                content_parts.append(str(delta["content"]))
            if delta.get("tool_calls"):
                tool_calls.extend(delta["tool_calls"])
        if choice.get("finish_reason"):
            finish_reason = str(choice["finish_reason"])

    message: dict[str, Any] = {"role": role, "content": "".join(content_parts)}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": first.get("id", "stream"),
        "object": "chat.completion",
        "created": last.get("created") or first.get("created"),
        "model": last.get("model") or first.get("model"),
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    }
