"""Blind API judge for Stage 2 (pre-registered in STAGE2_PREREGISTRATION.md section 9).

    # no network: packet count and cost estimate only
    python stage2_judge.py --dry-run
    # real run (needs ANTHROPIC_API_KEY in YOUR shell; never written to a file)
    python stage2_judge.py --cap-usd 2.50

Judge: claude-sonnet-4-6, temperature 0, rubric in judge_rubric.md as the system prompt, one packet per call.
Packets in blind_s2/ carry no arm, run id or rep. Scores go to judge_s2_scores.jsonl (append-only, resumable).
Do NOT open blind_map_s2.json until this file is final. Stdlib only.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
MODEL = "claude-sonnet-4-6"
URL = "https://api.anthropic.com/v1/messages"
PRICE_IN, PRICE_OUT = 3.00, 15.00  # USD per million tokens, Sonnet 4.6 base tier; verify on the pricing page
MAX_OUT = 400
KEYS = ["requirements", "plan", "review", "release_note"]


def parse(text):
    t = text.strip()
    m = re.search(r"\{.*\}", t, re.S)
    d = json.loads(m.group(0) if m else t)
    for k, hi in zip(KEYS, (3, 2, 3, 2)):
        if not isinstance(d.get(k), int) or not 0 <= d[k] <= hi:
            raise ValueError(f"bad {k}")
    d["total"] = sum(d[k] for k in KEYS)  # recompute; never trust the model's arithmetic
    d["note"] = str(d.get("note", ""))[:300]
    return d


def call(key, system, packet):
    body = {"model": MODEL, "max_tokens": MAX_OUT, "temperature": 0, "system": system,
            "messages": [{"role": "user", "content": packet}]}
    req = urllib.request.Request(URL, json.dumps(body).encode(), {
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap-usd", type=float, default=2.50)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="judge_s2_scores.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="judge only the first N unscored packets (connectivity test)")
    a = ap.parse_args()
    system = (HERE / "judge_rubric.md").read_text(encoding="utf-8")
    packets = sorted((HERE / "blind_s2").glob("*.md"))
    out = HERE / a.out
    done = {json.loads(l)["id"] for l in out.read_text(encoding="utf-8").splitlines() if l.strip()} if out.exists() else set()
    todo = [p for p in packets if p.stem not in done]
    if a.limit:
        todo = todo[: a.limit]
    est_in = sum(len(p.read_text(encoding="utf-8")) + len(system) for p in todo) / 3.5  # conservative chars/token
    est = est_in / 1e6 * PRICE_IN + len(todo) * 150 / 1e6 * PRICE_OUT
    print(f"{len(packets)} packets, {len(done)} already scored, {len(todo)} to do; estimated cost about ${est:.2f} (cap ${a.cap_usd:.2f})")
    if a.dry_run:
        return
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("ANTHROPIC_API_KEY is not set in this shell")
    if est > a.cap_usd:
        sys.exit("estimate exceeds the cap; raise --cap-usd or judge fewer packets")
    spent = 0.0
    for i, p in enumerate(todo, 1):
        packet = p.read_text(encoding="utf-8")
        for attempt in (1, 2, 3):
            try:
                r = call(key, system, packet)
                u = r["usage"]
                spent += u["input_tokens"] / 1e6 * PRICE_IN + u["output_tokens"] / 1e6 * PRICE_OUT
                d = parse(r["content"][0]["text"])
                break
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 529) and attempt < 3:
                    time.sleep(10 * attempt)
                    continue
                sys.exit(f"HTTP {e.code} on packet {p.stem}: {e.read().decode('utf-8', 'replace')[:300]}\nstopped. Spent about ${spent:.3f}")
            except (TimeoutError, urllib.error.URLError, ConnectionError) as e:
                # network stall: a timed-out request may still have been billed, so spend can be understated
                print(f"  packet {p.stem} attempt {attempt}: {type(e).__name__}; retrying", flush=True)
                if attempt == 3:
                    sys.exit(f"network failure on packet {p.stem}; stopped. Check connection, VPN or proxy. Spent about ${spent:.3f} (timed-out calls not counted)")
                time.sleep(15 * attempt)
            except (ValueError, KeyError, json.JSONDecodeError):
                if attempt == 3:
                    sys.exit(f"unparseable judge reply for {p.stem}; stopped. Spent about ${spent:.3f}")
        with out.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": p.stem, **{k: d[k] for k in KEYS}, "total": d["total"], "note": d["note"]}) + "\n")
        if spent > a.cap_usd:
            sys.exit(f"cap reached after {i} packets; about ${spent:.3f} spent")
        if i == 1 or i % 20 == 0:
            print(f"{i}/{len(todo)} judged, about ${spent:.3f} spent", flush=True)
    print(f"done: {len(todo)} packets, about ${spent:.3f}")


if __name__ == "__main__":
    main()
