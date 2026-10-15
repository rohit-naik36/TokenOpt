"""Post-hoc diagnosis of invalid review-stage outputs in Stage 2 phase A. Diagnostic only; changes no score.

    python stage2_review_diagnose.py

Reads full_s2_outputs.jsonl, full_s2_runs.jsonl and tickets/. Does not read blind_map_s2.json.
An "invalid" review is one that fails the pre-registered review check in score.py (not valid JSON, or a
schema failure). Each invalid review gets the cause of its failure on the span from the first '{' to the last '}'
(after markdown fence removal), using the fixes the diagnosis is testing:
  - trailing comma: parses once trailing commas before } or ] are removed
  - missing closer: parses after the Stage 1 brace repair (tails "}", "]}", "}}", "]}}")
  - extra closer: the bracket stack hits a closer with nothing open, or a mismatched one
  - truncated: stop_reason == max_tokens (none expected; checked, not assumed)
  - other: none of the above parses
  - wrong schema: the span parses as JSON but the review check fails
Flags (fence, prose outside the span) are counted independently because they co-occur.
"""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import score as s1

HERE = Path(__file__).parent
ARMS = ["control", "A", "H", "AH"]
CAUSES = ["truncated", "trailing_comma", "missing_closer", "extra_closer", "other", "wrong_schema"]


def strip_fence(t):
    return re.sub(r"```\s*$", "", re.sub(r"^```(?:json)?\s*", "", t.strip(), flags=re.I))


def span_of(t):
    s = strip_fence(t)
    a, b = s.find("{"), s.rfind("}")
    return s, (a, b)


def bracket_problem(span):
    """String-aware scan of a JSON span. Returns 'extra_closer', 'missing_closer' or None."""
    stack, in_str, esc = [], False, False
    pair = {"}": "{", "]": "["}
    for ch in span:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if not stack or stack[-1] != pair[ch]:
                return "extra_closer"
            stack.pop()
    return "missing_closer" if stack else None


def classify(text, stop_reason):
    s, (a, b) = span_of(text)
    flags = {"fence": "```" in text, "prose_outside": bool(a >= 0 and b >= a and (s[:a].strip() or s[b + 1:].strip()))}
    if a < 0 or b < a:
        return flags, "other", False
    span = s[a:b + 1]
    try:
        json.loads(span)
        ok_span = True
    except json.JSONDecodeError:
        ok_span = False
    if ok_span:
        return flags, None, True
    if stop_reason == "max_tokens":
        return flags, "truncated", False
    try:
        json.loads(re.sub(r",(\s*[}\]])", r"\1", span))
        return flags, "trailing_comma", False
    except json.JSONDecodeError:
        pass
    if s1.parse_json_repaired(text) is not None:
        return flags, bracket_problem(span) or "missing_closer", False
    return flags, "other", False


def upstream_parse(raw):
    """Same parse as the workflow's parseJ: fence strip, first '{' to last '}', then tail repairs."""
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.I)
    s = re.sub(r"```\s*$", "", s)
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < a:
        return None
    body = s[a:b + 1]
    for tail in ["", "]", "] }", "]", " }"]:
        try:
            return json.loads(body + tail)
        except json.JSONDecodeError:
            pass
    return None


def h_review_input(raw, ticket):
    """Rebuild the H-arm review user content (needed('review') in build_workflow_stage2.py)."""
    up = {k: upstream_parse(raw[k]) for k in ("triage", "requirements", "plan")}
    tr, rq, pl = (up[k] or {} for k in ("triage", "requirements", "plan"))
    steps = pl.get("steps") if isinstance(pl.get("steps"), list) else []
    return json.dumps({
        "title": ticket["title"],
        "acceptance_criteria": rq.get("acceptance_criteria"),
        "plan_steps": [{"description": x.get("description"), "files": x.get("files")} for x in steps],
        "diff": ticket["diff"],
    }, indent=2), {k: up[k] is not None for k in up}


def main():
    outs = {}
    for o in (json.loads(l) for l in (HERE / "full_s2_outputs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()):
        outs[(o["run_id"], o["stage"])] = o["output"]
    rows = [json.loads(l) for l in (HERE / "full_s2_runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    calls = {(r["run_id"], r["stage"]): r for r in rows if r["kind"] == "call"}
    runs = [r for r in rows if r["kind"] == "run"]
    gt = json.loads((HERE / "tickets" / "ground_truth.json").read_text(encoding="utf-8"))["tickets"]

    per = []
    for r in runs:
        rid = r["run_id"]
        text = outs[(rid, "review")]
        stop = calls[(rid, "review")]["stop_reason"]
        flags, span_cause, span_ok = classify(text, stop)
        schema_fail = s1.check_stage("review", s1.parse_json(text))
        invalid = bool(schema_fail) or stop == "max_tokens"
        if not invalid:
            cause_out = None
        elif span_ok and not schema_fail:
            cause_out = None  # cannot happen: a span that parses with no schema failure is valid
        elif not span_ok:
            cause_out = span_cause
        else:
            cause_out = "wrong_schema"
        raw_strict = False
        try:
            json.loads(text)
            raw_strict = True
        except json.JSONDecodeError:
            pass
        fence_strip_ok = s1.parse_json(text) is not None
        repaired_ok = s1.parse_json_repaired(text) is not None
        per.append(dict(run_id=rid, arm=r["arm"], ticket=r["ticket"], rep=r["rep"], invalid=invalid, cause=cause_out,
                        flags=flags, raw_strict=raw_strict, fence_strip_ok=fence_strip_ok, repaired_ok=repaired_ok,
                        repaired_schema_ok=repaired_ok and not s1.check_stage("review", s1.parse_json_repaired(text)),
                        stop=stop, text_len=len(text)))

    print("## Invalid review outputs: cause by arm (primary cause, mutually exclusive)\n")
    print("| arm | reviews | invalid | " + " | ".join(CAUSES) + " |")
    print("|---|---|---|" + "---|" * len(CAUSES))
    for a in ARMS:
        g = [p for p in per if p["arm"] == a]
        inv = [p for p in g if p["invalid"]]
        c = Counter(p["cause"] for p in inv)
        print(f"| {a} | {len(g)} | {len(inv)} | " + " | ".join(str(c.get(k, 0)) for k in CAUSES) + " |")
    tot = [p for p in per if p["invalid"]]
    print(f"| all | {len(per)} | {len(tot)} | " + " | ".join(str(Counter(p['cause'] for p in tot).get(k, 0)) for k in CAUSES) + " |")

    print("\n## Co-occurring flags among all 160 reviews (not mutually exclusive)\n")
    print("| arm | fence present | prose outside span | invalid with fence | invalid with prose |")
    print("|---|---|---|---|---|")
    for a in ARMS:
        g = [p for p in per if p["arm"] == a]
        print(f"| {a} | {sum(p['flags']['fence'] for p in g)} | {sum(p['flags']['prose_outside'] for p in g)} | "
              f"{sum(p['flags']['fence'] for p in g if p['invalid'])} | {sum(p['flags']['prose_outside'] for p in g if p['invalid'])} |")

    print("\n## Diagnostic parse tests on invalid reviews (what would parse)\n")
    print("| arm | invalid | strict parse on raw text | parses after fence strip | parses after Stage 1 brace repair | repaired and schema-valid |")
    print("|---|---|---|---|---|---|")
    for a in ARMS:
        inv = [p for p in per if p["arm"] == a and p["invalid"]]
        print(f"| {a} | {len(inv)} | {sum(p['raw_strict'] for p in inv)} | {sum(p['fence_strip_ok'] for p in inv)} | "
              f"{sum(p['repaired_ok'] for p in inv)} | {sum(p['repaired_schema_ok'] for p in inv)} |")

    # H-arm handoff inputs
    print("\n## Arm H: review-stage input vs review validity\n")
    h_runs = [r for r in runs if r["arm"] == "H"]
    rows_h = []
    for r in h_runs:
        rid = r["run_id"]
        t = json.loads((HERE / "tickets" / f"{r['ticket']}.json").read_text(encoding="utf-8"))
        raw = {k: outs[(rid, k)] for k in ("triage", "requirements", "plan")}
        inp, parsed = h_review_input(raw, t)
        p = next(x for x in per if x["run_id"] == rid)
        rows_h.append(dict(run_id=rid, input=inp, invalid=p["invalid"], cause=p["cause"], upstream_ok=parsed, text=outs[(rid, "review")]))
    grp = defaultdict(lambda: [0, 0])
    for x in rows_h:
        key = "all upstream parsed" if all(x["upstream_ok"].values()) else "an upstream stage did not parse"
        grp[key][0] += x["invalid"]; grp[key][1] += 1
    for k, (i, n) in grp.items():
        print(f"- H review invalid when {k}: {i}/{n}")
    cg = defaultdict(lambda: [0, 0])
    for p in per:
        if p["arm"] == "control":
            cg["control, all reviews"][0] += p["invalid"]; cg["control, all reviews"][1] += 1
    for k, (i, n) in cg.items():
        print(f"- {k}: invalid {i}/{n}")
    print("- Upstream-parse effect on H (plan stage parse failure -> empty plan_steps):")
    for flag in (True, False):
        g = [x for x in rows_h if x["upstream_ok"]["plan"] == flag]
        if g:
            print(f"    plan parsed={flag}: invalid {sum(x['invalid'] for x in g)}/{len(g)}")

    import sys
    if "--show" in sys.argv:
        inv = [x for x in rows_h if x["invalid"]][:3]
        val = [x for x in rows_h if not x["invalid"]][:3]
        for label, group in (("INVALID", inv), ("VALID", val)):
            for x in group:
                print(f"\n### {label} {x['run_id']} (cause: {x['cause']})")
                print("review-stage input (first 300 chars):")
                print(x["input"][:300].replace("\n", "\\n"))
                print("review output (first 300 chars):")
                print(x["text"][:300].replace("\n", "\\n"))


if __name__ == "__main__":
    main()
