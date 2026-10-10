import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from measure_handoff import classify, extract_payload, analyze, shares


def test_classify_used_unused_neutral():
    payload = "alpha_func in tokenopt/cache.py\nunrelated_zebra_thing 98765\n}"
    r = classify(payload, "", "I looked at alpha_func and cache", 0.5)
    assert r["used"] > 0 and r["unused"] > 0 and r["neutral"] > 0 and r["units"] == 3


def test_exclusion_of_prompt_tokens():
    r = classify("alpha_func here", "alpha_func here", "", 0.5)
    assert r["used"] == 0 and r["unused"] == 0 and r["neutral"] > 0


def _row(seq, agent, msgs, out, handoff=None, p=100, o=10):
    r = {"workflow_id": "w", "agent": agent, "seq": seq, "task": "t", "request": {"messages": msgs},
         "response": {"message": {"content": out}, "usage": {"prompt_tokens": p, "completion_tokens": o}},
         "estimates": {"prompt_tokens_o200k": p}}
    if handoff:
        r["handoff"] = handoff
    return r


def test_analyze_rebilling():
    body = "<<<HANDOFF id=h1 from=A>>>\nused_ident_xyz line\nnever_mentioned_qqq 4242\n<<<END HANDOFF h1>>>"
    msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task " + body}]
    rows = [_row(1, "B", msgs, "calls used_ident_xyz", {"from": "A", "id": "h1"}), _row(2, "B", msgs, "done")]
    h = analyze(rows)
    assert len(h) == 1 and h[0]["turns_billed"] == 2
    assert h[0]["t0.50"]["unused"] > 0 and h[0]["t0.50"]["used"] > 0
    s = shares(rows, h)
    assert s["unused_rebilled_tokens_est"] == 2 * h[0]["t0.50"]["unused"]
    assert s["provider_total_tokens"] == 220
    assert 0 < s["bloat_share_tokens_provider_denominator"] < s["gross_share_tokens_provider_denominator"] < 1


def test_extract():
    p, rest = extract_payload([{"content": "x <<<HANDOFF id=h9 from=A>>>\nbody\n<<<END HANDOFF h9>>> y"}], "h9")
    assert p == "body" and "body" not in rest


def test_no_absolute_paths_in_output(tmp_path):
    import json, re
    import measure_handoff
    from pathlib import Path
    repo = Path(measure_handoff.__file__).resolve().parent.parent.parent
    tr = tmp_path / "t.jsonl"
    tr.write_text(json.dumps(_row(1, "A", [{"role": "user", "content": "x"}], "alpha_func")) + chr(10), encoding="utf-8")
    out = tmp_path / "o.json"
    measure_handoff.main(str(tr), str(out))
    txt = out.read_text(encoding="utf-8")
    assert not re.search(r"[A-Za-z]:[\\/]", txt) and str(tmp_path) not in txt
    import run_workflow
    assert str(repo) not in run_workflow.scrub("error in " + str(repo) + "/tokenopt/x.py")
