"""Phase 1b SDLC token/cost census. Offline: no model calls, no network, read-only on existing artifacts.

  .venv/Scripts/python.exe experiments/sdlc_census/census.py   -> results/census.json

Truth = provider usage fields (prompt, cached, completion). o200k (tcc.tok) is used ONLY to apportion a turn's
provider prompt tokens among its context items. Weighted cost W = uncached*1 + cached*W_C + output*W_O (ASSUMED prices).
Position model: the cached prefix covers the first `cached` tokens of [static, item1, item2, ...] in context order.
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(EXP, "context_codec"))
from tcc.tok import counter, message_tokens  # noqa: E402

C = counter()
W_C, W_O = 0.1, 4.0                                  # ASSUMED prices (prior reports); sensitivity GRID below
GRID = [(c, o) for c in (0.05, 0.1, 0.25, 0.5) for o in (1.0, 4.0, 8.0)]   # same as cost_census.py
BREAK_MIN_TOKENS, BREAK_FRAC = 256, 0.05             # a cache-prefix break = shortfall >= max(256 tok, 5% of previous prompt)
CATS = ["tr_test_ci", "tr_json_logs", "tr_diffs", "tr_file_reads", "tr_other"]
STATIC, HIST = "static(system+tools+task)", "assistant_history"

# ---------------------------------------------------------------- classifier
TEST_CMD = re.compile(r"\b(pytest|unittest|tox|nox|ruff|mypy|flake8|pylint|npm (run )?(test|build|lint)|yarn (test|build)|jest|cargo (test|build|check)|go (test|build|vet)|make( test| build| check)?|tsc|mvn|gradle)\b")
DIFF_CMD = re.compile(r"\bgit (diff|show)\b|\bgit log\b.*\s-p\b|^\s*diff\s")
READ_CMD = re.compile(r"^\s*(cat|head|tail|sed -n|ls|find|grep|rg|tree|wc|type)\b")
READ_TOOLS = {"read", "grep", "glob", "ls", "view", "list", "search", "find"}
OTHER_TOOLS = {"edit", "write", "multiedit", "todowrite", "notebookedit"}
DIFF_TXT = re.compile(r"(^diff --git |^@@ -\d+(,\d+)? \+\d+(,\d+)? @@|^--- a/|^\+\+\+ b/)", re.M)
TEST_TXT = re.compile(r"(={3,} .*(test session|FAILURES|short test summary|passed|failed)|\b\d+ (passed|failed)\b|^FAILED |^PASSED |Traceback \(most recent call last\)|AssertionError|\bAll checks passed\b|Success: no issues|error TS\d+)", re.M)
LOG_TXT = re.compile(r"^\s*(\d{4}-\d\d-\d\d[T ]\d\d:\d\d|\[?(INFO|WARN|WARNING|ERROR|DEBUG)\]?\b)", re.M)


def is_json(t):
    t = t.strip()
    if not t or t[0] not in "{[":
        return False
    try:
        json.loads(t)
        return True
    except ValueError:
        return False


def content_class(text):
    if DIFF_TXT.search(text):
        return "tr_diffs"
    if TEST_TXT.search(text):
        return "tr_test_ci"
    if is_json(text) or len(LOG_TXT.findall(text)) >= 3:
        return "tr_json_logs"
    return "tr_other"


def classify(name, args, text):
    """Tool name first, then command regex for shell tools, then content heuristics. Returns a CATS member."""
    n = (name or "").lower()
    if n in READ_TOOLS:
        return "tr_file_reads"
    if n in OTHER_TOOLS:
        return "tr_other"
    if n in ("bash", "shell", "run", "execute", "command"):
        cmd = str((args or {}).get("command", (args or {}).get("cmd", "")))
        if DIFF_CMD.search(cmd):
            return "tr_diffs"
        if TEST_CMD.search(cmd):
            return "tr_test_ci"
        if READ_CMD.search(cmd):
            return "tr_file_reads"
    return content_class(text)


# ---------------------------------------------------------------- session model
def canon(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def opencode_session(path):
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    calls = {}
    turns, ctx, prefix_ok = [], [], True
    prev = None
    for k, r in enumerate(rows):
        u = r["response"]["usage"]
        msgs = r["request"]["messages"]
        if prev is not None and msgs[:len(prev)] != prev:
            prefix_ok = False
        prev = msgs
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                a = tc["function"]["arguments"]
                calls[tc["id"]] = (tc["function"]["name"], json.loads(a) if isinstance(a, str) else a)
        items, static_tok = [], C(json.dumps(r["request"].get("tools") or []))
        for i, m in enumerate(msgs):
            tok = message_tokens(m, C)
            if m["role"] in ("system", "user") and not any(x["role"] == "assistant" for x in msgs[:i]):
                static_tok += tok
            elif m["role"] == "assistant":
                items.append((HIST, tok, None))
            elif m["role"] == "tool":
                nm, args = calls.get(m.get("tool_call_id"), (m.get("name"), {}))
                txt = m["content"] if isinstance(m.get("content"), str) else json.dumps(m.get("content"))
                items.append((classify(nm, args, txt), tok, ("oc", i)))
            else:
                items.append((HIST, tok, None))
        ctx.append([(STATIC, static_tok, None)] + items)
        turns.append((u["prompt_tokens"], (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0, u["completion_tokens"]))
    out_split = collections.Counter()
    for r in rows:
        msg = r["response"]["message"]
        out_split["reasoning"] += C(msg.get("reasoning") or "")
        out_split["visible_text"] += C(msg.get("content") or "")
        for tc in msg.get("tool_calls") or []:
            out_split["tool_call_args"] += C(tc["function"]["name"] + " " + str(tc["function"]["arguments"]))
    tools = collections.Counter(c[0] for c in calls.values())
    return {"id": os.path.basename(path), "set": "opencode", "turns": turns, "ctx": ctx, "prefix_ok": prefix_ok, "out_split_est": dict(out_split),
            "tool_calls": dict(tools), "session_ids": sorted({r["session_id"] for r in rows}), "has_content": True, "tool_results": ctx_results(ctx)}


def ctx_results(ctx):
    return sum(1 for it in ctx[-1] if it[0] in CATS)


def aegis_session(run_dir, set_name):
    ev = [json.loads(line) for line in open(os.path.join(run_dir, "events.jsonl")) if line.strip()]
    msgs, order, results, sids, sidechain = {}, [], {}, set(), 0
    for line in open(os.path.join(run_dir, "raw", "stream.jsonl"), encoding="utf-8"):
        if not line.startswith("{"):
            continue
        e = json.loads(line)
        if e.get("session_id"):
            sids.add(e["session_id"])
        if e.get("parent_tool_use_id"):
            sidechain += 1
        if e.get("type") == "assistant":
            mid = e["message"]["id"]
            if mid not in msgs:
                msgs[mid] = {"text": [], "think": [], "tools": {}}
                order.append(mid)
            for b in e["message"]["content"]:
                if b["type"] == "tool_use":
                    msgs[mid]["tools"][b["id"]] = (b["name"], b.get("input") or {})
                elif b["type"] == "text" and b["text"] not in msgs[mid]["text"]:
                    msgs[mid]["text"].append(b["text"])
                elif b["type"] == "thinking" and b["thinking"] not in msgs[mid]["think"]:
                    msgs[mid]["think"].append(b["thinking"])
        elif e.get("type") == "user":
            for b in e["message"]["content"]:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    c = b["content"]
                    results[b["tool_use_id"]] = (c if isinstance(c, str) else "".join(x.get("text", "") for x in c), bool(b.get("is_error")))
    turns = [(x["input_tokens"], x["cached_prefix_tokens"], x["output_tokens"]) for x in ev]
    n = len(turns)
    aligned = len(order) == n
    # per-turn items entering context after turn i: assistant text+tool_use args, then that turn's tool results (thinking excluded: echo UNKNOWN)
    entering = []
    out_split = collections.Counter()
    tools = collections.Counter()
    for mid in order[:n]:
        m = msgs[mid]
        h = C("\n".join(m["text"])) + sum(C(nm + " " + canon(a)) for nm, a in m["tools"].values()) + 4
        its = [(HIST, h, None)]
        for tid, (nm, a) in m["tools"].items():
            tools[nm] += 1
            txt, _err = results.get(tid, ("", False))
            if tid in results:
                its.append((classify(nm, a, txt), C(txt) + 4, ("ae", tid)))
        entering.append(its)
        out_split["reasoning"] += sum(C(t) for t in m["think"])
        out_split["visible_text"] += C("\n".join(m["text"]))
        out_split["tool_call_args"] += sum(C(nm + " " + canon(a)) for nm, a in m["tools"].values())
    ctx = []
    for j in range(n):
        items = [it for i in range(j) for it in (entering[i] if i < len(entering) else [])]
        ctx.append([(STATIC, 0, None)] + items)   # static size filled in at accounting time (= turn-1 provider prompt)
    return {"id": os.path.basename(run_dir.rstrip("/\\")), "set": set_name, "turns": turns, "ctx": ctx, "prefix_ok": None, "aligned": aligned,
            "out_split_est": dict(out_split), "tool_calls": dict(tools), "session_ids": sorted(sids), "sidechain_events": sidechain, "has_content": True,
            "aegis": True, "bash_cmds": [a.get("command", "") for m in msgs.values() for nm, a in m["tools"].values() if nm == "Bash"]}


# ---------------------------------------------------------------- accounting
def account(s, wc=W_C, wo=W_O):
    """Per-category billing. Returns dict with token+weighted totals, first-entry vs rebilled, cache breaks, turn costs."""
    T, ctx = s["turns"], s["ctx"]
    cat = collections.defaultdict(lambda: collections.defaultdict(float))     # cat -> {unc, cac, first_unc, first_cac, reb_unc, reb_cac}
    seen_item, turn_w, breaks = set(), [], []
    for j, (p, c, o) in enumerate(T):
        items = list(ctx[j])
        if s.get("aegis"):
            items[0] = (STATIC, T[0][0], None)
            est = sum(t for _, t, _ in items[1:])
            sc = (p - T[0][0]) / est if est and j else 0.0
            sizes = [T[0][0]] + [t * sc for _, t, _ in items[1:]]
            if j == 0:
                sizes = [p]
        else:
            est = sum(t for _, t, _ in items)
            sizes = [t * p / est for _, t, _ in items]
        pos, w_turn = 0.0, 0.0
        shortfall = 0
        exp = T[j - 1][0] if j else 0
        if j and exp - c >= max(BREAK_MIN_TOKENS, BREAK_FRAC * exp):
            shortfall = exp - c
        extra_by = collections.defaultdict(float)
        for (k, _, key), sz in zip(items, sizes):
            cached = max(0.0, min(sz, c - pos))
            unc = sz - cached
            lo, hi = pos, pos + sz                                   # tokens in [c, exp) are the missed-cache span
            miss = max(0.0, min(hi, exp) - max(lo, c)) if shortfall else 0.0
            extra_by[k] += miss * (1 - wc)
            first = key is not None and key not in seen_item
            if key is not None:
                seen_item.add(key)
            d = cat[k]
            d["unc"] += unc
            d["cac"] += cached
            d["break_extra_w"] += miss * (1 - wc)
            tag = "first" if first else "reb"
            if key is not None:
                d[tag + "_unc"] += unc
                d[tag + "_cac"] += cached
            pos += sz
            w_turn += unc + wc * cached
        w_turn += wo * o
        turn_w.append(w_turn)
        if shortfall:
            breaks.append({"turn": j + 1, "shortfall_tokens": shortfall, "extra_weighted": round(sum(extra_by.values()), 1), "by_category": {k: round(v, 1) for k, v in extra_by.items()}})
    P, Cc, Ot = (sum(t[i] for t in T) for i in range(3))
    W = sum(turn_w)
    return {"turns": len(T), "P": P, "C": Cc, "O": Ot, "W": W, "cat": {k: dict(v) for k, v in cat.items()}, "breaks": breaks, "turn_w": turn_w}


def shares(a, wc=W_C, wo=W_O):
    """Everything as fraction of TOTAL tokens (P+O) and of weighted cost W. Re-derives W for the given prices."""
    tot_tok = a["P"] + a["O"]
    W = sum(v["unc"] + wc * v["cac"] for v in a["cat"].values()) + wo * a["O"]
    rows = {}
    for k, v in a["cat"].items():
        tok, w = v["unc"] + v["cac"], v["unc"] + wc * v["cac"]
        row = {"tok_share": tok / tot_tok, "w_share": w / W}
        if k in CATS:
            row.update({"first_tok_share": (v.get("first_unc", 0) + v.get("first_cac", 0)) / tot_tok, "first_w_share": (v.get("first_unc", 0) + wc * v.get("first_cac", 0)) / W,
                        "rebill_tok_share": (v.get("reb_unc", 0) + v.get("reb_cac", 0)) / tot_tok, "rebill_w_share": (v.get("reb_unc", 0) + wc * v.get("reb_cac", 0)) / W,
                        "rebill_cached_tok_share": v.get("reb_cac", 0) / tot_tok, "rebill_uncached_tok_share": v.get("reb_unc", 0) / tot_tok})
        row["break_extra_w_share"] = v["break_extra_w"] / W * ((1 - wc) / (1 - W_C)) if W else 0
        rows[k] = row
    rows["output"] = {"tok_share": a["O"] / tot_tok, "w_share": wo * a["O"] / W}
    brk = sum(b["shortfall_tokens"] for b in a["breaks"]) * (1 - wc)
    turn_mean = W / a["turns"]
    return {"W": W, "total_tokens": tot_tok, "rows": rows, "n_breaks": len(a["breaks"]), "break_w_share": brk / W, "break_shortfall_tokens": sum(b["shortfall_tokens"] for b in a["breaks"]),
            "mean_turn_w_share": turn_mean / W, "mean_turn_tok_share": 1 / a["turns"], "max_turn_w_share": max(a["turn_w"]) / sum(a["turn_w"]), "last_turn_w_share": a["turn_w"][-1] / sum(a["turn_w"])}


def pool(accts, wc=W_C, wo=W_O):
    """Pooled = ratio of sums over sessions (turn-weighted); also min/max/mean of per-session shares."""
    merged = {"turns": sum(a["turns"] for a in accts), "P": sum(a["P"] for a in accts), "C": sum(a["C"] for a in accts), "O": sum(a["O"] for a in accts), "cat": {}, "breaks": [], "turn_w": []}
    for a in accts:
        merged["breaks"] += a["breaks"]
        merged["turn_w"] += a["turn_w"]
        for k, v in a["cat"].items():
            m = merged["cat"].setdefault(k, collections.defaultdict(float))
            for kk, vv in v.items():
                m[kk] += vv
    sh = shares(merged, wc, wo)
    per = [shares(a, wc, wo) for a in accts]
    sh["per_session_w_share"] = {k: {"mean": sum(p["rows"].get(k, {}).get("w_share", 0) for p in per) / len(per), "min": min(p["rows"].get(k, {}).get("w_share", 0) for p in per),
                                     "max": max(p["rows"].get(k, {}).get("w_share", 0) for p in per)} for k in list(merged["cat"]) + ["output"]}
    sh["per_session_mean"] = {"break_w_share": sum(p["break_w_share"] for p in per) / len(per), "mean_turn_w_share": sum(p["mean_turn_w_share"] for p in per) / len(per),
                              "sessions_with_break": sum(1 for p in per if p["n_breaks"]), "turns_mean": merged["turns"] / len(accts)}
    sh["mean_turn_w_share"] = sh["per_session_mean"]["mean_turn_w_share"]      # avg turn as share of ITS OWN session, averaged over sessions
    sh["mean_turn_tok_share"] = sum(1 / a["turns"] for a in accts) / len(accts)
    sh["n_sessions"], sh["n_turns"] = len(accts), merged["turns"]
    sh["_acct"] = {k: merged[k] for k in ("turns", "P", "C", "O")}
    return sh


def lever_table(p):
    """Upper bound = addressable share at 100% removal (no compression rate assumed). Union is non-overlapping (see REPORT)."""
    r = p["rows"]
    handlers = {"test/CI output handler": "tr_test_ci", "JSON/log handler": "tr_json_logs", "diff handler": "tr_diffs", "file-read (outline) handler": "tr_file_reads"}
    out = []
    for name, k in handlers.items():
        x = r.get(k, {"w_share": 0, "tok_share": 0, "first_w_share": 0, "first_tok_share": 0})
        out.append({"lever": name, "tag": "handler", "w_ub": x["w_share"], "tok_ub": x["tok_share"], "w_first_entry": x.get("first_w_share", 0), "w_rebilled": x.get("rebill_w_share", 0)})
    out.append({"lever": "cache-prefix-break avoidance", "tag": "cache discipline", "w_ub": p["break_w_share"], "tok_ub": 0.0, "note": "0 under total-token metric: tokens are billed either way; only price changes"})
    out.append({"lever": "one-turn reduction (avg turn)", "tag": "turn reduction", "w_ub": p["mean_turn_w_share"], "tok_ub": p["mean_turn_tok_share"], "note": "overlaps every other lever"})
    out.append({"lever": "output-token reduction", "tag": "handler/terse output", "w_ub": r["output"]["w_share"], "tok_ub": r["output"]["tok_share"]})
    handler_cats = [v for v in handlers.values()]
    # non-overlapping union: tool-result categories + output + break extra that falls OUTSIDE those categories (static/history)
    union_w = sum(r.get(k, {}).get("w_share", 0) for k in handler_cats) + r["output"]["w_share"]
    outside_break = sum(r[k]["break_extra_w_share"] for k in r if k not in handler_cats and k != "output" and "break_extra_w_share" in r[k])
    union_tok = sum(r.get(k, {}).get("tok_share", 0) for k in handler_cats) + r["output"]["tok_share"]
    return out, {"union_w_ub": union_w + outside_break, "union_w_handlers_output": union_w, "break_extra_outside_handlers": outside_break, "union_tok_ub": union_tok}


# ---------------------------------------------------------------- handoff (multi-agent) measurement
IDENT = re.compile(r"[A-Za-z0-9_./\\:-]{6,}")


def idents(t):
    return {x for x in IDENT.findall(t) if re.search(r"[_./\\:0-9-]", x) or re.search(r"[a-z][A-Z]", x)}


def shingles(t, n=8):
    w = re.findall(r"\S+", t)
    return {" ".join(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def handoff_workflow():
    path = os.path.join(EXP, "workflow_replay", "tokenopt_replay_dataset_v1.json")
    d = json.load(open(path, encoding="utf-8"))
    agents, prev_out_txt = [], ""
    for a in d["agents"]:
        t2 = a["turns"][-1]
        outs = " ".join(json.dumps(t["expected_model_output"], ensure_ascii=False) for t in a["turns"])
        outs_idents = idents(outs)
        msgs = t2["model_input"]
        parts = {}
        for m in msgs:
            if m["role"] in ("system", "user"):
                parts[m["role"]] = parts.get(m["role"], "") + (m["content"] or "")
            elif m["role"] == "tool":
                parts["tool:" + (m.get("name") or "")] = m["content"]
        rows = []
        for nm, txt in parts.items():
            ids = idents(txt)
            lines = [ln for ln in txt.split("\n") if ln.strip()]
            ref_tok = sum(C(ln) for ln in lines if idents(ln) & outs_idents or (shingles(ln, 6) & shingles(outs, 6)))
            rows.append({"part": nm, "tokens_est": C(txt), "ident_count": len(ids), "ident_referenced_in_own_output": round(len(ids & outs_idents) / len(ids), 3) if ids else None,
                         "line_tokens_referenced_frac": round(ref_tok / max(1, sum(C(ln) for ln in lines)), 3),
                         "overlap_with_prev_agent_output_8gram_frac": round(len(shingles(txt) & shingles(prev_out_txt)) / max(1, len(shingles(txt))), 3) if prev_out_txt else None})
        agents.append({"agent": a["agent_name"], "turns": a["turn_count"], "received_tokens_est_last_turn": sum(r["tokens_est"] for r in rows), "parts": rows,
                       "own_output_tokens_est": C(outs)})
        prev_out_txt = outs
    tot_in = sum(C(json.dumps(t["model_input"], ensure_ascii=False)) for a in d["agents"] for t in a["turns"])
    tot_out = sum(C(json.dumps(t["expected_model_output"], ensure_ascii=False)) for a in d["agents"] for t in a["turns"])
    rec = sum(r["tokens_est"] for a in agents for r in a["parts"])
    unref = sum(r["tokens_est"] * (1 - r["line_tokens_referenced_frac"]) for a in agents for r in a["parts"])
    return {"agg": {"est_input_tokens_all_6_turns": tot_in, "est_output_tokens_all_6_turns": tot_out, "est_total_vs_ui_reported": round((tot_in + tot_out) / d["baseline"]["total_tokens"], 3),
                    "received_tokens_last_turn_sum": rec, "unreferenced_line_tokens": round(unref), "unreferenced_frac_of_received": round(unref / rec, 3),
                    "unreferenced_as_share_of_est_total_tokens": round(unref / (tot_in + tot_out), 3)},
            "source": path, "workflow_total_tokens_ui_reported": d["baseline"]["total_tokens"], "limitations": d["source_limitations"], "agents": agents,
            "regime": "reconstructed enterprise (AAVA) 3-agent workflow; ONE workflow; no per-turn provider usage (cost shares UNKNOWN)"}


# ---------------------------------------------------------------- driver
def run():
    sets = collections.OrderedDict()
    sess = []
    for p in sorted(glob.glob(os.path.join(EXP, "agent_benchmark", "traces", "*.jsonl"))):
        sess.append(opencode_session(p))
    for sname in ("baseline_variance", "t1a", "t1b"):
        for rd in sorted(glob.glob(os.path.join(EXP, "cost_model", "results", sname, "runs", "*/"))):
            arm_f = [f for f in glob.glob(os.path.join(rd, "*arm.json"))]
            arm = json.load(open(arm_f[0]))["arm"] if arm_f else "C"
            sess.append(aegis_session(rd, f"{sname}:{arm}"))
    excluded = [s["id"] for s in sess if s.get("aligned") is False]      # stream has more assistant messages than usage events: item order not trustworthy
    for s in sess:
        if s.get("aligned") is not False:
            sets.setdefault(s["set"], []).append(s)
    res = {"prices": {"W_C": W_C, "W_O": W_O}, "break_rule": {"min_tokens": BREAK_MIN_TOKENS, "frac_of_prev_prompt": BREAK_FRAC, "expected_cached": "previous request prompt_tokens"},
           "sets": {}, "sessions": {}, "excluded_unaligned_sessions": excluded}
    for name, ss in sets.items():
        ac = [account(s) for s in ss]
        pl = pool(ac)
        lv, un = lever_table(pl)
        grid = {}
        for c, o in GRID:
            g = pool([account(s, c, o) for s in ss], c, o)
            l2, u2 = lever_table(g)
            grid[f"w_c={c},w_o={o}"] = {"union_w_ub": u2["union_w_ub"], "tool_results_w": sum(g["rows"].get(k, {}).get("w_share", 0) for k in CATS), "output_w": g["rows"]["output"]["w_share"],
                                         "break_w": g["break_w_share"], "turn_w": g["mean_turn_w_share"]}
        pl.pop("_acct")
        r_ = pl["rows"]
        ctx_w = un["union_w_handlers_output"] - r_["output"]["w_share"] + un["break_extra_outside_handlers"]    # handlers + break extra outside them (no output, no turns)
        ctx_tok = un["union_tok_ub"] - r_["output"]["tok_share"]
        decision = {"context_levers_w_ub": ctx_w, "context_levers_tok_ub": ctx_tok, "with_output_w_ub": un["union_w_ub"], "with_output_tok_ub": un["union_tok_ub"],
                    "needed_realization_for_25pct_w_context_only": 0.25 / ctx_w if ctx_w else None, "needed_realization_for_30pct_w_context_only": 0.30 / ctx_w if ctx_w else None,
                    "needed_realization_for_25pct_w_with_output": 0.25 / un["union_w_ub"], "needed_realization_for_25pct_tok_context_only": 0.25 / ctx_tok if ctx_tok else None,
                    "static_prefix_w_share": r_[STATIC]["w_share"], "static_prefix_tok_share": r_[STATIC]["tok_share"]}
        res["sets"][name] = {"n_sessions": len(ss), "pooled": pl, "levers": lv, "union": un, "decision": decision, "grid": grid,
                             "out_split_est_tokens": dict(sum((collections.Counter(s["out_split_est"]) for s in ss), collections.Counter())),
                             "tool_calls": dict(sum((collections.Counter(s["tool_calls"]) for s in ss), collections.Counter())),
                             "sidechain_events": sum(s.get("sidechain_events", 0) for s in ss), "distinct_session_ids_per_run": sorted({len(s["session_ids"]) for s in ss})}
        for s, a in zip(ss, ac):
            sh = shares(a)
            res["sessions"][s["id"]] = {"set": name, "turns": a["turns"], "P": a["P"], "C": a["C"], "O": a["O"], "W": round(a["W"]), "n_breaks": sh["n_breaks"], "breaks": a["breaks"], "break_w_share": round(sh["break_w_share"], 4),
                                        "mean_turn_w_share": round(sh["mean_turn_w_share"], 4), "w_share": {k: round(v["w_share"], 4) for k, v in sh["rows"].items()}, "tok_share": {k: round(v["tok_share"], 4) for k, v in sh["rows"].items()},
                                        "first_w_share": {k: round(v.get("first_w_share", 0), 4) for k, v in sh["rows"].items() if k in CATS}, "rebill_w_share": {k: round(v.get("rebill_w_share", 0), 4) for k, v in sh["rows"].items() if k in CATS}}
    res["handoff_workflow"] = handoff_workflow()
    res["bash_commands"] = collections.Counter(c.split("\n")[0][:80] for s in sess for c in s.get("bash_cmds", [])).most_common(25)
    res["classifier_audit"] = classifier_audit(sess)
    return res


def classifier_audit(sess):
    """Re-read every tool result once; compare final classifier vs content-only; report disagreement by token mass."""
    n_tok = dis_tok = 0
    mat, oc_mat = collections.Counter(), collections.Counter()
    # Aegis results are re-derived from stream files; opencode from trace requests
    for rd in glob.glob(os.path.join(EXP, "cost_model", "results", "*", "runs", "*/")):
        calls, res = {}, {}
        for line in open(os.path.join(rd, "raw", "stream.jsonl"), encoding="utf-8"):
            if not line.startswith("{"):
                continue
            e = json.loads(line)
            if e.get("type") == "assistant":
                for b in e["message"]["content"]:
                    if b["type"] == "tool_use":
                        calls[b["id"]] = (b["name"], b.get("input") or {})
            elif e.get("type") == "user":
                for b in e["message"]["content"]:
                    if isinstance(b, dict) and b.get("type") == "tool_result":
                        c = b["content"]
                        res[b["tool_use_id"]] = c if isinstance(c, str) else "".join(x.get("text", "") for x in c)
        for tid, txt in res.items():
            nm, a = calls.get(tid, ("?", {}))
            f, g = classify(nm, a, txt), content_class(txt)
            t = C(txt)
            n_tok += t
            mat[(f, g)] += t
            dis_tok += t if f != g else 0
    for tf in glob.glob(os.path.join(EXP, "agent_benchmark", "traces", "*.jsonl")):
        rows = [json.loads(line) for line in open(tf, encoding="utf-8") if line.strip()]
        calls = {tc["id"]: (tc["function"]["name"], json.loads(tc["function"]["arguments"])) for r in rows for tc in (r["response"]["message"].get("tool_calls") or [])}
        for m in rows[-1]["request"]["messages"]:
            if m["role"] == "tool" and isinstance(m.get("content"), str):
                nm, a = calls.get(m["tool_call_id"], ("?", {}))
                f, g = classify(nm, a, m["content"]), content_class(m["content"])
                t = C(m["content"])
                oc_mat[(f, g)] += t
    return {"opencode_results_matrix_final_vs_content_tokens": {f"{a}|{b}": v for (a, b), v in sorted(oc_mat.items())}, "aegis_results_token_mass": n_tok, "disagree_token_frac_final_vs_content_only": round(dis_tok / max(1, n_tok), 4), "matrix_final_vs_content_tokens": {f"{a}|{b}": v for (a, b), v in sorted(mat.items())}}


if __name__ == "__main__":
    r = run()
    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    json.dump(r, open(os.path.join(HERE, "results", "census.json"), "w", encoding="utf-8"), indent=1, default=str)
    sys.stdout.reconfigure(encoding="utf-8")
    for n, s in r["sets"].items():
        p = s["pooled"]
        print(n, s["n_sessions"], "sessions", p["n_turns"], "turns; union W UB {:.3f}; breaks {:.3f}; turn {:.3f}; output {:.3f}".format(s["union"]["union_w_ub"], p["break_w_share"], p["mean_turn_w_share"], p["rows"]["output"]["w_share"]))
