# MLOps Assignment Report

## How I approached the assignment

I tried to do as much work as possible locally first so I would not waste the
Nebius H100 slot on setup issues. Locally I used Ollama to validate the agent
flow, the eval harness, the load-test script, the dashboards, and the report
structure. The final evidence in this report comes only from the real Nebius
run with `Qwen/Qwen3-30B-A3B-Instruct-2507` on one H100 through `vLLM`.

## Serving configuration

I started from the checked-in `vLLM` launch settings in `scripts/start_vllm.sh`:

| Flag | Initial value | Why I started with it |
|---|---:|---|
| `--max-model-len` | `4096` | The prompts are usually schema-heavy, but I wanted to avoid over-allocating KV cache at the start. |
| `--max-num-seqs` | `64` | A reasonable first concurrency guess for an agent that makes multiple dependent model calls. |
| `--max-num-batched-tokens` | `8192` | Enough room for batching prompt and decode work without jumping too high immediately. |
| `--gpu-memory-utilization` | `0.92` | Use most of the H100 while still leaving some headroom. |
| `--enable-prefix-caching` | on | The schema and system prompt prefixes repeat a lot, so this should help. |
| `--enable-chunked-prefill` | on | Useful for long prompts so prefills do not block decode work too badly. |
| `--disable-log-requests` | on | Less request logging noise during load tests. |

After the tuning rounds, the best config I measured was:

| Flag | Final value | Why I kept it |
|---|---:|---|
| `--max-model-len` | `12288` | I hit prompt-length failures at both `4096` and `8192`, so I had to raise this. |
| `--max-num-seqs` | `128` | This was better than `64`, but going to `256` made the tail worse. |
| `--max-num-batched-tokens` | `16384` | Better than the smaller settings; increasing further to `24576` regressed latency again. |
| `--gpu-memory-utilization` | `0.95` | Safe on the H100 and still did not push KV pressure too high in Grafana. |
| `--enable-prefix-caching` | on | Worth keeping because the repeated prompt prefixes were very common. |
| `--enable-chunked-prefill` | on | Helped with the schema-heavy prompt pattern. |
| `--disable-log-requests` | on | Still useful during the sustained runs. |

## Eval results

### Local validation

Before the Nebius run, I validated the graph and scorer locally using Ollama
with `qwen2.5-coder:3b`:

| Run | Backend | Accuracy | Iteration 1 | Iteration 2 | Iteration 3 | P95 latency |
|---|---|---:|---:|---:|---:|---:|
| `results/eval_local_ollama.json` | Ollama `qwen2.5-coder:3b` | 8/30 | 6/30 | 8/30 | 8/30 | 43.45s |

This was not final evidence, but it confirmed that the full
`generate_sql -> verify -> revise -> verify` loop worked end to end.

### Nebius H100 baseline and final eval

Once the real stack was running on Nebius, I ran the baseline eval and then ran
it again after tuning:

| Run | Backend | Accuracy | Iteration 1 | Iteration 2 | Iteration 3 | P95 latency |
|---|---|---:|---:|---:|---:|---:|
| `results/eval_baseline.json` | Nebius H100 + vLLM | 12/30 | 11/30 | 12/30 | 12/30 | 3.57s |
| `results/eval_after_tuning.json` | Nebius H100 + tuned vLLM | 12/30 | 11/30 | 12/30 | 12/30 | 3.63s |

The main takeaway is that serving-side tuning improved stability under load,
but it did not improve SQL quality on the eval set. The score stayed at
`12/30`.

## Langfuse tracing

I ran Langfuse on the Nebius VM through Docker Compose at
`http://localhost:3001`. After adding the API keys into `.env` and restarting
the agent, I sent 5 tagged requests through the real H100 backend.

The traces included metadata like:

| Metadata key | Value |
|---|---|
| `phase` | `h100_trace_batch` |
| `backend` | `vllm` |
| `model` | `Qwen/Qwen3-30B-A3B-Instruct-2507` |

Several traces clearly showed the full
`generate_sql -> verify -> revise -> verify` flow. A good example was the smoke
test question about Australian Grand Prix circuit coordinates: the first SQL
returned duplicate rows, the verifier caught that, and the revise step fixed it
by adding `DISTINCT`.

## Tuning log

I used Grafana plus the request outcomes to guide the tuning rounds. I also had
to fix some setup and code issues on the VM before the actual tuning results
were meaningful.

| Iteration | What I saw | What I thought was happening | What I changed | Result |
|---|---|---|---|---|
| Baseline smoke test | `transformers 5.x` tokenizer crash, missing Python headers, outdated `start_vllm.sh`, stale Ollama `.env` | The VM copy was older than my local repo and was missing several real-run fixes | Pinned `transformers<5`, installed `python3.12-dev`, synced updated repo files, fixed `.env`, updated `scripts/start_vllm.sh` | vLLM and the agent finally started correctly on the H100 |
| Load baseline | `4 RPS` produced 157 HTTP errors and `p95=9.33s` | Some requests were failing before real throughput tuning because prompts were already too long for the context window | Raised `max-model-len` from `4096` to `8192`; raised batched tokens to `12288` | The `4096` prompt-limit failures disappeared, but load still failed because of an agent-side crash |
| Bug fix round | `500` responses with `AttributeError: 'NoneType' object has no attribute 'replace'` | Schema rendering was not handling nullable foreign-key metadata safely | Patched `agent/schema.py` to handle `None` identifiers | Short `2 RPS / 60s` check became `120/120` OK with `p95=4.26s` |
| Round 1 | `4 RPS / 300s` after the schema fix: `1187/1200` OK, `p95=11.17s`, 11 timeouts | The system was healthier, but still not good enough under sustained load | Increased `max-num-seqs` from `64` to `128` while keeping `8192 / 12288 / 0.92` | Mild improvement: `1190/1200` OK, `p95=10.19s` |
| Round 2 | vLLM still logged `maximum context length` failures at `8192` (`8256`-token request) | Some schema-heavy requests still overflowed the context window | Increased to `max-model-len=12288`, `max-num-batched-tokens=16384`, `gpu-memory-utilization=0.95`, kept `max-num-seqs=128` | Best measured run: `1194/1200` OK, `p95=10.02s`, `p50=1.68s`, 5 timeouts, 0 HTTP errors |
| Round 3 | KV cache pressure was still not high, so I checked whether more concurrency would help | Maybe higher admitted concurrency would improve throughput | Increased `max-num-seqs` to `256` | Regressed: `1188/1200` OK, `p95=10.85s`, much worse tail latency |
| Round 4 | I tried one more batching-focused experiment | Maybe a larger batch token cap would help without changing concurrency | Increased `max-num-batched-tokens` to `24576` while returning to `max-num-seqs=128` | Regressed again: `1189/1200` OK, `p95=11.49s` |

## Best load-test result

The best `4 RPS / 300s` run I measured was:

| Run | Config | Successes | P50 | P95 | Notes |
|---|---|---:|---:|---:|---|
| `results/load_test_rps4_len12288.json` | `12288 / 128 / 16384 / 0.95` | `1194/1200` | `1.68s` | `10.02s` | Best tuned run |

Important note: the latency percentiles in `load_test/driver.py` are computed
only over successful requests. Even with that caveat, this still misses the
target badly.

Also, the reported `achieved_rps` numbers in the load-test JSON include the
post-test drain time while in-flight requests finish, which is why the achieved
rate is lower than the raw request schedule might suggest.

I stopped the ramp at `4 RPS` because the system was already far above the
`p95 < 5s` target there, so pushing to `8` or `10` RPS would not have been a
good use of slot time.

## Did the agent loop add value?

Yes, but only a little.

On the H100-backed eval:

- Iteration 1 accuracy: `11/30` (`36.7%`)
- Iteration 2 accuracy: `12/30` (`40.0%`)
- Iteration 3 accuracy: `12/30` (`40.0%`)

So the revise loop earned one extra correct answer on the 30-question eval set.
That means the loop is doing some real work, but the third attempt did not add
anything beyond the second one in my final setup.

## Final conclusion

The tuning work definitely improved system stability:

- I removed prompt-length failures by increasing `max-model-len`
- I fixed an actual schema-rendering crash in the agent
- I reduced the number of failed requests a lot
- I improved the worst-case latency a lot compared to the early runs

But the final serving target was still not met.

The best measured result at `4 RPS / 300s` was:

- `1194/1200` successful requests
- `p50 = 1.68s`
- `p95 = 10.02s`

So my final answer is:

- the stack worked end to end on the real Nebius H100
- the agent loop worked and added a small quality gain
- tuning improved stability and reduced failures
- the SLO was still missed

## What I would do with more time

If I had more time, I would focus less on only changing `vLLM` flags and more
on reducing the actual work per request:

- Trim schema context instead of sending the full schema every time
- Shorten the verifier and revise prompts
- Make the third iteration conditional or remove it, since it did not improve eval accuracy
- Profile agent-side latency versus raw model-side latency more directly
- Work on prompts or graph logic for quality, because infra tuning did not change the `12/30` eval score
