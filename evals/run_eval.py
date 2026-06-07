"""Eval runner using execution accuracy.

Reads evals/eval_set.jsonl, calls the agent at AGENT_URL on each question,
then compares the agent's SQL output to the gold SQL by *executed rows*
(canonicalized: sorted, stringified, None-coerced to empty).

Helpers (run_sql / canonicalize / matches) are provided. You implement
eval_one() and summarize().

Run:
    uv run python evals/run_eval.py --out results/eval_baseline.json
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EVAL_FILE = ROOT / "evals" / "eval_set.jsonl"
DEFAULT_OUT_FILE = ROOT / "results" / "eval_baseline.json"
DB_DIR = ROOT / "data" / "bird"
AGENT_URL_DEFAULT = "http://localhost:8001/answer"


# ---------- Helpers (provided) -----------------------------------------

def run_sql(db_id: str, sql: str, timeout: float = 5.0) -> tuple[bool, list[tuple] | None, str | None]:
    """Run sql against db_id in read-only mode. Returns (ok, rows, error)."""
    path = DB_DIR / f"{db_id}.sqlite"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=timeout) as conn:
            cur = conn.execute(sql)
            rows = cur.fetchall()
            return True, rows, None
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def canonicalize(rows: list[tuple] | None) -> list[tuple] | None:
    """Sort rows; coerce cells to str; None -> ''."""
    if rows is None:
        return None
    return sorted(tuple("" if c is None else str(c) for c in row) for row in rows)


def matches(gold_rows: list[tuple] | None, pred_rows: list[tuple] | None) -> bool:
    if gold_rows is None or pred_rows is None:
        return False
    return canonicalize(gold_rows) == canonicalize(pred_rows)


# ---------- Implement these (Phase 5) ----------------------------------

def eval_one(question: dict, agent_url: str) -> dict:
    """Score one question. Return a dict capturing per-iteration correctness."""
    import httpx

    payload = {
        "question": question["question"],
        "db": question["db_id"],
        "tags": {"phase": "eval", "db_id": question["db_id"]},
    }
    t0 = time.monotonic()
    try:
        response = httpx.post(agent_url, json=payload, timeout=180.0)
        response.raise_for_status()
        agent = response.json()
        agent_error = None
    except Exception as e:  # noqa: BLE001
        agent = {}
        agent_error = f"{type(e).__name__}: {e}"
    latency = time.monotonic() - t0

    gold_ok, gold_rows, gold_error = run_sql(question["db_id"], question["gold_sql"])
    final_sql = agent.get("sql", "")
    pred_ok, pred_rows, pred_error = run_sql(question["db_id"], final_sql) if final_sql else (False, None, "empty SQL")

    attempts: list[dict] = []
    seen_sql: set[str] = set()
    for item in agent.get("history", []):
        if item.get("node") not in {"generate_sql", "revise"}:
            continue
        sql = str(item.get("sql", "")).strip()
        if not sql or sql in seen_sql:
            continue
        seen_sql.add(sql)
        ok, rows, error = run_sql(question["db_id"], sql)
        attempts.append({
            "iteration": len(attempts) + 1,
            "sql": sql,
            "execution_ok": ok,
            "execution_error": error,
            "correct": gold_ok and matches(gold_rows, rows),
        })

    if final_sql and (not attempts or attempts[-1]["sql"] != final_sql):
        attempts.append({
            "iteration": len(attempts) + 1,
            "sql": final_sql,
            "execution_ok": pred_ok,
            "execution_error": pred_error,
            "correct": gold_ok and matches(gold_rows, pred_rows),
        })

    return {
        "question": question["question"],
        "db_id": question["db_id"],
        "gold_sql": question["gold_sql"],
        "gold_execution_ok": gold_ok,
        "gold_error": gold_error,
        "final_sql": final_sql,
        "final_execution_ok": pred_ok,
        "final_error": agent_error or pred_error,
        "correct": gold_ok and matches(gold_rows, pred_rows),
        "agent_iterations": agent.get("iterations", 0),
        "latency_seconds": latency,
        "attempts": attempts,
    }


def summarize(results: list[dict]) -> dict:
    """Aggregate per-question results.

    Per-iteration carry-forward: if the agent terminated at iteration j < k
    (verify said ok at j, or it hit MAX_ITERATIONS at j < k), treat the
    question's iteration-k result as identical to its iteration-j result.
    The agent stopped emitting; whatever it had at termination is what
    would have been served had we polled at iteration k.
    """
    total = len(results)
    correct = sum(1 for r in results if r.get("correct"))
    max_iter = max((len(r.get("attempts", [])) for r in results), default=0)

    per_iteration: dict[str, dict] = {}
    for i in range(1, max_iter + 1):
        n_correct = 0
        for r in results:
            attempts = r.get("attempts", [])
            if not attempts:
                continue
            idx = min(i, len(attempts)) - 1
            n_correct += 1 if attempts[idx].get("correct") else 0
        per_iteration[str(i)] = {
            "correct": n_correct,
            "total": total,
            "accuracy": (n_correct / total) if total else 0.0,
        }

    latencies = sorted(r.get("latency_seconds", 0.0) for r in results)

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        k = int(round(p * (len(latencies) - 1)))
        return latencies[k]

    return {
        "total": total,
        "correct": correct,
        "accuracy": (correct / total) if total else 0.0,
        "per_iteration": per_iteration,
        "agent_errors": sum(1 for r in results if r.get("final_error") and not r.get("final_execution_ok")),
        "latency_p50_seconds": pct(0.50),
        "latency_p95_seconds": pct(0.95),
    }


# ---------- Main (provided) --------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-set", type=Path, default=DEFAULT_EVAL_FILE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT_FILE)
    parser.add_argument("--agent-url", default=AGENT_URL_DEFAULT)
    args = parser.parse_args()

    questions = [json.loads(line) for line in args.eval_set.read_text().splitlines() if line.strip()]
    print(f"Loaded {len(questions)} eval questions from {args.eval_set}")

    results: list[dict] = []
    t0 = time.monotonic()
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q['db_id']}: {q['question'][:60]}...", flush=True)
        results.append(eval_one(q, args.agent_url))
    elapsed = time.monotonic() - t0

    summary = summarize(results)
    out = {
        "summary": summary,
        "wall_clock_seconds": elapsed,
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(f"Wrote {args.out}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
