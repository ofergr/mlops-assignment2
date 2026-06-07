# Nebius Slot Checklist

Use this checklist during the H100 window so the time is spent only on the
real Nebius run and final evidence collection.

Important: this is not a one-pass run. The assignment expects multiple tuning
rounds with different vLLM parameters, measured results after each change, and
an evidence-based explanation of what improved or failed to improve.

## Before you start

- Confirm SSH access to the Nebius VM works.
- Forward ports `3000`, `9090`, `3001`, `8000`, `8001`.
- Have your repo URL ready.
- Have your Hugging Face token ready in case the model pull requires it.
- Keep this repo open locally so you can copy notes back into `REPORT.md`.

## 1. VM bootstrap

SSH into the VM and run:

```bash
git clone <your-repo-url>
cd <repo-folder>
uv sync
cp .env.example .env
uv run python scripts/load_data.py
docker compose up -d
```

## 2. Fill the VM `.env`

Use the real H100 backend, not local Ollama:

```env
HF_TOKEN=<huggingface-token-if-needed>
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
OPENAI_API_KEY=not-needed
LANGFUSE_PUBLIC_KEY=<from Langfuse UI on the VM>
LANGFUSE_SECRET_KEY=<from Langfuse UI on the VM>
LANGFUSE_HOST=http://localhost:3001
```

## 3. Start vLLM

Start with the checked-in initial config:

```bash
bash scripts/start_vllm.sh
```

Initial flags to validate and later tune:

- `--max-model-len=4096`
- `--max-num-seqs=64`
- `--max-num-batched-tokens=8192`
- `--gpu-memory-utilization=0.92`
- `--enable-prefix-caching`
- `--enable-chunked-prefill`
- `--disable-log-requests`

## 4. Start the agent

In another shell:

```bash
uv run uvicorn agent.server:app --host 0.0.0.0 --port 8001
```

## 5. Smoke test the real stack

Run:

```bash
curl -X POST http://localhost:8001/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the coordinates location of the circuits for Australian grand prix?","db":"formula_1","tags":{"phase":"h100_smoke","backend":"vllm"}}'
```

Confirm:

- the agent responds successfully
- the SQL looks sensible
- ideally the request shows a verify/revise loop at least once

## 6. Capture early evidence

Capture these as soon as the real stack is healthy:

- `screenshots/vllm_manual_query.png`
  Show vLLM serving plus one manual query returning SQL.
- `screenshots/grafana_serving.png`
  Show the full Grafana dashboard with panels reacting.

## 7. Langfuse setup on the VM

- Open `http://localhost:3001`
- Create a local Langfuse account/project on the VM
- Copy the project keys into the VM `.env`
- Restart the agent if needed so it picks up the keys
- Fire about 10 tagged questions through the agent

Capture:

- `screenshots/langfuse_trace.png`
- `screenshots/langfuse_tags.png`

Use useful metadata tags such as:

- `phase=h100_trace_batch`
- `backend=vllm`
- `model=Qwen/Qwen3-30B-A3B-Instruct-2507`

## 8. Run baseline eval

Run:

```bash
uv run python evals/run_eval.py --out results/eval_baseline.json
```

While it runs:

- watch Grafana
- note any obvious queueing, latency spikes, or KV pressure

Capture:

- `screenshots/grafana_eval_run.png`

## 9. Run load tests

Start below target, then ramp up:

```bash
uv run python load_test/driver.py --rps 4 --duration 300 --out results/load_test_rps4.json
uv run python load_test/driver.py --rps 8 --duration 300 --out results/load_test_rps8.json
uv run python load_test/driver.py --rps 10 --duration 300 --out results/load_test_rps10.json
```

Target to evaluate:

- `p95` end-to-end agent latency under `5s`
- `10+` full agent requests per second
- sustained for `5 minutes`

Do not expect to hit this on the first attempt. Plan for several rounds with
different parameter settings and capture the outcome of each round.

## 10. Tune one thing at a time

For each tuning step:

1. Look at Grafana and identify what moves first.
2. Write a concrete hypothesis.
3. Change one thing.
4. Re-run the test.
5. Record the outcome in `REPORT.md`.

Treat this as a loop, not a single step. Repeat until:

- the SLO is reached, or
- you have a clear metric-grounded explanation for why it is still missed

Use this log format:

```text
saw X -> hypothesized Y -> changed Z -> result was W
```

Capture:

- `screenshots/grafana_before.png`
- `screenshots/grafana_after.png`

Likely first knobs to revisit:

- `VLLM_MAX_NUM_SEQS`
- `VLLM_MAX_NUM_BATCHED_TOKENS`
- `VLLM_GPU_MEMORY_UTILIZATION`

Good practice for the slot:

- keep one baseline run
- make one parameter change per round when possible
- save each round's test output
- capture Grafana evidence for the rounds that matter
- stop guessing and re-read metrics if too many rounds are not moving the result

## 10A. Concrete tuning-round plan

This is the planned sequence for the Nebius slot. Use it as the default path
unless the metrics clearly suggest a better next step.

### Round 0: baseline

Use the checked-in starting config:

- `VLLM_MAX_MODEL_LEN=4096`
- `VLLM_MAX_NUM_SEQS=64`
- `VLLM_MAX_NUM_BATCHED_TOKENS=8192`
- `VLLM_GPU_MEMORY_UTILIZATION=0.92`
- prefix caching on
- chunked prefill on

Goal:

- establish the first real p95 / throughput numbers
- see whether the first bottleneck is queueing, long prefills, or KV pressure

### Round 1: raise concurrency

Keep everything else fixed and increase:

- `VLLM_MAX_NUM_SEQS=128`

If the system still has KV headroom and queueing is still the first failure
mode, test:

- `VLLM_MAX_NUM_SEQS=256`

Why this round:

- one user request triggers multiple dependent model calls
- low sequence concurrency may cap throughput early

Watch for:

- better throughput with similar latency
- worse p95 due to over-admission
- KV cache saturation

### Round 2: increase batched tokens

Keep the best `max_num_seqs` from Round 1, then test:

- `VLLM_MAX_NUM_BATCHED_TOKENS=12288`

If metrics still suggest the scheduler is starved by long prefills and memory
headroom is available, test:

- `VLLM_MAX_NUM_BATCHED_TOKENS=16384`

Why this round:

- prompts are large and schema-heavy
- larger batch-token budget may improve mixed prefill/decode efficiency

Watch for:

- higher throughput
- lower or flatter prefill latency
- worse tail latency if batches become too large

### Round 3: increase GPU memory utilization

Keep the best prior settings and test:

- `VLLM_GPU_MEMORY_UTILIZATION=0.94`

If stable and still KV-limited:

- `VLLM_GPU_MEMORY_UTILIZATION=0.96`

Why this round:

- more memory budget can increase KV capacity and help concurrency

Watch for:

- improved throughput or fewer cache-pressure symptoms
- startup or runtime instability
- signs that pushing memory higher stops helping

### Round 4: long-prefill fairness

If long schema prompts are clearly blocking shorter work, keep chunked prefill
enabled and try the prefill fairness knobs.

Candidate settings to test:

- `VLLM_MAX_NUM_PARTIAL_PREFILLS=2`
- `VLLM_MAX_LONG_PARTIAL_PREFILLS=1`
- `VLLM_LONG_PREFILL_TOKEN_THRESHOLD=1024`

Possible follow-up:

- `VLLM_MAX_NUM_PARTIAL_PREFILLS=4`
- keep `VLLM_MAX_LONG_PARTIAL_PREFILLS=1`

Why this round:

- the workload mixes long prompts with short outputs
- giving shorter work a chance to jump ahead can improve latency

Watch for:

- better p95 without hurting throughput too much
- reduced long-prompt blocking
- whether the scheduler becomes fairer under load

### Round 5: revisit max model length only if justified

Default:

- keep `VLLM_MAX_MODEL_LEN=4096`

Only test changes if evidence suggests wasted KV capacity and prompts are
comfortably below the lower bound.

Conservative experiment:

- `VLLM_MAX_MODEL_LEN=3584`

Why this round is later:

- lowering context too aggressively can break valid prompts
- it is higher risk than tuning concurrency or batching first

Watch for:

- any prompt truncation or failures
- whether reduced reserved KV meaningfully improves throughput

### Optional later rounds

Only if the main knobs plateau:

- test async scheduling behavior
- test scheduler delay behavior

These are lower-priority than:

- `max_num_seqs`
- `max_num_batched_tokens`
- `gpu_memory_utilization`
- chunked-prefill fairness settings

## 10C. Secondary knobs if needed

These are not the first parameters to touch, but they are valid follow-up
options if the main rounds plateau and the metrics suggest a specific need.

### `async-scheduling`

Use if:

- GPU utilization has visible gaps
- the scheduler appears to be leaving work on the table

Why:

- async scheduling can improve latency and throughput by reducing scheduling
  stalls

### `scheduler-delay-factor`

Use if:

- request admission timing looks inefficient
- p95 is being hurt by the way new prompts are admitted under load

Why:

- it changes how aggressively new work is scheduled relative to prior prompt
  latency

### `block-size`

Use if:

- KV/cache behavior looks unusual
- the main batching/concurrency knobs have already been explored

Why:

- token block size affects KV allocation behavior and can sometimes shift
  memory efficiency tradeoffs

### `enforce-eager`

Use if:

- you suspect graph/capture behavior is causing instability or unexpected
  latency

Why:

- it is mainly a diagnostic comparison rather than a first-choice optimization

### `performance_mode`

Use if:

- the installed vLLM version supports it clearly
- the observed bottleneck suggests a throughput-oriented preset might help

Why:

- it may alter default batching behavior in a useful way, but should not be
  treated as a substitute for understanding the metrics

### `swap-space` / offload-related settings

Use if:

- memory pressure is clearly the dominant bottleneck
- simpler tuning did not resolve it

Why:

- these are fallback levers, not preferred first-round changes on a single H100

## 10D. Knobs to avoid unless strongly justified

Do not reach for these early in the slot:

- quantization changes
- speculative decoding
- major scheduler-class changes
- offload-heavy workarounds
- invasive changes that make the run harder to explain in `REPORT.md`

Reason:

- they add complexity and risk, and the assignment is better served by a clean,
  explainable tuning story around batching, concurrency, prefill, and KV
  behavior first

## 10B. What to record per round

For every round, save:

- parameter values used
- load test command
- achieved RPS
- p95 latency
- whether the run met the SLO
- what the Grafana dashboard showed first
- one-line interpretation for `REPORT.md`

Use this format:

```text
Round N
saw X -> hypothesized Y -> changed Z -> result was W
```

## 11. Run final eval after tuning

Run:

```bash
uv run python evals/run_eval.py --out results/eval_after_tuning.json
```

Confirm whether quality survived the tuning changes.

## 12. Final report pass

Before ending the slot, make sure `REPORT.md` includes:

- final serving configuration and one-line rationale for each flag
- baseline eval results
- per-iteration pass rates
- whether the verify/revise loop added real value
- baseline versus final SLO numbers
- tuning iteration log
- honest final verdict

## Required outputs to leave with

- `results/eval_baseline.json`
- `results/eval_after_tuning.json`
- `screenshots/vllm_manual_query.png`
- `screenshots/grafana_serving.png`
- `screenshots/langfuse_trace.png`
- `screenshots/langfuse_tags.png`
- `screenshots/grafana_eval_run.png`
- `screenshots/grafana_before.png`
- `screenshots/grafana_after.png`
- updated `REPORT.md`

## Reminder: what was already done locally

These are already done on the Mac and should not consume Nebius slot time:

- Python `3.12` virtualenv creation
- dependency installation
- local `.env` setup
- BIRD dataset download and preparation
- local Docker observability stack startup
- local Langfuse project setup and key wiring
- local Ollama smoke test
- local verification that the agent loop works end to end
