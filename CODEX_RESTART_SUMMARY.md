# Codex Restart Summary

Use this file when reopening Codex from the renamed folder.

## New project path

`/Users/oferg/work/nebius/mlops3/0303/mlops-assignment2`

## What was completed locally on the Mac

- Created a Python `3.12` virtual environment.
- Added `requirements.txt` and installed local Python dependencies.
- Created and populated `.env` for local Ollama debugging.
- Downloaded and prepared the BIRD subset.
- Started local Docker observability services and verified them.
- Set up local Langfuse keys and confirmed tracing works.
- Verified the local smoke test end-to-end with Ollama.
- Added Nebius planning docs for the future H100 slot.

## Local smoke-test status

The local smoke test succeeded against Ollama with the expected loop:

`generate_sql -> verify -> revise -> verify`

The sample Formula 1 coordinates question was corrected from `location` to
`DISTINCT lat, lng` and returned rows successfully.

## Important docs to read first in the new session

- `CODEX_HANDOFF.md`
- `README.md`
- `NEBIUS_RUNBOOK.md`
- `NEBIUS_SLOT_CHECKLIST.md`
- `REPORT.md`

## Nebius-slot understanding

The final screenshots, evals, tuning evidence, and reported numbers must come
from the real Nebius H100 run with `Qwen/Qwen3-30B-A3B-Instruct-2507` via
`vLLM`, not from local Ollama.

Multiple measured tuning rounds are mandatory. The plan is documented in
`NEBIUS_SLOT_CHECKLIST.md`, including baseline, parameter-round strategy, and
what to record in `REPORT.md`.

## Suggested next step in the new session

Open the renamed folder in Codex and begin by reading:

1. `CODEX_RESTART_SUMMARY.md`
2. `NEBIUS_SLOT_CHECKLIST.md`
3. `CODEX_HANDOFF.md`

Then continue from the Nebius slot plan when the GPU window is available.
