# Nebius Quickstart

Use this when the Nebius H100 slot is live and you want the shortest reliable
sequence to get the stack running.

## 1. SSH from your Mac with port forwarding

Run on your Mac:

```bash
ssh -L 3000:localhost:3000 \
    -L 9090:localhost:9090 \
    -L 3001:localhost:3001 \
    -L 8000:localhost:8000 \
    -L 8001:localhost:8001 \
    <user>@<vm-host>
```

## 2. Clone and prepare on the Nebius VM

Run on the VM:

```bash
git clone <your-repo-url>
cd mlops-assignment2
uv sync
cp .env.example .env
uv run python scripts/load_data.py
docker compose up -d
```

## 3. Fill `.env` on the VM

Set:

```env
HF_TOKEN=<huggingface-token-if-needed>
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=Qwen/Qwen3-30B-A3B-Instruct-2507
OPENAI_API_KEY=not-needed
LANGFUSE_PUBLIC_KEY=<from Langfuse UI>
LANGFUSE_SECRET_KEY=<from Langfuse UI>
LANGFUSE_HOST=http://localhost:3001
```

## 4. Start vLLM on the VM

Run on the VM:

```bash
bash scripts/start_vllm.sh
```

## 5. Start the agent on the VM

Open a second shell on the VM and run:

```bash
uv run uvicorn agent.server:app --host 0.0.0.0 --port 8001
```

## 6. Smoke test

Run on the VM:

```bash
curl -X POST http://localhost:8001/answer \
  -H "Content-Type: application/json" \
  -d '{"question":"What is the coordinates location of the circuits for Australian grand prix?","db":"formula_1","tags":{"phase":"h100_smoke","backend":"vllm"}}'
```

## 7. Open the forwarded UIs from your Mac

- `http://localhost:3000` for Grafana
- `http://localhost:3001` for Langfuse

## 8. Run the real measurements on the VM

```bash
uv run python evals/run_eval.py --out results/eval_baseline.json
uv run python load_test/driver.py --rps 4 --duration 300 --out results/load_test_rps4.json
uv run python load_test/driver.py --rps 8 --duration 300 --out results/load_test_rps8.json
uv run python load_test/driver.py --rps 10 --duration 300 --out results/load_test_rps10.json
```

Why three load-test runs:

- `driver.py` does not need exactly three runs.
- The checked-in plan uses `4`, `8`, and `10` RPS to ramp from below target up
  to target and see where latency, queueing, or throughput starts to break.
- If needed, add more runs such as `6`, `12`, or a repeated `10` after tuning.

## 9. Tuning loop

This is not a one-shot run. After the baseline, inspect results and tune.

Use this loop:

1. Run baseline eval and load test.
2. Inspect:
   - Grafana panels
   - eval JSON
   - load-test JSON
3. Write a concrete hypothesis.
4. Change one vLLM parameter.
5. Restart vLLM.
6. Re-run the same measurement.
7. Compare before vs after.
8. Record what improved or regressed.

Main parameters to tune first:

- `VLLM_MAX_NUM_SEQS`
- `VLLM_MAX_NUM_BATCHED_TOKENS`
- `VLLM_GPU_MEMORY_UTILIZATION`

Suggested first sequence:

1. Baseline with the checked-in defaults.
2. Raise `VLLM_MAX_NUM_SEQS` to `128`.
3. If queueing is still the first problem and memory allows it, test `256`.
4. Keep the best `max_num_seqs`, then raise
   `VLLM_MAX_NUM_BATCHED_TOKENS` to `12288`.
5. If memory headroom looks safe, try a slightly higher
   `VLLM_GPU_MEMORY_UTILIZATION`.

Each round:

```bash
# edit .env or export variables for the next run
bash scripts/start_vllm.sh
uv run python evals/run_eval.py --out results/eval_after_tuning.json
uv run python load_test/driver.py --rps 10 --duration 300 --out results/load_test_after_tuning.json
```

Use the same RPS when comparing two rounds so the results are comparable.

Record notes in this format:

```text
saw X -> hypothesized Y -> changed Z -> result was W
```

## Notes

- The Docker services run on the Nebius VM, not on your Mac, for the real slot.
- `vLLM` is not in `docker-compose.yml`; it runs directly on the VM host.
- Your Mac is mainly for SSH and viewing forwarded ports in the browser.
- If dependency resolution pulls `transformers` `5.x` and causes trouble on the
  VM, keep it below `5.0.0` and refresh the environment:

```bash
uv lock --upgrade-package transformers
uv sync
```
