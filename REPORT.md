# MLOps Assignment Report

## Local-first plan

This repo is prepared locally first. Agent logic, prompts, eval harness, dashboard
JSON, and report structure can be developed without occupying the Nebius H100 VM.
Numbers reported as final evidence will be collected only from
`Qwen/Qwen3-30B-A3B-Instruct-2507` running on one H100.

## Serving configuration

Nebius-only for final numbers. The initial H100 launch config is captured in
`scripts/start_vllm.sh` and should be tuned against vLLM metrics:

| Flag | Initial value | Rationale |
|---|---:|---|
| `--max-model-len` | `4096` | Fits the 1.5K-3K schema prompts while avoiding unnecessary KV cache allocation. |
| `--max-num-seqs` | `64` | Starts with enough concurrency for multi-step agent traffic, then tune against queue/KV metrics. |
| `--max-num-batched-tokens` | `8192` | Allows useful batching for mixed prompt and decode work. |
| `--gpu-memory-utilization` | `0.92` | Uses most of the H100 while leaving runtime headroom. |
| `--enable-prefix-caching` | on | Reuses repeated schema/system prompt prefixes. |
| `--enable-chunked-prefill` | on | Reduces long-prefill blocking for schema-heavy prompts. |
| `--disable-log-requests` | on | Avoids request logging overhead during load tests. |

Final values go here after the H100 tuning loop.

## Baseline eval

Nebius-only for final pass rates. The eval runner can be validated locally against
any OpenAI-compatible backend.

Local validation used Ollama with `qwen2.5-coder:3b` through the OpenAI-compatible
endpoint at `http://localhost:11434/v1`. This is not final evidence, but it
validated the graph and scorer end-to-end:

| Run | Backend | Accuracy | Iteration 1 | Iteration 2 | Iteration 3 | P95 latency |
|---|---|---:|---:|---:|---:|---:|
| `results/eval_local_ollama.json` | Ollama `qwen2.5-coder:3b` | 8/30 | 6/30 | 8/30 | 8/30 | 43.45s |

The loop fixed at least two local cases, including a coordinate query where the
first SQL returned `location` and the revised SQL returned `DISTINCT lat, lng`.
Most remaining misses were small-model schema or SQL capability failures, so the
next quality signal must come from the H100-backed Qwen 30B endpoint.

## Agent tracing

Local Langfuse is running from Docker Compose at `http://localhost:3001`.
The agent was restarted with project API keys in `.env`, then 10 tagged local
requests were sent through the Ollama backend. Langfuse captured all 10 traces
with metadata:

| Metadata key | Value |
|---|---|
| `phase` | `local_trace_batch` |
| `backend` | `ollama` |
| `model` | `qwen2.5-coder:3b` |

Several traces include the full `generate_sql -> verify -> revise -> verify`
waterfall. Screenshots still need to be captured from the UI for the final
deliverables.

## SLO iteration log

Nebius-only.

| Iteration | Saw | Hypothesized | Changed | Result |
|---|---|---|---|---|
| Baseline | TBD | TBD | TBD | TBD |

## Agent value

To be filled from `results/eval_baseline.json`, especially the per-iteration
accuracy. The key question is whether later revise attempts improve execution
accuracy over the initial generated SQL.

## More time

TBD with specifics after observing the actual bottlenecks.
