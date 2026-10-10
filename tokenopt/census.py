"""SDLC token/cost census: where do an agent's tokens and (weighted) dollars go?

    python -m tokenopt.census <trace dir> [<trace dir> ...] [--json PATH]
        [--cached 0.1] [--output 4]

Offline, no model calls. Inputs are auto-detected under each dir (recursively):
  * agent-trace/v1 JSONL (one request/response per row, with `messages`)
  * Aegis run dirs (`events.jsonl` + `raw/stream.jsonl`)

Truth = provider usage (prompt, cached, completion). o200k_base counts are used only to apportion a
turn's provider prompt tokens among its context items. Weighted cost =
uncached*1 + cached*W_C + output*W_O
(ASSUMED prices, printed). Position model: the cached prefix covers the first `cached` tokens of
[static, item1, item2, ...] in context order. Upper bounds are shares at 100% removal;
no compression
rate is assumed.

Optional multi-agent fields on agent-trace v1 rows (rows without them parse unchanged):
    workflow_id, parent_workflow_id, agent, step
    handoff = {"payload_tokens": int, "used_tokens": int}
If any row carries a `handoff` object, the handoff payload share is
sum(payload_tokens) / total (prompt + completion) tokens of the set; otherwise it prints UNKNOWN.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

W_C, W_O = 0.1, 4.0
BREAK_MIN_TOKENS, BREAK_FRAC = 256, 0.05  # break = shortfall >= max(256 tok, 5% of previous prompt)
CATS = ["tr_test_ci", "tr_json_logs", "tr_diffs", "tr_file_reads", "tr_other"]
STATIC, HIST = "static(system+tools+task)", "assistant_history"
LABEL = {
    "tr_test_ci": "tool: test/CI/build",
    "tr_json_logs": "tool: JSON/logs",
    "tr_diffs": "tool: diffs",
    "tr_file_reads": "tool: file reads",
    "tr_other": "tool: other",
    STATIC: "static prefix",
    HIST: "assistant history",
    "output": "output",
}
HANDLERS = {
    "test/CI/build output handler": "tr_test_ci",
    "JSON/log handler": "tr_json_logs",
    "diff handler": "tr_diffs",
    "file-read (outline) handler": "tr_file_reads",
}
CAVEAT = (
    "CAVEAT: upper bounds, not savings. Small n and one regime per set (local models, short "
    "synthetic SDLC tasks); do not extrapolate to other workloads."
)

Item = tuple[str, float, Any]  # (category, tokens, first-entry key or None)
Session = dict[str, Any]
Acct = dict[str, Any]


def _num(v: Any) -> float:
    """Cached counts may be the string "UNKNOWN" (server did not report): treat as 0 cached."""
    return float(v) if isinstance(v, (int, float)) else 0.0


def _make_counter() -> Callable[[str], int]:
    import tiktoken

    enc = tiktoken.get_encoding("o200k_base")
    return lambda s: len(enc.encode(s, disallowed_special=()))


_COUNT: Callable[[str], int] | None = None


def count(s: str) -> int:
    global _COUNT
    if _COUNT is None:
        _COUNT = _make_counter()
    return _COUNT(s)


def message_tokens(m: dict[str, Any]) -> int:
    n = 4
    c = m.get("content")
    if isinstance(c, str):
        n += count(c)
    elif isinstance(c, list):
        n += count(json.dumps(c, ensure_ascii=False))
    for tc in m.get("tool_calls") or []:
        n += count(json.dumps(tc, ensure_ascii=False))
    if m.get("name"):
        n += count(str(m["name"]))
    return n


# ---------------------------------------------------------------- classifier
TEST_CMD = re.compile(
    r"\b(pytest|unittest|tox|nox|ruff|mypy|flake8|pylint|npm (run )?(test|build|lint)|yarn (test|build)|jest|cargo (test|build|check)|go (test|build|vet)|make( test| build| check)?|tsc|mvn|gradle)\b"  # noqa: E501
)  # noqa: E501
DIFF_CMD = re.compile(r"\bgit (diff|show)\b|\bgit log\b.*\s-p\b|^\s*diff\s")
READ_CMD = re.compile(r"^\s*(cat|head|tail|sed -n|ls|find|grep|rg|tree|wc|type)\b")
READ_TOOLS = {"read", "grep", "glob", "ls", "view", "list", "search", "find"}
OTHER_TOOLS = {"edit", "write", "multiedit", "todowrite", "notebookedit"}
DIFF_TXT = re.compile(r"(^diff --git |^@@ -\d+(,\d+)? \+\d+(,\d+)? @@|^--- a/|^\+\+\+ b/)", re.M)
TEST_TXT = re.compile(
    r"(={3,} .*(test session|FAILURES|short test summary|passed|failed)|\b\d+ (passed|failed)\b|^FAILED |^PASSED |Traceback \(most recent call last\)|AssertionError|\bAll checks passed\b|Success: no issues|error TS\d+)",  # noqa: E501
    re.M,
)  # noqa: E501
LOG_TXT = re.compile(
    r"^\s*(\d{4}-\d\d-\d\d[T ]\d\d:\d\d|\[?(INFO|WARN|WARNING|ERROR|DEBUG)\]?\b)", re.M
)


def _is_json(t: str) -> bool:
    t = t.strip()
    if not t or t[0] not in "{[":
        return False
    try:
        json.loads(t)
        return True
    except ValueError:
        return False


def content_class(text: str) -> str:
    if DIFF_TXT.search(text):
        return "tr_diffs"
    if TEST_TXT.search(text):
        return "tr_test_ci"
    if _is_json(text) or len(LOG_TXT.findall(text)) >= 3:
        return "tr_json_logs"
    return "tr_other"


def classify(name: str | None, args: dict[str, Any] | None, text: str) -> str:
    """Tool name first, then command regex for shell tools, then content heuristics."""
    n = (name or "").lower()
    if n in READ_TOOLS:
        return "tr_file_reads"
    if n in OTHER_TOOLS:
        return "tr_other"
    if n in ("bash", "shell", "run", "execute", "command"):
        a = args or {}
        cmd = str(a.get("command", a.get("cmd", "")))
        if DIFF_CMD.search(cmd):
            return "tr_diffs"
        if TEST_CMD.search(cmd):
            return "tr_test_ci"
        if READ_CMD.search(cmd):
            return "tr_file_reads"
    return content_class(text)


def _canon(x: Any) -> str:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip().startswith("{")]


# ---------------------------------------------------------------- session loaders
def trace_session(path: Path, rows: list[dict[str, Any]]) -> Session:
    calls: dict[str, tuple[str, dict[str, Any]]] = {}
    turns: list[tuple[int, int, int]] = []
    ctx: list[list[Item]] = []
    handoff = {"payload": 0, "used": 0, "n": 0}
    for r in rows:
        u = r["response"]["usage"]
        msgs = r["request"]["messages"]
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                a = tc["function"]["arguments"]
                calls[tc["id"]] = (
                    tc["function"]["name"],
                    json.loads(a) if isinstance(a, str) else a,
                )
        items: list[Item] = []
        static_tok = count(json.dumps(r["request"].get("tools") or []))
        for i, m in enumerate(msgs):
            tok = message_tokens(m)
            if m["role"] in ("system", "user") and not any(
                x["role"] == "assistant" for x in msgs[:i]
            ):
                static_tok += tok
            elif m["role"] == "tool":
                nm, args = calls.get(m.get("tool_call_id", ""), (m.get("name"), {}))
                c = m.get("content")
                items.append(
                    (classify(nm, args, c if isinstance(c, str) else json.dumps(c)), tok, ("oc", i))
                )
            else:
                items.append((HIST, tok, None))
        ctx.append([(STATIC, static_tok, None), *items])
        turns.append(
            (
                u["prompt_tokens"],
                int(_num((u.get("prompt_tokens_details") or {}).get("cached_tokens"))),
                u["completion_tokens"],
            )
        )
        h = r.get("handoff")
        if isinstance(h, dict) and "payload_tokens" in h:
            handoff["payload"] += int(h["payload_tokens"])
            handoff["used"] += int(h.get("used_tokens", 0))
            handoff["n"] += 1
    known = all(
        isinstance(
            (r["response"]["usage"].get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            (int, float),
        )
        for r in rows
    )
    return {
        "id": path.stem,
        "turns": turns,
        "ctx": ctx,
        "aegis": False,
        "handoff": handoff,
        "cache_known": known,
    }


def aegis_session(run_dir: Path) -> Session:
    ev = _jsonl(run_dir / "events.jsonl")
    msgs: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    results: dict[str, str] = {}
    for e in _jsonl(run_dir / "raw" / "stream.jsonl"):
        if e.get("type") == "assistant":
            mid = e["message"]["id"]
            if mid not in msgs:
                msgs[mid] = {"text": [], "tools": {}}
                order.append(mid)
            for b in e["message"]["content"]:
                if b["type"] == "tool_use":
                    msgs[mid]["tools"][b["id"]] = (b["name"], b.get("input") or {})
                elif b["type"] == "text" and b["text"] not in msgs[mid]["text"]:
                    msgs[mid]["text"].append(b["text"])
        elif e.get("type") == "user":
            for b in e["message"]["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b["content"]
                    results[b["tool_use_id"]] = (
                        c if isinstance(c, str) else "".join(x.get("text", "") for x in c)
                    )
    turns = [(x["input_tokens"], x["cached_prefix_tokens"], x["output_tokens"]) for x in ev]
    n = len(turns)
    entering: list[list[Item]] = []
    for mid in order[:n]:
        m = msgs[mid]
        h = (
            count("\n".join(m["text"]))
            + sum(count(nm + " " + _canon(a)) for nm, a in m["tools"].values())
            + 4
        )
        its: list[Item] = [(HIST, h, None)]
        for tid, (nm, a) in m["tools"].items():
            if tid in results:  # thinking excluded: echo into context UNKNOWN
                its.append(
                    (
                        classify(nm, a, results[tid]),
                        count(results[tid]) + 4,
                        ("ae", run_dir.name, tid),
                    )
                )
        entering.append(its)
    ctx: list[list[Item]] = []
    for j in range(n):
        ctx.append(
            [(STATIC, 0, None)] + [it for i in range(min(j, len(entering))) for it in entering[i]]
        )
    # unaligned = stream has more assistant messages than usage events: item order not trustworthy
    return {
        "id": run_dir.name,
        "turns": turns,
        "ctx": ctx,
        "aegis": True,
        "aligned": len(order) == n,
        "handoff": {"payload": 0, "used": 0, "n": 0},
    }


def load_sessions(root: Path) -> list[Session]:
    sess: list[Session] = []
    for ev in sorted(root.rglob("events.jsonl")):
        if (ev.parent / "raw" / "stream.jsonl").is_file():
            s = aegis_session(ev.parent)
            if s["aligned"]:
                sess.append(s)
    for p in sorted(root.rglob("*.jsonl")):
        if p.name in ("events.jsonl", "stream.jsonl"):
            continue
        rows = _jsonl(p)
        if (
            rows
            and str(rows[0].get("trace_version", "")).startswith("agent-trace")
            and "messages" in rows[0].get("request", {})
        ):
            sess.append(trace_session(p, rows))
    return sess


# ---------------------------------------------------------------- accounting
def account(s: Session, wc: float = W_C, wo: float = W_O) -> Acct:
    T, ctx = s["turns"], s["ctx"]
    cat: dict[str, dict[str, float]] = collections.defaultdict(
        lambda: collections.defaultdict(float)
    )
    seen: set[Any] = set()
    turn_w: list[float] = []
    breaks: list[int] = []
    for j, (p, c, o) in enumerate(T):
        items: list[Item] = list(ctx[j])
        if s["aegis"]:
            items[0] = (STATIC, T[0][0], None)
            est = sum(t for _, t, _ in items[1:])
            sc = (p - T[0][0]) / est if est and j else 0.0
            sizes = [float(p)] if j == 0 else [float(T[0][0])] + [t * sc for _, t, _ in items[1:]]
        else:
            est = sum(t for _, t, _ in items) or 1
            sizes = [t * p / est for _, t, _ in items]
        exp = T[j - 1][0] if j else 0
        shortfall = exp - c if j and exp - c >= max(BREAK_MIN_TOKENS, BREAK_FRAC * exp) else 0
        pos = w_turn = 0.0
        for (k, _, key), sz in zip(items, sizes):
            cached = max(0.0, min(sz, c - pos))
            unc = sz - cached
            first = key is not None and key not in seen
            if key is not None:
                seen.add(key)
            miss = max(0.0, min(pos + sz, exp) - max(pos, c)) if shortfall else 0.0
            d = cat[k]
            d["unc"] += unc
            d["cac"] += cached
            d["break_extra_w"] += miss * (1 - wc)
            if key is not None:
                tag = "first" if first else "reb"
                d[tag + "_unc"] += unc
                d[tag + "_cac"] += cached
            pos += sz
            w_turn += unc + wc * cached
        turn_w.append(w_turn + wo * o)
        if shortfall and s.get("cache_known", True):
            breaks.append(shortfall)
    return {
        "turns": len(T),
        "P": sum(t[0] for t in T),
        "C": sum(t[1] for t in T),
        "O": sum(t[2] for t in T),
        "cat": {k: dict(v) for k, v in cat.items()},
        "breaks": breaks,
        "turn_w": turn_w,
    }


def pool(accts: list[Acct]) -> Acct:
    m: Acct = {"turns": 0, "P": 0, "C": 0, "O": 0, "cat": {}, "breaks": [], "turn_w": []}
    for a in accts:
        for k in ("turns", "P", "C", "O"):
            m[k] += a[k]
        m["breaks"] += a["breaks"]
        m["turn_w"] += a["turn_w"]
        for k, v in a["cat"].items():
            d = m["cat"].setdefault(k, collections.defaultdict(float))
            for kk, vv in v.items():
                d[kk] += vv
    m["avg_turn_share"] = sum(1 / a["turns"] for a in accts) / len(
        accts
    )  # avg turn as share of its own session
    m["n_sessions"] = len(accts)
    return m


def shares(a: Acct, wc: float = W_C, wo: float = W_O) -> dict[str, Any]:
    tot = a["P"] + a["O"]
    W = sum(v["unc"] + wc * v["cac"] for v in a["cat"].values()) + wo * a["O"]
    rows: dict[str, dict[str, float]] = {}
    for k, v in a["cat"].items():
        row = {
            "tok": (v["unc"] + v["cac"]) / tot,
            "w": (v["unc"] + wc * v["cac"]) / W,
            "break_extra_w": v["break_extra_w"] / W,
        }
        if k in CATS:
            row.update(
                first_tok=(v.get("first_unc", 0) + v.get("first_cac", 0)) / tot,
                first_w=(v.get("first_unc", 0) + wc * v.get("first_cac", 0)) / W,
                rebill_tok=(v.get("reb_unc", 0) + v.get("reb_cac", 0)) / tot,
                rebill_w=(v.get("reb_unc", 0) + wc * v.get("reb_cac", 0)) / W,
            )
        rows[k] = row
    rows["output"] = {"tok": a["O"] / tot, "w": wo * a["O"] / W}
    return {
        "rows": rows,
        "n_breaks": len(a["breaks"]),
        "break_w": sum(a["breaks"]) * (1 - wc) / W,
        "avg_turn_share": a["avg_turn_share"],
        "n_sessions": a["n_sessions"],
        "n_turns": a["turns"],
        "total_tokens": tot,
    }


def levers(sh: dict[str, Any], handoff_ub: float | None) -> list[dict[str, Any]]:
    r = sh["rows"]
    out = [
        {
            "lever": n,
            "tag": "handler",
            "w_ub": r.get(k, {}).get("w", 0.0),
            "tok_ub": r.get(k, {}).get("tok", 0.0),
        }
        for n, k in HANDLERS.items()
    ]
    out.append(
        {
            "lever": "output-token reduction",
            "tag": "turn reduction",
            "w_ub": r["output"]["w"],
            "tok_ub": r["output"]["tok"],
        }
    )
    out.append(
        {
            "lever": "cache-prefix-break avoidance",
            "tag": "cache discipline",
            "w_ub": sh["break_w"],
            "tok_ub": 0.0,
        }
    )  # tokens are billed either way; only price changes
    out.append(
        {
            "lever": "one-turn reduction (avg turn)",
            "tag": "turn reduction",
            "w_ub": sh["avg_turn_share"],
            "tok_ub": sh["avg_turn_share"],
        }
    )  # overlaps every other lever
    out.append(
        {
            "lever": "handoff payload",
            "tag": "handoff contract",
            "w_ub": handoff_ub,
            "tok_ub": handoff_ub,
        }
    )
    return sorted(out, key=lambda x: 1.0 if x["w_ub"] is None else -x["w_ub"])


def census(root: Path, wc: float = W_C, wo: float = W_O) -> dict[str, Any] | None:
    sess = load_sessions(root)
    if not sess:
        return None
    sh = shares(pool([account(s, wc, wo) for s in sess]), wc, wo)
    h_n = sum(s["handoff"]["n"] for s in sess)
    h = None
    if h_n:
        pay, used = (
            sum(s["handoff"]["payload"] for s in sess),
            sum(s["handoff"]["used"] for s in sess),
        )
        h = {"payload_tokens": pay, "used_tokens": used, "share": pay / sh["total_tokens"]}
    sh["handoff"] = h
    sh["cache_known"] = all(x.get("cache_known", True) for x in sess)
    sh["levers"] = levers(sh, h["share"] if h else None)
    if not sh["cache_known"]:
        for lv in sh["levers"]:
            if lv["tag"] == "cache discipline":
                lv["w_ub"] = lv["tok_ub"] = None
    return sh


# ---------------------------------------------------------------- report
def pct(x: float | None) -> str:
    return "UNKNOWN" if x is None else f"{100 * x:5.1f}%"


def render(name: str, sh: dict[str, Any]) -> str:
    L = [
        f"\n== {name}: {sh['n_sessions']} sessions, {sh['n_turns']} turns, {sh['total_tokens']} tokens ==",  # noqa: E501
        f"{'component':22s}{'tok%':>8s}{'cost%':>8s}{'first-entry cost%':>19s}{'re-billed cost%':>17s}",  # noqa: E501
    ]
    for k in [STATIC, HIST, *CATS, "output"]:
        x = sh["rows"].get(k)
        if x is None:
            continue
        fr = (pct(x["first_w"]), pct(x["rebill_w"])) if "first_w" in x else ("", "")
        L.append(f"{LABEL[k]:22s}{pct(x['tok']):>8s}{pct(x['w']):>8s}{fr[0]:>19s}{fr[1]:>17s}")
    L.append(
        "cache-prefix breaks: UNKNOWN (server did not report cached tokens)"
        if not sh.get("cache_known", True)
        else f"cache-prefix breaks: {sh['n_breaks']}, cost {pct(sh['break_w'])} of weighted cost; "
        f"avg turn = {pct(sh['avg_turn_share'])} of its session"
    )
    h = sh["handoff"]
    L.append(
        "handoff payload: "
        + (
            "UNKNOWN (no rows with workflow fields + handoff object)"
            if h is None
            else f"{pct(h['share'])} of tokens sent once ({h['payload_tokens']} payload, {h['used_tokens']} used; excludes re-billing across later turns, see experiments/nested_trace)"  # noqa: E501
        )
    )
    L.append("levers ranked by upper bound at 100% removal (cost% / tok%):")
    for i, lv in enumerate(sh["levers"], 1):
        L.append(f"  {i}. {lv['lever']:32s}[{lv['tag']}] {pct(lv['w_ub'])} / {pct(lv['tok_ub'])}")
    L.append(CAVEAT)
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tokenopt.census", description=__doc__.split("\n")[0])
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--json", type=Path, help="also write results as JSON")
    ap.add_argument("--cached", type=float, default=W_C, help="cached-token price (uncached = 1)")
    ap.add_argument("--output", type=float, default=W_O, help="output-token price (uncached = 1)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(
        f"Price assumptions (relative to uncached input): uncached 1, cached {a.cached}, output {a.output}"  # noqa: E501
    )
    res: dict[str, Any] = {
        "prices": {"uncached": 1.0, "cached": a.cached, "output": a.output},
        "sets": {},
    }
    for d in a.dirs:
        sh = census(d, a.cached, a.output)
        if sh is None:
            print(f"\n== {d}: no agent-trace/v1 or Aegis run data found ==")
            continue
        res["sets"][d.name] = sh
        print(render(d.name, sh))
    if a.json:
        a.json.write_text(json.dumps(res, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
