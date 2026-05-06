# Chaos-Qwen adversarial heal-cycle sweep · 2026-05-06T08:04:14Z

Upstream: `http://127.0.0.1:11434/v1`  ·  model: `qwen3:0.6b`  ·  proxy: `127.0.0.1:8001`

| mode | recipe | attempts | outcome | duration_ms |
|---|---|---:|---|---:|
| healthy | — | 0 | healed | 1843 |
| models_500 | fallback_model_provider | 2 | unrecoverable | 1202 |
| chat_500 | fallback_model_provider | 2 | unrecoverable | 1213 |
| chat_invalid_json | fallback_model_provider | 2 | unrecoverable | 7542 |
| empty_response | fallback_model_provider | 2 | unrecoverable | 7561 |
| partial_response | fallback_model_provider | 2 | unrecoverable | 7559 |
| rate_limit | fallback_model_provider | 2 | unrecoverable | 2376 |
| rate_limit_once | — | 0 | healed | 2097 |
| slow_response | increase_timeout | 1 | healed | 4026 |
| drop_connection | fallback_model_provider | 2 | unrecoverable | 1562 |
| empty_chat_content | switch_prompt_template | 2 | unrecoverable | 4140 |
| empty_chat_content_once | increase_health_max_tokens | 1 | healed | 2012 |
| instruction_drift | tighten_expected_health_response | 2 | unrecoverable | 4171 |
| hallucinated_tool_call | tighten_expected_health_response | 2 | unrecoverable | 4110 |
| repetitive_output | lower_health_max_tokens | 2 | unrecoverable | 3972 |
| stream_interrupt | disable_streaming | 1 | healed | 2277 |

Expected-heal gate: `healthy rate_limit_once slow_response empty_chat_content_once stream_interrupt`

Gate: **PASS** — every expected-heal mode reached a healed outcome.
