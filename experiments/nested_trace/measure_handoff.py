"""Handoff-bloat measurement over agent-trace/v1 JSONL rows (nested_trace extension).

Matching rule (ESTIMATE, not exact): a payload unit (non-blank line) is "used" if
>= THRESH of its distinctive tokens appear in the receiver's assistant outputs
(content + tool-call args). Distinctive = identifier-like word (3+ chars) or 2+-digit
number, lowercased, minus stop-words/Python keywords, minus tokens in the receiver's
system prompt and task instructions. Units with no distinctive token are "neutral" and
are counted in neither used nor unused (conservative: lowers the bloat figure).
Known error: over-counts use for common identifiers; under-counts paraphrase.
Sensitivity is reported at thresholds 0.25 / 0.5 / 1.0.
"""
import json, re, glob
from pathlib import Path
import tiktoken

ENC = tiktoken.get_encoding("o200k_base")
TOK = re.compile(r"[A-Za-z_]\w{2,}|\d{2,}")
STOP = set("""the and for that this with from are was were has have had not but you your can will would should could
into than then them they their there here what when where which who whom how why also any all each other such only
more most some use used using via per its else elif try except finally def class return import pass none true false
self cls lambda yield raise assert while break continue global nonlocal del test tests file files line
""".split())
THRESHOLDS = (0.25, 0.5, 1.0)


def ntok(s):
    return len(ENC.encode(s or ""))


def toks(s):
    return {t.lower() for t in TOK.findall(s or "")} - STOP


def extract_payload(messages, hid):
    pat = re.compile(r"<<<HANDOFF id=%s [^>]*>>>\n(.*?)\n<<<END HANDOFF %s>>>" % (re.escape(hid), re.escape(hid)), re.S)
    for m in messages:
        c = m.get("content") or ""
        mm = pat.search(c)
        if mm:
            return mm.group(1), pat.sub("", c)
    return "", ""


def outputs_text(rows):
    out = []
    for r in rows:
        msg = (r.get("response") or {}).get("message") or {}
        out.append(msg.get("content") or "")
        for tc in msg.get("tool_calls") or []:
            out.append(json.dumps(tc.get("function", {}).get("arguments", {})))
    return "\n".join(out)


def split_units(payload):
    return [l for l in payload.split("\n") if l.strip()]


def classify(payload, exclude_text, out_text, thresh=0.5):
    """Return o200k token counts of used/unused/neutral units."""
    ex, outs = toks(exclude_text), toks(out_text)
    res = {"used": 0, "unused": 0, "neutral": 0, "units": 0}
    for u in split_units(payload):
        d = toks(u) - ex
        n = ntok(u)
        res["units"] += 1
        if not d:
            res["neutral"] += n
        elif len(d & outs) / len(d) >= thresh:
            res["used"] += n
        else:
            res["unused"] += n
    return res


def load(paths):
    rows = []
    for p in paths:
        rows += [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def usage(r):
    u = (r.get("response") or {}).get("usage") or {}
    return u.get("prompt_tokens") or 0, u.get("completion_tokens") or 0


def est_prompt(r):
    return (r.get("estimates") or {}).get("prompt_tokens_o200k") or 0


def wcost(p, o):  # uncached prompt = 1 (cached UNKNOWN), output = 4
    return p + 4 * o


def analyze(rows):
    rows = [r for r in rows if r.get("response")]
    handoffs = []
    for r in rows:
        h = r.get("handoff")
        if not h:
            continue
        same = [x for x in rows if x["workflow_id"] == r["workflow_id"] and x["agent"] == r["agent"] and x["seq"] >= r["seq"]]
        payload, rest = extract_payload(r["request"]["messages"], h["id"])
        sysmsg = " ".join(m.get("content") or "" for m in r["request"]["messages"] if m["role"] == "system")
        excl = sysmsg + "\n" + rest
        outs = outputs_text(same)
        rec = {"task": r.get("task", "?"), "workflow_id": r["workflow_id"], "agent": r["agent"], "from": h["from"],
               "kind": h.get("kind", "forward"), "turns_billed": len(same), "payload_tokens": ntok(payload)}
        for t in THRESHOLDS:
            rec["t%.2f" % t] = classify(payload, excl, outs, t)
        handoffs.append(rec)
    return handoffs


def shares(rows, handoffs, thr="t0.50"):
    P = sum(usage(r)[0] for r in rows)
    O = sum(usage(r)[1] for r in rows)
    EP = sum(est_prompt(r) for r in rows)
    gross = sum(h["payload_tokens"] * h["turns_billed"] for h in handoffs)
    unused = sum(h[thr]["unused"] * h["turns_billed"] for h in handoffs)
    used = sum(h[thr]["used"] * h["turns_billed"] for h in handoffs)
    neutral = sum(h[thr]["neutral"] * h["turns_billed"] for h in handoffs)
    f = lambda a, b: round(a / b, 4) if b else None
    return {
        "n_calls": len(rows), "n_handoffs": len(handoffs),
        "provider_prompt_tokens": P, "provider_output_tokens": O, "provider_total_tokens": P + O,
        "est_full_prompt_tokens_o200k": EP,
        "unused_rebilled_tokens_est": unused, "used_rebilled_tokens_est": used, "neutral_rebilled_tokens_est": neutral,
        "gross_payload_rebilled_tokens_est": gross,
        "bloat_share_tokens_provider_denominator": f(unused, P + O),
        "bloat_share_tokens_estfull_denominator": f(unused, EP + O),
        "gross_share_tokens_provider_denominator": f(gross, P + O),
        "gross_share_tokens_estfull_denominator": f(gross, EP + O),
        "weighted_cost_provider": wcost(P, O), "weighted_cost_estfull": wcost(EP, O),
        "bloat_share_cost_provider_denominator": f(unused, wcost(P, O)),
        "bloat_share_cost_estfull_denominator": f(unused, wcost(EP, O)),
        "gross_share_cost_provider_denominator": f(gross, wcost(P, O)),
        "gross_share_cost_estfull_denominator": f(gross, wcost(EP, O)),
    }


def turns_per_agent(rows):
    d = {}
    for r in rows:
        d.setdefault(r["agent"], {}).setdefault(r["task"], 0)
        d[r["agent"]][r["task"]] += 1
    return d


def main(trace_glob, out):
    paths = sorted(glob.glob(trace_glob))
    rows = [r for r in load(paths) if r.get("response")]
    handoffs = analyze(rows)
    res = {"note": "ESTIMATES: used/unused is a lexical matching heuristic; payload token counts are o200k, not the served model's tokenizer. Provider usage (Ollama prompt_eval_count/eval_count) is truth for totals but cached tokens are UNKNOWN. NOT a quality comparison.",
           "traces": paths, "pooled": {}, "per_task": {}, "turns_per_agent": turns_per_agent(rows), "handoffs": handoffs}
    for thr in ("t0.25", "t0.50", "t1.00"):
        res["pooled"][thr] = shares(rows, handoffs, thr)
    for task in sorted({r["task"] for r in rows}):
        tr = [r for r in rows if r["task"] == task]
        th = [h for h in handoffs if h["task"] == task]
        res["per_task"][task] = {thr: shares(tr, th, thr) for thr in ("t0.25", "t0.50", "t1.00")}
    Path(out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res["pooled"]["t0.50"], indent=2))


if __name__ == "__main__":
    here = Path(__file__).parent
    main(str(here / "traces" / "*.jsonl"), str(here / "results" / "handoff.json"))
