# ROCm Doctor Incident Report

- Incident ID: `20260506T040955Z`
- Created: `2026-05-06T04:09:55Z`
- Config: `/Users/michaelchen/Downloads/AMD_Competition/demo/.rocm-doctor.dashboard.yaml`
- Model provider: `ollama-qwen3-0-6b`
- Provider adapter: `openai-compatible`
- Runtime type: `ollama`
- Skipped checks: `rocm_device_flags, tool_call_parser`
- Failure class: `provider_skipped`
- Provider: `anthropic`
- Suspected cause: Optional provider is unavailable in this environment.
- Repair recipe: ``
- Repair applied: `False`
- Repair rejected: `False`
- Verification healthy: `False`

## Evidence

### Before

```json
{
  "endpoint": {
    "chat": {
      "attempts": 1,
      "error": "skipped because models check failed",
      "ok": false,
      "response": null,
      "status_code": null
    },
    "configured_base_url": "http://127.0.0.1:11435/v1",
    "expected_base_url": "http://127.0.0.1:11434/v1",
    "missing_rocm_device_flags": [],
    "models": {
      "attempts": 2,
      "error": "<urlopen error [Errno 61] Connection refused>",
      "ok": false,
      "response": null,
      "status_code": null
    },
    "profile": {
      "adapter": "openai-compatible",
      "base_url": "http://127.0.0.1:11435/v1",
      "capabilities": {
        "chat_completions": true,
        "context_length": true,
        "models": true,
        "restart": false,
        "rocm_device_flags": false,
        "tool_calls": false
      },
      "endpoint_protocol": "openai-compatible",
      "expected_base_url": "http://127.0.0.1:11434/v1",
      "expected_tool_parser": "",
      "health_probes": [
        "endpoint_models",
        "chat_completion",
        "context_length"
      ],
      "id": "ollama-qwen3-0-6b",
      "known_failure_signatures": {
        "context_length_too_large": [
          "max_model_len exceeds safe_max_model_len"
        ],
        "wrong_endpoint_port": [
          "GET /v1/models failed",
          "configured URL differs from expected URL"
        ]
      },
      "max_model_len": 1024,
      "model_name": "qwen3:0.6b",
      "request_timeout_seconds": 30.0,
      "retry": {
        "backoff_seconds": 0.25,
        "max_attempts": 2,
        "retry_on_invalid_json": true,
        "retry_on_timeout": true,
        "retry_status_codes": [
          408,
          409,
          429,
          500,
          502,
          503,
          504
        ]
      },
      "runtime_type": "ollama",
      "safe_max_model_len": 2048,
      "safe_repair_recipes": [
        "noop",
        "retry_without_config_change",
        "update_endpoint_url",
        "increase_health_max_tokens",
        "lower_health_max_tokens",
        "increase_timeout",
        "increase_retry_backoff",
        "disable_streaming",
        "switch_prompt_template",
        "fallback_model_provider",
        "restore_last_known_good_config",
        "tighten_expected_health_response",
        "lower_max_model_len"
      ],
      "skip_reasons": {
        "restart": "ROCm Doctor does not control the local Ollama service",
        "rocm_device_flags": "local Ollama does not use ROCm container device flags",
        "tool_calls": "native tool-call output is not required for this tiny Ollama profile"
      },
      "stream": false,
      "templates": {
        "health_chat": "../templates/health_chat.j2",
        "health_chat_fallbacks": [
          "../templates/health_chat.qwen_strict.j2",
          "../templates/health_chat.no_reasoning.j2",
          "../templates/health_chat.minimal.j2"
        ],
        "tool_call": "../templates/tool_call_prompt.j2"
      },
      "tool_check_enabled": false,
      "tool_parser": "",
      "tool_parser_header": "X-ROCm-Doctor-Tool-Parser",
      "validation": {
        "expected_health_response": "ROCM_DOCTOR_OK",
        "health_max_tokens": 256,
        "health_response_match": "case_insensitive",
        "max_health_response_chars": 160,
        "max_repeated_token_count": 8
      },
      "wrong_base_url": "http://127.0.0.1:11435/v1"
    },
    "skipped_checks": {
      "rocm_device_flags": "local Ollama does not use ROCm container device flags",
      "tool_call_parser": "tool calling is disabled for this model provider"
    },
    "tool_call": {}
  },
  "health": {
    "checks": {
      "chat_completion": false,
      "context_length": true,
      "endpoint_models": false,
      "rocm_device_flags": true,
      "tool_call_parser": true
    },
    "errors": [
      "GET /v1/models failed: <urlopen error [Errno 61] Connection refused>"
    ],
    "healthy": false,
    "summary": "unhealthy: GET /v1/models failed: <urlopen error [Errno 61] Connection refused>"
  },
  "runtime": {
    "capabilities": {
      "chat_completions": true,
      "context_length": true,
      "models": true,
      "restart": false,
      "rocm_device_flags": false,
      "tool_calls": false
    },
    "diagnosis_providers": [
      "anthropic",
      "fake",
      "openai-codex",
      "openai-compatible",
      "rules"
    ],
    "endpoint_protocol": "openai-compatible",
    "hardware": {
      "accelerator": "cpu-or-available-gpu",
      "amd": {
        "benchmark_profile": "tiny-local",
        "device_flags": [],
        "rocm_required": false
      },
      "backend": "local",
      "deployment_target": "developer-laptop",
      "runtime": "ollama"
    },
    "model_provider_adapter": "openai-compatible",
    "model_provider_id": "ollama-qwen3-0-6b",
    "runtime_type": "ollama",
    "service": {
      "name": "ollama",
      "restart_count": 0,
      "restart_mode": "external"
    },
    "skipped_checks": {
      "rocm_device_flags": "local Ollama does not use ROCm container device flags",
      "tool_call_parser": "tool calling is disabled for this model provider"
    }
  }
}
```

### After

```json
{}
```

## Repair Details

```json
{}
```

