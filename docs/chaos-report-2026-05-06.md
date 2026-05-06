# Chaos report · 2026-05-06T08:03:42Z

Overall: **PASS**

| layer | what | status | detail |
|---|---|---|---|
| 1 | deterministic chaos pytests | pass | 4 passed in 31.59s |
| 2 | adversarial-proxy sweep (real Qwen) | pass | chaos_qwen: running mode=repetitive_output;chaos_qwen: running mode=stream_interrupt;wrote docs/stress-test-screens/chaos-qwen.md; |
| 3 | two-brain stress matrix | pass | providers=rules openai-codex · wrote docs/stress-test-screens/stress-matrix.md;raw runs in docs/stress-test-screens/runs; |
| 5 | supervisor stability soak (10 cycles) | pass | chaos_supervisor: PASS heal_rate=100.00% mean_attempts_2h=1.00 learned_replays=6 output=docs/chaos-supervisor-2026-05-06.json |

Layer 2 markdown: `docs/stress-test-screens/chaos-qwen.md`
Layer 3 markdown: `docs/stress-test-screens/stress-matrix.md`
Layer 5 JSON: `docs/chaos-supervisor-2026-05-06.json`
