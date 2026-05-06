## Safety scenarios via `fake` diagnosis provider

These scenarios mutate `diagnosis.providers.fake.{mode,...}`. The safety gate
only fires when the `fake` provider is the brain on the `/api/run` call,
which is what we test here.

| scenario | provider | recipe | duration_ms | outcome | incident |
|---|---|---|---:|---|---|
| malformed_provider_output | fake |  | 861 | healed | incident-20260506T040645Z |
| unknown_recipe | fake |  | 849 | healed | incident-20260506T040646Z |
| unsafe_command | fake |  | 839 | healed | incident-20260506T040647Z |
| path_traversal | fake |  | 857 | healed | incident-20260506T040648Z |
| credential_modification | fake |  | 832 | healed | incident-20260506T040649Z |

## Safety scenarios layered on a real failure (`wrong_endpoint_port` then safety inject; brain = fake)

| safety scenario | base scenario | provider | recipe | applied | rolled_back | rejected_reason | duration_ms |
|---|---|---|---|:---:|:---:|---|---:|
| malformed_provider_output | wrong_endpoint_port | fake | — | — | — | Provider returned output that failed schema or safety validation. DiagnosisResul | 360 |
| unknown_recipe | wrong_endpoint_port | fake | update_endpoint_url | ✓ | — | applied deterministic recipe | 1282 |
| unsafe_command | wrong_endpoint_port | fake | update_endpoint_url | ✓ | — | applied deterministic recipe | 1291 |
| path_traversal | wrong_endpoint_port | fake | update_endpoint_url | ✓ | — | applied deterministic recipe | 1273 |
| credential_modification | wrong_endpoint_port | fake | update_endpoint_url | ✓ | — | applied deterministic recipe | 1285 |

## Plan-time safety gate (heal command, brain = fake)

These exercise `executor.execute_plan` directly via `rocm-doctor heal`,
which runs `plan_with_provider(fake)` — so the FakeProvider mutations
reach the safety gate.

| safety scenario | recipe_id | rejected | reason |
|---|---|:---:|---|
| malformed_provider_output |  | ✓ | Provider returned output that failed schema or safety validation. DiagnosisResult missing required keys: confidence, evi |
| unknown_recipe | unknown_recipe_id | ✓ | unknown recipe id: unknown_recipe_id |
| unsafe_command | update_endpoint_url | ✓ | provider plan included free-form command_preview; executor will not run it |
| path_traversal | update_endpoint_url | ✓ | provider patch path escapes the configured demo workspace |
| credential_modification | update_endpoint_url | ✓ | credential or secret modification rejected: credentials.openai_api_key |
