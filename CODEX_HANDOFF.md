# Codex Handoff

Use this file to resume the assignment on another machine.

## Plain-English assignment summary

The assignment is to build a small "ask questions about data" system.

The flow is:

```text
English question
-> agent asks an LLM to write SQL
-> SQL runs on a SQLite database
-> agent checks whether the answer makes sense
-> agent revises SQL if needed
-> system returns rows
```

The final system must be demonstrated with the real model
`Qwen/Qwen3-30B-A3B-Instruct-2507` running on one Nebius H100 through vLLM.

Important terms:

- LLM: the model/brain that generates text.
- vLLM: the inference/model server that hosts the LLM behind an API and runs it
  efficiently on the GPU. It is not an agent. It handles batching, concurrency,
  KV cache, scheduling, token generation, and metrics.
- Agent: the LangGraph workflow we build on top of the model server. It decides
  to generate SQL, execute SQL, verify, and revise.
- BIRD: the text-to-SQL benchmark dataset. It provides databases, English
  questions, gold SQL, and expected result rows.
- Prometheus: the metrics collector. vLLM exposes `/metrics`, Prometheus stores
  those time-series metrics, and Grafana displays them.
- Grafana: the dashboard UI for vLLM serving health.
- Langfuse: the tracing UI for the agent workflow.

The assignment's inference-tuning sentence says:

```text
Everything else is up to you, use your knowledge of inference optimizations.

We are not enumerating which parameters to consider on purpose. Knowing which
levers to reach for, given a workload profile (1.5-3K-token prompts, short
structured outputs, ~2-3 dependent calls per user request) and a latency target,
is the apply-the-lectures part of the assignment. Heads-up: you'll need to
iterate.
```

Meaning: the model and hardware are fixed, but the vLLM serving configuration is
our responsibility. We need to choose flags, run load tests, read metrics, change
one thing at a time, and explain the reason for each change.

Initial vLLM flags chosen in `scripts/start_vllm.sh`:

```bash
--max-model-len 4096
--max-num-seqs 64
--max-num-batched-tokens 8192
--gpu-memory-utilization 0.92
--enable-prefix-caching
--enable-chunked-prefill
--disable-log-requests
```

These are not final. They are a first hypothesis for the H100 run.

Simple rationale:

- `--max-model-len 4096`: enough room for 1.5K-3K token schema prompts without
  wasting too much KV cache.
- `--max-num-seqs 64`: allows concurrent LLM calls, important because one user
  request can trigger 2-3 dependent model calls.
- `--max-num-batched-tokens 8192`: gives vLLM room to batch mixed prompt/decode
  work.
- `--gpu-memory-utilization 0.92`: uses most of the H100 while leaving runtime
  headroom.
- `--enable-prefix-caching`: useful because schemas/system prompts repeat.
- `--enable-chunked-prefill`: helps long schema prompts avoid blocking decode
  work.
- `--disable-log-requests`: avoids request logging overhead during load tests.

Performance target:

```text
p95 end-to-end agent latency < 5 seconds
10+ full agent requests per second
for 5 minutes
```

`p95` means 95th percentile: 95% of requests must finish below that latency.
End-to-end agent latency includes generate SQL, execute SQL, verify, possible
revise calls, and final response.

## Repository state

Local checkpoint commit:

```text
aa8db49 Implement local agent eval and observability prep
```

Push this commit to your fork, then clone the fork on the Mac.

## What was implemented

- `agent/graph.py`
  - Implemented `verify_node`, `revise_node`, and `route_after_verify`.
  - Added robust JSON parsing for verifier replies.
  - Added deterministic verifier guards for coordinate-column mismatch and duplicate answer rows.

- `agent/prompts.py`
  - Added generation, verification, and revision prompts.

- `evals/run_eval.py`
  - Implemented HTTP agent calls.
  - Implemented execution-accuracy scoring.
  - Implemented per-iteration carry-forward summary.

- `infra/grafana/provisioning/dashboards/serving.json`
  - Expanded dashboard with latency, lifecycle, throughput, token-size, KV-cache, and prefix-cache panels.

- `scripts/start_vllm.sh`
  - Added configurable initial H100 vLLM launch flags.

- `REPORT.md`
  - Added local-first notes, local Ollama eval results, Langfuse tracing status, and initial serving config rationale.

- `NEBIUS_RUNBOOK.md`
  - Added cloud-phase setup, launch, eval, load-test, and evidence checklist.

## Local validation already done on Windows

- Repo-local venv created.
- Ollama installed.
- `qwen2.5-coder:3b` pulled.
- BIRD dev data loaded.
- Docker Desktop installed and working.
- Docker Compose observability stack started successfully.
- Grafana loaded the `vLLM serving` dashboard.
- Langfuse received traces from the local agent.
- Full local Ollama eval:

```text
results/eval_local_ollama.json
accuracy: 8/30
iteration 1: 6/30
iteration 2: 8/30
iteration 3: 8/30
p95 latency: 43.45s
```

These local numbers are only debug evidence. Final numbers must come from Nebius
with `Qwen/Qwen3-30B-A3B-Instruct-2507` on H100.

## Recreate local Mac state

After cloning on the Mac:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install langgraph langchain langchain-openai langfuse fastapi "uvicorn[standard]" pydantic python-dotenv httpx aiohttp tqdm datasets
```

Install Ollama and pull the local debug model:

```bash
ollama pull qwen2.5-coder:3b
```

Create `.env`:

```bash
cp .env.example .env
```

Use this for local Ollama debugging:

```env
HF_TOKEN=
VLLM_BASE_URL=http://localhost:11434/v1
VLLM_MODEL=qwen2.5-coder:3b
OPENAI_API_KEY=ollama
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=http://localhost:3001
```

Load data:

```bash
python scripts/load_data.py
```

Start optional local observability:

```bash
docker compose up -d
```

Start the agent:

```bash
uvicorn agent.server:app --host 127.0.0.1 --port 8001
```

Smoke test:

```bash
curl -X POST http://127.0.0.1:8001/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the coordinates location of the circuits for Australian grand prix?","db":"formula_1","tags":{"phase":"mac_smoke","backend":"ollama"}}'
```

Expected shape:

```text
generate_sql -> verify -> revise -> verify
final SQL returns DISTINCT lat, lng
```

## Next work

1. Push this repo to your fork and clone it on the Mac.
2. Recreate `.venv`, `.env`, Ollama, data, and Docker stack on the Mac.
3. Capture local UI screenshots if useful.
4. Move to Nebius for:
   - real vLLM serving on H100,
   - final baseline eval,
   - Grafana screenshots with vLLM metrics,
   - Langfuse screenshots,
   - SLO/load-test tuning,
   - final `REPORT.md`.
