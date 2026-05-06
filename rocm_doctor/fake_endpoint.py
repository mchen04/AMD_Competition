from __future__ import annotations

import json
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class FakeOpenAIHandler(BaseHTTPRequestHandler):
    server: "FakeOpenAIHTTPServer"

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
        if self.server.failure_mode == "rate_limit_once" and self.server._consume_once("models"):
            self._send_json(429, {"error": {"message": "rate limited once"}})
            return
        self._send_json(
            200,
            {
                "object": "list",
                "data": [
                    {
                        "id": self.server.model_id,
                        "object": "model",
                        "owned_by": "rocm-doctor-fake",
                    }
                ],
            },
        )

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "not found"}})
            return
        if self.server.failure_mode == "chat_invalid_json":
            data = b'{"choices": ['
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.server.failure_mode == "empty_response":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.server.failure_mode == "partial_response":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"choices":[{"message":')
            return
        if self.server.failure_mode == "slow_response":
            time.sleep(self.server.slow_response_seconds)
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or 0))
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": {"message": "invalid json request"}})
            return
        if self.server.failure_mode == "chat_500":
            self._send_json(500, {"error": {"message": "chat endpoint failed"}})
            return
        if self.server.failure_mode in {"hip_oom", "hip_oom_once"}:
            if self.server.failure_mode == "hip_oom_once" and not self.server._consume_once("chat_hip_oom"):
                pass  # already consumed → fall through to healthy below
            else:
                self._send_json(
                    500,
                    {
                        "error": {
                            "type": "RuntimeError",
                            "message": (
                                "RuntimeError: HIP error: hipErrorOutOfMemory: "
                                "ROCm out of memory while allocating KV cache on MI300X"
                            ),
                        }
                    },
                )
                return
        if self.server.failure_mode in {"max_model_len_exceeded", "max_model_len_exceeded_once"}:
            if self.server.failure_mode == "max_model_len_exceeded_once" and not self.server._consume_once("chat_max_model_len"):
                pass
            else:
                self._send_json(
                    400,
                    {
                        "error": {
                            "type": "BadRequestError",
                            "message": (
                                "This model's maximum context length is "
                                "8192 tokens. However, you requested context length of "
                                "16384 tokens which is greater than the maximum max_model_len."
                            ),
                        }
                    },
                )
                return
        if self.server.failure_mode == "rate_limit":
            self._send_json(429, {"error": {"message": "rate limited"}})
            return
        if self.server.failure_mode == "stream_interrupt" and payload.get("stream"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b"data: {\"choices\":[")
            return
        if payload.get("stream") and not payload.get("tools"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            stream = (
                'data: {"id":"chatcmpl_rocm_doctor_fake_stream","object":"chat.completion.chunk",'
                '"model":"%s","choices":[{"index":0,"delta":{"role":"assistant"}}]}\n\n'
                'data: {"id":"chatcmpl_rocm_doctor_fake_stream","object":"chat.completion.chunk",'
                '"model":"%s","choices":[{"index":0,"delta":{"content":"ROCM_DOCTOR_OK"},'
                '"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n"
            ) % (self.server.model_id, self.server.model_id)
            self.wfile.write(stream.encode("utf-8"))
            return
        if payload.get("tools"):
            parser = self.headers.get("X-ROCm-Doctor-Tool-Parser", "")
            if self.server.failure_mode == "tool_wrong_name":
                self._send_json(200, _tool_call_response(self.server.model_id, name="not_rocm_doctor_ping"))
                return
            if parser == self.server.expected_tool_parser:
                self._send_json(200, _tool_call_response(self.server.model_id))
            else:
                self._send_json(200, _plain_response(self.server.model_id, "plain text; no tool call"))
            return
        if self.server.failure_mode == "hallucinated_tool_call":
            self._send_json(200, _tool_call_response(self.server.model_id))
            return
        if self.server.failure_mode == "empty_chat_content_once" and self.server._consume_once("chat"):
            self._send_json(200, _plain_response(self.server.model_id, ""))
            return
        if self.server.failure_mode == "empty_chat_content":
            self._send_json(200, _plain_response(self.server.model_id, ""))
            return
        if self.server.failure_mode == "instruction_drift":
            self._send_json(200, _plain_response(self.server.model_id, "ROCM_DOCTOR_OK extra text"))
            return
        if self.server.failure_mode == "repetitive_output":
            self._send_json(200, _plain_response(self.server.model_id, "loop " * 20))
            return
        self._send_json(200, _plain_response(self.server.model_id, "ROCM_DOCTOR_OK"))

    def log_message(self, format: str, *args: Any) -> None:
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


class FakeOpenAIHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        model_id: str = "fake-qwen3",
        expected_tool_parser: str = "qwen3",
        failure_mode: str = "healthy",
        slow_response_seconds: float = 2.0,
    ) -> None:
        super().__init__(server_address, FakeOpenAIHandler)
        self.model_id = model_id
        self.expected_tool_parser = expected_tool_parser
        self.failure_mode = failure_mode
        self.slow_response_seconds = slow_response_seconds
        self._once_failures: set[str] = set()

    def _consume_once(self, key: str) -> bool:
        if key in self._once_failures:
            return False
        self._once_failures.add(key)
        return True


class FakeOpenAIServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        model_id: str = "fake-qwen3",
        expected_tool_parser: str = "qwen3",
        failure_mode: str = "healthy",
        slow_response_seconds: float = 2.0,
    ) -> None:
        self._server = FakeOpenAIHTTPServer(
            (host, port),
            model_id=model_id,
            expected_tool_parser=expected_tool_parser,
            failure_mode=failure_mode,
            slow_response_seconds=slow_response_seconds,
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

    def start(self) -> "FakeOpenAIServer":
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> "FakeOpenAIServer":
        return self.start()

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.stop()


def serve_forever(
    host: str = "127.0.0.1",
    port: int = 8000,
    model_id: str = "fake-qwen3",
    expected_tool_parser: str = "qwen3",
    failure_mode: str = "healthy",
    slow_response_seconds: float = 2.0,
) -> None:
    server = FakeOpenAIHTTPServer(
        (host, port),
        model_id=model_id,
        expected_tool_parser=expected_tool_parser,
        failure_mode=failure_mode,
        slow_response_seconds=slow_response_seconds,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _plain_response(model_id: str, content: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl_rocm_doctor_fake",
        "object": "chat.completion",
        "model": model_id,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
    }


def _tool_call_response(model_id: str, name: str = "rocm_doctor_ping") -> dict[str, Any]:
    return {
        "id": "chatcmpl_rocm_doctor_fake_tool",
        "object": "chat.completion",
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_rocm_doctor_ping",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": "{\"status\":\"ok\"}",
                            },
                        }
                    ],
                },
            }
        ],
    }
