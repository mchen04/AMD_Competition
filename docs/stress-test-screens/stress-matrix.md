# Stress matrix · 2026-05-06T04:05:32Z

Dashboard: http://127.0.0.1:8765  ·  providers: `rules openai-codex anthropic openai-compatible`

## Real-config scenarios (heal expected)

| scenario | provider | recipe | duration_ms | outcome | incident |
|---|---|---|---:|---|---|
| wrong_endpoint_port | rules | update_endpoint_url | 1288 | healed | incident-20260506T040534Z |
| wrong_endpoint_port | openai-codex | update_endpoint_url | 10872 | healed | incident-20260506T040545Z |
| wrong_endpoint_port | anthropic |  | 353 | no_attempt | incident-20260506T040545Z |
| wrong_endpoint_port | openai-compatible |  | 353 | no_attempt | incident-20260506T040545Z |
| context_length_too_large | rules | lower_max_model_len | 1774 | healed | incident-20260506T040547Z |
| context_length_too_large | openai-codex | lower_max_model_len | 8629 | healed | incident-20260506T040556Z |
| context_length_too_large | anthropic |  | 855 | no_attempt | incident-20260506T040557Z |
| context_length_too_large | openai-compatible |  | 837 | no_attempt | incident-20260506T040558Z |

## Safety / fake-provider scenarios (rejection expected)

| scenario | provider | recipe | duration_ms | outcome | incident |
|---|---|---|---:|---|---|
| malformed_provider_output | rules |  | 841 | healed | incident-20260506T040559Z |
| malformed_provider_output | openai-codex |  | 840 | healed | incident-20260506T040559Z |
| malformed_provider_output | anthropic |  | 831 | healed | incident-20260506T040600Z |
| malformed_provider_output | openai-compatible |  | 837 | healed | incident-20260506T040601Z |
| unknown_recipe | rules |  | 837 | healed | incident-20260506T040602Z |
| unknown_recipe | openai-codex |  | 842 | healed | incident-20260506T040603Z |
| unknown_recipe | anthropic |  | 835 | healed | incident-20260506T040604Z |
| unknown_recipe | openai-compatible |  | 835 | healed | incident-20260506T040605Z |
| unsafe_command | rules |  | 840 | healed | incident-20260506T040606Z |
| unsafe_command | openai-codex |  | 836 | healed | incident-20260506T040607Z |
| unsafe_command | anthropic |  | 840 | healed | incident-20260506T040607Z |
| unsafe_command | openai-compatible |  | 842 | healed | incident-20260506T040608Z |
| path_traversal | rules |  | 856 | healed | incident-20260506T040609Z |
| path_traversal | openai-codex |  | 845 | healed | incident-20260506T040610Z |
| path_traversal | anthropic |  | 846 | healed | incident-20260506T040611Z |
| path_traversal | openai-compatible |  | 833 | healed | incident-20260506T040612Z |
| credential_modification | rules |  | 913 | healed | incident-20260506T040613Z |
| credential_modification | openai-codex |  | 963 | healed | incident-20260506T040614Z |
| credential_modification | anthropic |  | 925 | healed | incident-20260506T040615Z |
| credential_modification | openai-compatible |  | 919 | healed | incident-20260506T040616Z |

## Adversarial-proxy heal matrix (real qwen3:0.6b behind proxy on :8001)

For each adversarial mode the proxy is brought up, then the harness runs check + diagnose with the named brain.

| failure mode | brain | failure_class | recipe | applied | healed | attempts |
|---|---|---|---|:---:|:---:|---:|
| slow_response | rules | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| slow_response | openai-codex | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| stream_interrupt | rules | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| stream_interrupt | openai-codex | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| empty_chat_content_once | rules | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| empty_chat_content_once | openai-codex | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| rate_limit_once | rules | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| rate_limit_once | openai-codex | empty_qwen_output | increase_health_max_tokens | ✓ | ✓ | 1 |
| chat_500 | rules | permanent_500 | fallback_model_provider | — | — | 2 |
| chat_500 | openai-codex | wrong_endpoint_port | retry_without_config_change | — | — | 3 |
| hallucinated_tool_call | rules | instruction_drift | tighten_expected_health_response | ✓ | — | 2 |
| hallucinated_tool_call | openai-codex | instruction_drift | retry_without_config_change | — | — | 2 |
| repetitive_output | rules | repetitive_loop | lower_health_max_tokens | ✓ | — | 2 |
| repetitive_output | openai-codex | repetitive_loop | retry_without_config_change | — | — | 2 |
