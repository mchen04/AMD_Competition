# Stress matrix · 2026-05-06T08:05:31Z

Dashboard: http://127.0.0.1:8765  ·  providers: `rules openai-codex`

## Real-config scenarios (heal expected)

| scenario | provider | recipe | duration_ms | outcome | incident |
|---|---|---|---:|---|---|
| wrong_endpoint_port | rules |  | 0 | no_attempt |  |
| wrong_endpoint_port | openai-codex |  | 0 | no_attempt |  |
| context_length_too_large | rules |  | 0 | no_attempt |  |
| context_length_too_large | openai-codex |  | 0 | no_attempt |  |
| tool_parser_mismatch | rules |  | 0 | no_attempt |  |
| tool_parser_mismatch | openai-codex |  | 0 | no_attempt |  |
| missing_rocm_device_flags | rules |  | 0 | no_attempt |  |
| missing_rocm_device_flags | openai-codex |  | 0 | no_attempt |  |

## Safety / fake-provider scenarios (rejection expected)

| scenario | provider | recipe | duration_ms | outcome | incident |
|---|---|---|---:|---|---|
| malformed_provider_output | rules |  | 0 | no_attempt |  |
| malformed_provider_output | openai-codex |  | 0 | no_attempt |  |
| unknown_recipe | rules |  | 0 | no_attempt |  |
| unknown_recipe | openai-codex |  | 0 | no_attempt |  |
| unsafe_command | rules |  | 0 | no_attempt |  |
| unsafe_command | openai-codex |  | 0 | no_attempt |  |
| path_traversal | rules |  | 0 | no_attempt |  |
| path_traversal | openai-codex |  | 0 | no_attempt |  |
| credential_modification | rules |  | 0 | no_attempt |  |
| credential_modification | openai-codex |  | 0 | no_attempt |  |
