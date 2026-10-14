"""Stage 2 driver: n8n SDLC chain on the Claude Messages API (or Ollama). Resumable, interleaved, budget-guarded. Stdlib only.

    # dry run: plan and budget arithmetic only, no network
    python stage2_runner.py --tickets T01 --reps 1 --cap-usd 0.50 --dry-run
    # pilot
    python stage2_runner.py --tickets T01 --reps 1 --caching none --cap-usd 0.50 --out pilot_s2_runs.jsonl

Order is interleaved: for ticket, for rep, for arm in (control, A, H, AH). One run = one webhook call that
runs the five stages. Rows (JSONL, append-only):
  call           one per stage that completed (HTTP 200), including stages of a run that later failed
  attempt_error  one per failed attempt (HTTP 429/529/5xx or transport), with retry-after
  run            one per run: status ok | harness_error, attempts, totals
  budget_stop    written when the dollar cap stops the runner
Completed-stage usage of a failed attempt is billed, so it is logged as `call` rows with that attempt number.

The API key is checked for presence only; it is never printed, written to a file, or put in the payload.
"""
import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import stage2_cost as cost

HERE = Path(__file__).parent
ARMS = ["control", "A", "H", "AH"]
STAGES = ["triage", "requirements", "plan", "review", "release_note"]
MARK = "SDLC_STAGE_FAILED "
INPUT_BOUND = 20_000  # tokens per stage; only for the budget estimate before any run has finished


def post(url, body, timeout):
    """Return (status, parsed_json, headers). HTTP error bodies are returned, not raised."""
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            data = json.loads(raw)
        except ValueError:
            data = {"message": raw}
        return e.code, data, dict(e.headers)


def read_rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_failure(message):
    """Extract the JSON payload from an SDLC_STAGE_FAILED error message, or None."""
    i = message.find(MARK)
    if i < 0:
        return None
    try:
        return json.loads(message[i + len(MARK):])
    except ValueError:
        return None


def backoff_s(attempt, retry_after, sleep_scale):
    if retry_after is not None:
        try:
            return min(float(retry_after), 600.0) * sleep_scale
        except (TypeError, ValueError):
            pass
    return (min(20.0 * 2 ** (attempt - 1), 300.0) + random.uniform(0, 5)) * sleep_scale


def worst_case_run_usd(prices, model, max_tokens):
    p = prices[model]
    per_stage = (INPUT_BOUND * p["input"] + max_tokens * p["output"]) / 1_000_000
    return per_stage * len(STAGES)


def attempt_once(a, payload, post_fn, log, run_id, attempt, tid, rep, arm):
    """One webhook call. Returns (ok, completed_stage_items, retry_after, http_code).

    Completed stages are returned even when the run fails: their usage is billed and the caller logs it.
    """
    base = {"run_id": run_id, "attempt": attempt, "arm": arm, "ticket": tid, "rep": rep}
    try:
        code, res, _headers = post_fn(a.webhook, payload, a.timeout)
    except Exception as e:  # noqa: BLE001 - transport error: whether the server billed anything is unknown
        log({"kind": "attempt_error", **base, "error_type": type(e).__name__, "error": str(e)[:300],
             "usage_known": False})
        return False, [], None, None
    if code == 200 and isinstance(res, list):
        res = res[0]
    if code == 200 and isinstance(res, dict) and "stages" in res:
        items = []
        for s in STAGES:
            st = res["stages"][s]
            if st.get("http_status") != 200:
                raise SystemExit(f"{run_id}: stage {s} http_status {st.get('http_status')} inside a 200 webhook")
            items.append((s, st))
        return True, items, None, 200
    fail = res.get("sdlc_failure") if isinstance(res, dict) else None
    if fail is None or "failed_stage" not in fail:
        msg = res.get("message", "") if isinstance(res, dict) else str(res)
        fail = parse_failure(msg)
    if fail is None or "failed_stage" not in fail:
        log({"kind": "attempt_error", **base, "http_status": code, "error": str(res)[:300], "usage_known": False})
        return False, [], None, code
    log({"kind": "attempt_error", **base, "failed_stage": fail["failed_stage"], "http_status": fail["http_status"],
         "error_type": fail["error_type"], "error": fail["error_message"], "request_id": fail["request_id"],
         "retry_after": fail["retry_after"], "usage_known": True})
    return False, list(fail["completed"].items()), fail["retry_after"], fail["http_status"]


def main(argv=None, post_fn=post):
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["anthropic", "ollama"], default="anthropic")
    ap.add_argument("--model", default=None, help="default: claude-haiku-5-5 (anthropic) or qwen3.5:9b (ollama)")
    ap.add_argument("--caching", choices=["none", "fixed"], default="none", help="none = phase A, fixed = phase B")
    ap.add_argument("--tickets", default="", help="comma list; default all tickets/T*.json")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--max-tokens", type=int, default=2048)
    ap.add_argument("--cap-usd", type=float, required=True, help="dollar cap; the runner stops before exceeding it")
    ap.add_argument("--webhook", default="http://localhost:5678/webhook/sdlc-bench-s2")
    ap.add_argument("--anthropic-base-url", default=None, help="test-only override (fake server)")
    ap.add_argument("--ollama-base-url", default="http://host.docker.internal:11434", help="as seen from n8n")
    ap.add_argument("--temperature", type=float, default=0.3, help="ollama only")
    ap.add_argument("--prices", type=Path, default=cost.PRICES_PATH)
    ap.add_argument("--out", type=Path, default=HERE / "runs_stage2.jsonl")
    ap.add_argument("--outputs", type=Path, default=HERE / "outputs_stage2.jsonl")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--max-attempts", type=int, default=4)
    ap.add_argument("--sleep-scale", type=float, default=1.0, help="multiplies every backoff sleep (tests use 0)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if a.model is None:
        a.model = "claude-haiku-5-5" if a.backend == "anthropic" else "qwen3.5:9b"

    if a.cap_usd <= 0:
        sys.exit("cap must be > 0")
    prices = cost.load_prices(a.prices)
    if a.backend == "anthropic":
        if a.model not in prices:
            sys.exit(f"no prices entry for {a.model}; add it to {a.prices} first")
        if not a.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
            sys.exit("ANTHROPIC_API_KEY is not set in this process environment")
        needed = ["input", "output"] + (["cache_write_5m", "cache_read"] if a.caching == "fixed" else [])
        todo = [k for k in needed if not isinstance(prices[a.model].get(k), (int, float))]
        if todo:
            sys.exit(f"prices for {a.model} not set: {todo} (TODO in {a.prices}); the caching phase needs them")

    ids = a.tickets.split(",") if a.tickets else sorted(p.stem for p in (HERE / "tickets").glob("T*.json"))
    arms = [x for x in ARMS if x in a.arms.split(",")]
    rows = read_rows(a.out)
    done = {r["run_id"] for r in rows if r["kind"] == "run" and r["status"] == "ok"}
    failed_attempts = {}
    for r in rows:
        if r["kind"] in ("attempt_error", "run"):
            failed_attempts[r["run_id"]] = max(failed_attempts.get(r["run_id"], 0), r.get("attempt", r.get("attempts", 0)))
    spent = sum((r.get("cost_usd") or 0.0) for r in rows if r["kind"] == "call")
    run_costs = [r["cost_usd"] for r in rows if r["kind"] == "run" and r.get("cost_usd") is not None]
    plan = [(tid, rep, arm) for tid in ids for rep in range(1, a.reps + 1) for arm in arms]

    if a.dry_run:
        pending = [p for p in plan if f"s2-{a.backend}-{a.caching}-{p[0]}-{p[2]}-r{p[1]:02d}" not in done]
        if a.backend == "anthropic":
            est = max(run_costs) if run_costs else worst_case_run_usd(prices, a.model, a.max_tokens)
            print(f"dry run: {len(plan)} planned, {len(pending)} pending, spent so far ${spent:.4f}; "
                  f"per-run estimate ${est:.4f} (worst case ${worst_case_run_usd(prices, a.model, a.max_tokens):.4f})")
        else:
            print(f"dry run: {len(pending)} pending (ollama: no dollar cost)")
        return

    def log(row):
        row["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with a.out.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def stop(reason):
        log({"kind": "budget_stop", "reason": reason, "spent_usd": round(spent, 6), "cap_usd": a.cap_usd})
        sys.exit(f"STOP: {reason}")

    for tid, rep, arm in plan:
        run_id = f"s2-{a.backend}-{a.caching}-{tid}-{arm}-r{rep:02d}"
        if run_id in done:
            continue
        ticket = json.loads((HERE / "tickets" / f"{tid}.json").read_text(encoding="utf-8"))
        diff = ticket.pop("diff")
        payload = {"run_id": run_id, "arm": arm, "backend": a.backend, "model": a.model, "caching": a.caching,
                   "max_tokens": a.max_tokens, "ticket": ticket, "diff": diff}
        if a.backend == "anthropic":
            if a.anthropic_base_url:
                payload["anthropic_base_url"] = a.anthropic_base_url
        else:
            payload.update({"ollama_base_url": a.ollama_base_url, "temperature": a.temperature, "seed": rep})

        est = max(run_costs) if run_costs else (
            worst_case_run_usd(prices, a.model, a.max_tokens) if a.backend == "anthropic" else 0.0)
        t_run = time.time()
        status, run_cost, totals = "harness_error", 0.0, cost.zero_usage()
        attempt = failed_attempts.get(run_id, 0)
        while attempt < a.max_attempts:
            attempt += 1
            if a.backend == "anthropic" and spent + est > a.cap_usd:
                stop(f"next run may exceed cap: spent ${spent:.4f} + estimate ${est:.4f} > cap ${a.cap_usd:.4f}")
            ok, items, retry_after, http_code = attempt_once(a, payload, post_fn, log, run_id, attempt, tid, rep, arm)
            for s, st in items:
                u = cost.as_usage(st.get("usage_raw"))
                c = cost.dollars(u, prices, a.model) if a.backend == "anthropic" else None
                log({"kind": "call", "run_id": run_id, "attempt": attempt, "arm": arm, "ticket": tid, "rep": rep,
                     "stage": s, "backend": a.backend, "model": a.model, "caching": a.caching,
                     "request_id": st.get("request_id"), "http_status": st.get("http_status"),
                     "stop_reason": st.get("stop_reason"), "latency_ms": st.get("latency_ms"),
                     "usage": u, "usage_raw": st.get("usage_raw"),
                     "weighted_cost_census": round(cost.weighted(u), 4), "cost_usd": c})
                with a.outputs.open("a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps({"run_id": run_id, "attempt": attempt, "stage": s,
                                        "output": st.get("output")}, ensure_ascii=False) + "\n")
                for k in totals:
                    totals[k] += u[k]
                if c is not None:
                    run_cost += c
                    spent += c
            if ok:
                status = "ok"
                break
            if spent > a.cap_usd:
                stop(f"spent ${spent:.4f} exceeded cap ${a.cap_usd:.4f} during {run_id}")
            if attempt >= a.max_attempts:
                break
            wait = backoff_s(attempt, retry_after, a.sleep_scale)
            print(f"{run_id}: attempt {attempt} failed (http {http_code}); retry in {wait:.1f}s", flush=True)
            time.sleep(wait)
        run_wall = round(time.time() - t_run, 1)
        log({"kind": "run", "run_id": run_id, "ticket": tid, "arm": arm, "rep": rep, "status": status,
             "attempts": attempt, "wall_s": run_wall, "usage_total": totals,
             "cost_usd": round(run_cost, 6) if a.backend == "anthropic" else None,
             "weighted_cost_census_total": round(cost.weighted(totals), 4), "backend": a.backend,
             "model": a.model, "caching": a.caching})
        if status == "ok":
            done.add(run_id)
            if a.backend == "anthropic":
                run_costs.append(run_cost)
        print(f"{run_id}: {status} attempts={attempt} wall={run_wall}s cost=${run_cost:.5f}", flush=True)
        if spent > a.cap_usd:
            stop(f"spent ${spent:.4f} exceeded cap ${a.cap_usd:.4f}")


if __name__ == "__main__":
    main()
