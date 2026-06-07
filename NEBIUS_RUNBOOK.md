# Nebius Runbook

This repo is prepared locally first. Use this runbook when moving to the Nebius
H100 VM for final evidence.

## 1. Connect and forward ports

Forward the five assignment ports from your laptop to the VM:

```bash
ssh -L 3000:localhost:3000 \
    -L 9090:localhost:9090 \
    -L 3001:localhost:3001 \
    -L 8000:localhost:8000 \
    -L 8001:localhost:8001 \
    <user>@<vm-host>
```

## 2. Install and prepare

Run on the VM:

```bash
git clone <your-repo-url>
cd <repo-folder>
uv sync
cp .env.example .env
uv run python scripts/load_data.py
docker compose up -d
```

Fill `.env`:

```env
HF_TOKEN=<huggingface-token-if-needed>
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
OPENAI_API_KEY=not-needed
LANGFUSE_PUBLIC_KEY=<from local Langfuse UI on the VM>
LANGFUSE_SECRET_KEY=<from local Langfuse UI on the VM>
LANGFUSE_HOST=http://localhost:3001
```

## 3. Start vLLM

Start with the checked-in initial config:

```bash
bash scripts/start_vllm.sh
```

Default flags in the script:

| Flag | Initial value | Why |
|---|---:|---|
| `--max-model-len` | `4096` | Fits the 1.5K-3K schema prompts while avoiding excess KV cache allocation. |
| `--max-num-seqs` | `64` | Allows enough concurrent LLM calls for multi-step agent traffic without starting too high. |
| `--max-num-batched-tokens` | `8192` | Gives the scheduler room to batch mixed prompt/decode work. |
| `--gpu-memory-utilization` | `0.92` | Uses most of the H100 while leaving headroom for runtime overhead. |
| `--enable-prefix-caching` | on | Reuses repeated schema/system prompt prefixes across eval/load requests. |
| `--enable-chunked-prefill` | on | Helps long prompts avoid blocking decode work too heavily. |
| `--disable-log-requests` | on | Reduces server logging overhead during load tests. |

The knobs to revisit first are `VLLM_MAX_NUM_SEQS`,
`VLLM_MAX_NUM_BATCHED_TOKENS`, and `VLLM_GPU_MEMORY_UTILIZATION`.

## 4. Start the agent

In another VM shell:

```bash
uv run uvicorn agent.server:app --host 0.0.0.0 --port 8001
```

Smoke test:

```bash
curl -X POST http://localhost:8001/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the coordinates location of the circuits for Australian grand prix?","db":"formula_1","tags":{"phase":"h100_smoke","backend":"vllm"}}'
```

## 5. Evidence sequence

1. Confirm vLLM responds and capture `screenshots/vllm_manual_query.png`.
2. Open Grafana at `http://localhost:3000` and confirm the vLLM dashboard reacts.
3. Fire 10 tagged questions and capture Langfuse trace screenshots.
4. Run baseline eval:

```bash
uv run python evals/run_eval.py --out results/eval_baseline.json
```

5. Run load tests, starting below target and ramping:

```bash
uv run python load_test/driver.py --rps 4 --duration 300 --out results/load_test_rps4.json
uv run python load_test/driver.py --rps 8 --duration 300 --out results/load_test_rps8.json
uv run python load_test/driver.py --rps 10 --duration 300 --out results/load_test_rps10.json
```

6. For each tuning iteration, record:

```text
saw X -> hypothesized Y -> changed Z -> result was W
```

7. Run final eval:

```bash
uv run python evals/run_eval.py --out results/eval_after_tuning.json
```
