from __future__ import annotations

import json
import time
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


ADVERSARIAL_FAILURE_MODES = (
    "healthy",
    "models_500",
    "chat_500",
    "chat_invalid_json",
    "empty_response",
    "partial_response",
    "rate_limit",
    "rate_limit_once",
    "slow_response",
    "drop_connection",
    "empty_chat_content",
    "empty_chat_content_once",
    "instruction_drift",
    "hallucinated_tool_call",
    "repetitive_output",
    "stream_interrupt",
)


class AdversarialProxyHandler(BaseHTTPRequestHandler):
    server: "AdversarialProxyHTTPServer"

    def do_GET(self) -> None:
        if self.path != "/v1/models":
            self._send_json(404, {"error": {"message": "not found"}})
            return
        if self.server.failure_mode == "models_500":
            self._send_json(500, {"error": {"message": "models endpoint failed"}})
            return
        if self.server.failure_mode == "rate_limit":
            self._send_json(429, {"error": {"message": "rate limited"}})
            return
        if self.server.failure_mode == "rate_limit_once" and self.server.consume_once("models"):
            self._send_json(429, {"error": {"message": "rate limited once"}})
            return
        self._forward("GET")

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "not found"}})
            return
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        mode = self.server.failure_mode
        if mode == "slow_response":
            time.sleep(self.server.slow_response_seconds)
        if mode == "drop_connection":
            self.close_connection = True
            return
        if mode in {
            "chat_invalid_json",
            "empty_response",
            "partial_response",
            "empty_chat_content",
            "instruction_drift",
            "hallucinated_tool_call",
            "repetitive_output",
        }:
            self._maybe_forward_before_failure(body)
        if mode == "chat_invalid_json":
            data = b'{"choices": ['
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if mode == "empty_response":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if mode == "partial_response":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":')
            return
        if mode == "chat_500":
            self._send_json(500, {"error": {"message": "chat endpoint failed"}})
            return
        if mode == "rate_limit":
            self._send_json(429, {"error": {"message": "rate limited"}})
            return
        if mode == "rate_limit_once" and self.server.consume_once("chat"):
            self._send_json(429, {"error": {"message": "rate limited once"}})
            return
        if mode == "stream_interrupt" and _payload_streams(body):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"choices":[{"delta":{"content":"ROC')
            return
        if mode == "hallucinated_tool_call":
            self._send_json(200, _tool_call_response(self.server.model_id))
            return
        if mode == "empty_chat_content_once" and self.server.consume_once("chat"):
            self._send_json(200, _plain_response(self.server.model_id, ""))
            return
        if mode == "empty_chat_content":
            self._send_json(200, _plain_response(self.server.model_id, ""))
            return
        if mode == "instruction_drift":
            self._send_json(200, _plain_response(self.server.model_id, "ROCM_DOCTOR_OK extra text"))
            return
        if mode == "repetitive_output":
            self._send_json(200, _plain_response(self.server.model_id, "loop " * 20))
            return
        self._forward("POST", body)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _maybe_forward_before_failure(self, body: bytes) -> None:
        if self.server.forward_before_failure:
            try:
                self.server.forward("POST", self.path, body, dict(self.headers))
            except OSError:
                return

    def _forward(self, method: str, body: bytes | None = None) -> None:
        try:
            status, headers, response_body = self.server.forward(method, self.path, body, dict(self.headers))
        except urllib.error.HTTPError as exc:
            response_body = exc.read()
            self.send_response(exc.code)
            for key, value in exc.headers.items():
                if key.lower() not in {"connection", "transfer-encoding"}:
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(response_body)
            return
        except OSError as exc:
            self._send_json(502, {"error": {"message": f"upstream request failed: {exc}"}})
            return
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() not in {"connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(response_body)
        except BrokenPipeError:
            return

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except BrokenPipeError:
            return


class AdversarialProxyHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        upstream_base_url: str,
        model_id: str = "qwen3:0.6b",
        failure_mode: str = "healthy",
        slow_response_seconds: float = 2.0,
        upstream_timeout_seconds: float = 60.0,
        forward_before_failure: bool = False,
    ) -> None:
        super().__init__(server_address, AdversarialProxyHandler)
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.model_id = model_id
        self.failure_mode = failure_mode
        self.slow_response_seconds = slow_response_seconds
        self.upstream_timeout_seconds = upstream_timeout_seconds
        self.forward_before_failure = forward_before_failure
        self.upstream_requests: list[dict[str, Any]] = []
        self._once_failures: set[str] = set()

    def consume_once(self, key: str) -> bool:
        if key in self._once_failures:
            return False
        self._once_failures.add(key)
        return True

    def forward(
        self,
        method: str,
        path: str,
        body: bytes | None,
        incoming_headers: dict[str, str],
    ) -> tuple[int, dict[str, str], bytes]:
        suffix = path.removeprefix("/v1")
        url = f"{self.upstream_base_url}{suffix}"
        headers = {
            key: value
            for key, value in incoming_headers.items()
            if key.lower() not in {"host", "content-length", "connection"}
        }
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        self.upstream_requests.append({"method": method, "path": path, "url": url})
        with urllib.request.urlopen(request, timeout=self.upstream_timeout_seconds) as response:
            return response.status, dict(response.headers.items()), response.read()


class AdversarialProxyServer:
    def __init__(
        self,
        upstream_base_url: str,
        host: str = "127.0.0.1",
        port: int = 0,
        model_id: str = "qwen3:0.6b",
        failure_mode: str = "healthy",
        slow_response_seconds: float = 2.0,
        upstream_timeout_seconds: float = 60.0,
        forward_before_failure: bool = False,
    ) -> None:
        self._server = AdversarialProxyHTTPServer(
            (host, port),
            upstream_base_url=upstream_base_url,
            model_id=model_id,
            failure_mode=failure_mode,
            slow_response_seconds=slow_response_seconds,
            upstream_timeout_seconds=upstream_timeout_seconds,
            forward_before_failure=forward_before_failure,
        )
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/v1"

    @property
    def upstream_request_count(self) -> int:
        return len(self._server.upstream_requests)

    @property
    def upstream_requests(self) -> list[dict[str, Any]]:
        return list(self._server.upstream_requests)

    def start(self) -> "AdversarialProxyServer":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> "AdversarialProxyServer":
        return self.start()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()


def serve_forever(
    upstream_base_url: str,
    host: str = "127.0.0.1",
    port: int = 8001,
    model_id: str = "qwen3:0.6b",
    failure_mode: str = "healthy",
    slow_response_seconds: float = 2.0,
    upstream_timeout_seconds: float = 60.0,
    forward_before_failure: bool = False,
) -> None:
    server = AdversarialProxyHTTPServer(
        (host, port),
        upstream_base_url=upstream_base_url,
        model_id=model_id,
        failure_mode=failure_mode,
        slow_response_seconds=slow_response_seconds,
        upstream_timeout_seconds=upstream_timeout_seconds,
        forward_before_failure=forward_before_failure,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _payload_streams(body: bytes) -> bool:
    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return False
    return bool(payload.get("stream"))


def _plain_response(model_id: str, content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl_rocm_doctor_adversarial",
        "object": "chat.completion",
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


def _tool_call_response(model_id: str, name: str = "rocm_doctor_ping") -> dict[str, Any]:
    return {
        "id": "chatcmpl_rocm_doctor_adversarial_tool",
        "object": "chat.completion",
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_rocm_doctor_ping",
                            "type": "function",
                            "function": {"name": name, "arguments": "{\"status\":\"ok\"}"},
                        }
                    ],
                },
            }
        ],
    }
