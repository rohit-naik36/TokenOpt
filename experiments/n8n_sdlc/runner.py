"""Driver for the n8n SDLC benchmark. Resumable; appends JSONL; stdlib only.

    python runner.py --out runs.jsonl                       # all tickets, 1 rep
    python runner.py --tickets T01 --reps 1 --out pilot.jsonl

Order is interleaved: for ticket, for rep, for arm in (control, A, H, AH).
Rows: one "stage" row per stage of each successful run, then one "run" row (the commit marker).
A run with status "harness_error" (HTTP/transport/Ollama/malformed response) is recorded separately,
is never scored as a quality failure, and is retried on the next invocation (max --max-attempts).
Ground truth is not read here.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
ARMS = ["control", "A", "H", "AH"]
STAGES = ["triage", "requirements", "plan", "review", "release_note"]


def post(url, body, timeout):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def load_done(path):
    ok, errors = set(), {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["kind"] == "run":
                if r["status"] == "ok":
                    ok.add(r["run_id"])
                else:
                    errors[r["run_id"]] = errors.get(r["run_id"], 0) + 1
    return ok, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", default="http://localhost:5678/webhook/sdlc-bench")
    ap.add_argument("--ollama-base-url", default="http://host.docker.internal:11434", help="as seen from n8n")
    ap.add_argument("--ollama-host", default="http://localhost:11434", help="as seen from this script (model unload)")
    ap.add_argument("--model", default="qwen3.5:9b")
    ap.add_argument("--tickets", default="", help="comma list; default all tickets/T*.json")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--out", type=Path, default=HERE / "runs.jsonl")
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--max-attempts", type=int, default=2)
    ap.add_argument("--no-unload", action="store_true", help="keep the model loaded between runs (warms the KV cache)")
    a = ap.parse_args()

    ids = a.tickets.split(",") if a.tickets else sorted(p.stem for p in (HERE / "tickets").glob("T*.json"))
    ok, errors = load_done(a.out)
    for tid in ids:
        ticket = json.loads((HERE / "tickets" / f"{tid}.json").read_text(encoding="utf-8"))
        diff = ticket.pop("diff")
        for rep in range(1, a.reps + 1):
            for arm in ARMS:
                run_id = f"{tid}-{arm}-r{rep:02d}"
                if run_id in ok or errors.get(run_id, 0) >= a.max_attempts:
                    continue
                if not a.no_unload:
                    post(a.ollama_host + "/api/generate", {"model": a.model, "keep_alive": 0}, 120)
                payload = {"run_id": run_id, "arm": arm, "model": a.model, "ollama_base_url": a.ollama_base_url,
                           "ticket": ticket, "diff": diff}
                t0, status, err, res = time.time(), "ok", None, None
                try:
                    res = post(a.webhook, payload, a.timeout)
                    if isinstance(res, list):
                        res = res[0]
                    for s in STAGES:
                        st = res["stages"][s]
                        if not isinstance(st.get("eval_count"), int) or not isinstance(st.get("prompt_eval_count"), int):
                            raise ValueError(f"stage {s} missing token counts")
                except Exception as e:  # noqa: BLE001 - every failure here is a harness error by definition
                    status, err = "harness_error", f"{type(e).__name__}: {e}"[:500]
                wall = round(time.time() - t0, 1)
                with a.out.open("a", encoding="utf-8", newline="\n") as f:
                    if status == "ok":
                        for s in STAGES:
                            f.write(json.dumps({"kind": "stage", "run_id": run_id, "ticket_id": tid, "arm": arm, "rep": rep,
                                                "stage": s, **res["stages"][s]}) + "\n")
                    f.write(json.dumps({"kind": "run", "run_id": run_id, "ticket_id": tid, "arm": arm, "rep": rep,
                                        "status": status, "error": err, "wall_s": wall, "model": a.model,
                                        "unloaded_before": not a.no_unload,
                                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}) + "\n")
                print(f"{run_id}: {status} {wall}s {err or ''}", flush=True)


if __name__ == "__main__":
    main()
