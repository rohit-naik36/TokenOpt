"""Naive nested multi-agent workflow on local Ollama; records agent-trace/v1 rows (+ workflow fields + handoff).

Orchestrator = deterministic harness code (0 model calls). Agents: A (tools) -> B (plan, nested B1 -> B2, finish) -> C (report).
Naive handoff: next agent's first prompt = previous agent's FULL final message + all tool results it gathered.
No compression anywhere. Run: python run_workflow.py [task_id ...]
"""
import json, os, re, shutil, subprocess, sys, time, uuid, datetime
from pathlib import Path
import requests
from measure_handoff import ntok, extract_payload, classify, outputs_text

HERE = Path(__file__).parent
REPO = HERE.parent.parent
SCRATCH = Path(os.environ.get("NT_SCRATCH", HERE / "_ws"))
URL, MODEL = "http://localhost:11434/api/chat", "qwen3.5:9b"
OPTS = {"num_ctx": 8192, "temperature": 0, "seed": 7, "num_predict": 700}
MAX_CALLS, MAX_SECONDS, TOOL_CAP = 80, 90 * 60, 2000
T0 = time.time()
STATE = {"calls": 0, "fails": 0, "hid": 0, "seq": 0}


class Stop(Exception):
    pass


# ---------------- workspace + tools ----------------
def make_ws(name):
    ws = SCRATCH / name
    if ws.exists():
        shutil.rmtree(ws)
    ig = shutil.ignore_patterns(".venv", ".git", "experiments", "__pycache__", "*.pyc", ".pytest_cache")
    ws.mkdir(parents=True)
    for d in ("tokenopt", "tests"):
        shutil.copytree(REPO / d, ws / d, ignore=ig)
    shutil.copy(REPO / "pyproject.toml", ws / "pyproject.toml")
    return ws


def safe(ws, p):
    q = (ws / p).resolve()
    if ws.resolve() not in q.parents and q != ws.resolve():
        raise ValueError("path outside workspace")
    return q


def scrub(s):
    """Replace local absolute paths in tool output so traces stay portable."""
    for q in (SCRATCH.resolve(), REPO.resolve(), Path.home()):
        s = s.replace(str(q), "<path>").replace(q.as_posix(), "<path>")
    return s


def cap(s):
    s = scrub(s)
    return s if len(s) <= TOOL_CAP else s[:TOOL_CAP] + "\n...[truncated %d chars]" % (len(s) - TOOL_CAP)


def run_tool(ws, name, a):
    try:
        if name == "read_file":
            return cap(safe(ws, a["path"]).read_text(encoding="utf-8", errors="replace"))
        if name == "list_dir":
            return cap("\n".join(sorted(x.name + ("/" if x.is_dir() else "") for x in safe(ws, a.get("path", ".")).iterdir() if x.name != "__pycache__")))
        if name == "grep":
            import re as _re
            rx, base, out = _re.compile(a["pattern"]), safe(ws, a.get("path", ".")), []
            for f in ([base] if base.is_file() else sorted(base.rglob("*.py"))):
                for i, l in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(l):
                        out.append("%s:%d:%s" % (f.relative_to(ws).as_posix(), i, l.strip()))
            return cap("\n".join(out[:40]) or "(no matches)")
        if name == "run_pytest":
            env = dict(os.environ, PYTHONPATH=str(ws))
            r = subprocess.run([sys.executable, "-m", "pytest", a["test_file"], "-q", "--no-cov", "-p", "no:cacheprovider", "--tb=short"],
                               cwd=ws, capture_output=True, text=True, timeout=180, env=env)
            return cap((r.stdout + r.stderr)[-TOOL_CAP:])
        if name == "write_file":
            p = safe(ws, a["path"])
            if "tests" not in p.relative_to(ws.resolve()).parts[:1]:
                return "error: write_file only allowed under tests/"
            p.write_text(a["content"], encoding="utf-8")
            return "wrote %s (%d chars)" % (a["path"], len(a["content"]))
        return "error: unknown tool " + name
    except Exception as e:
        return "error: %s: %s" % (type(e).__name__, e)


def tdef(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {"type": "object", "properties": {k: {"type": "string"} for k in props}, "required": req}}}


TOOLS = {
    "read_file": tdef("read_file", "Read a text file (path relative to repo root).", ["path"], ["path"]),
    "list_dir": tdef("list_dir", "List a directory.", ["path"], ["path"]),
    "grep": tdef("grep", "Regex search in .py files under path.", ["pattern", "path"], ["pattern"]),
    "run_pytest": tdef("run_pytest", "Run pytest on one test file.", ["test_file"], ["test_file"]),
    "write_file": tdef("write_file", "Write a file under tests/ (path, content).", ["path", "content"], ["path", "content"]),
}


# ---------------- model call + trace ----------------
def chat(row_ctx, messages, tools):
    if STATE["calls"] >= MAX_CALLS or time.time() - T0 > MAX_SECONDS:
        raise Stop("cap reached: calls=%d elapsed=%.0fs" % (STATE["calls"], time.time() - T0))
    body = {"model": MODEL, "messages": messages, "stream": False, "think": False, "options": OPTS}
    if tools:
        body["tools"] = tools
    err, resp, t = None, None, time.time()
    for attempt in (1, 2):  # retry once; two failures -> Stop
        if STATE["calls"] >= MAX_CALLS:
            raise Stop("call cap")
        STATE["calls"] += 1
        t = time.time()
        try:
            r = requests.post(URL, json=body, timeout=600)
            r.raise_for_status()
            resp = r.json()
            err = None
            break
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, e)
            STATE["fails"] += 1
            print("  call failed (attempt %d): %s" % (attempt, err), flush=True)
            time.sleep(5)
    STATE["seq"] += 1
    est = ntok(json.dumps(messages, ensure_ascii=False)) + (ntok(json.dumps(tools)) if tools else 0)
    msg = (resp or {}).get("message")
    row = {
        "trace_version": "agent-trace/v1", "session_id": row_ctx["session"], "turn_id": str(uuid.uuid4()), "seq": STATE["seq"],
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "capture": {"mechanism": "harness-direct", "request_modified": [], "redacted": False, "exact_replay": True},
        "provider": {"kind": "ollama-native", "upstream_host": "localhost:11434", "endpoint": "/api/chat"},
        "request": {"model": MODEL, "messages": messages, "tools": tools or None, "stream": False, "options": OPTS, "think": False},
        "response": None if not resp else {
            "http_status": 200, "stream": False, "id": None, "model": resp.get("model"),
            "message": msg, "finish_reason": resp.get("done_reason"),
            "usage": {"prompt_tokens": resp.get("prompt_eval_count"), "completion_tokens": resp.get("eval_count"),
                      "total_tokens": (resp.get("prompt_eval_count") or 0) + (resp.get("eval_count") or 0),
                      "prompt_tokens_details": {"cached_tokens": "UNKNOWN"}},
            "ollama_durations_ns": {k: resp.get(k) for k in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}},
        "timing": {"latency_ms": round((time.time() - t) * 1000, 1), "ttfb_ms": None},
        "error": err,
        "estimates": {"prompt_tokens_o200k": est, "note": "ESTIMATE of full prompt incl. tool schemas, o200k, no chat-template overhead"},
        "task": row_ctx["task"], "workflow_id": row_ctx["wf"], "parent_workflow_id": row_ctx.get("parent"),
        "agent": row_ctx["agent"], "step": row_ctx["step"],
    }
    if row_ctx.get("handoff"):
        row["handoff"] = row_ctx.pop("handoff")
    row_ctx["rows"].append(row)
    if not resp:
        raise Stop("Ollama failed twice: " + str(err))
    return resp["message"]


def handoff_block(src, kind, body):
    STATE["hid"] += 1
    hid = "h%d" % STATE["hid"]
    return hid, "<<<HANDOFF id=%s from=%s>>>\n%s\n<<<END HANDOFF %s>>>" % (hid, src, body, hid)


def run_agent(ctx, wf, parent, agent, system, task_text, tools, max_turns, ws, handoff=None):
    """handoff = (src, kind, payload_body) put in first user prompt. Returns dict(final, tool_log, turns)."""
    rc = dict(session=ctx["session"], task=ctx["task"], wf=wf, parent=parent, agent=agent, step=0, rows=ctx["rows"])
    user = task_text
    if handoff:
        hid, blk = handoff_block(*handoff)
        user = task_text + "\n\nContext from previous agent:\n" + blk
        rc["handoff"] = {"from": handoff[0], "kind": handoff[1], "id": hid, "payload_tokens": ntok(handoff[2]), "used_tokens": None}
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    log, final = [], ""
    for turn in range(1, max_turns + 1):
        rc["step"] = turn
        last = turn == max_turns
        m = chat(rc, msgs, None if last or not tools else [TOOLS[t] for t in tools])
        msgs.append({k: v for k, v in m.items() if k in ("role", "content", "tool_calls")})
        calls = m.get("tool_calls") or []
        if not calls or last:
            final = m.get("content") or ""
            break
        for c in calls:
            n, a = c["function"]["name"], c["function"].get("arguments") or {}
            out = run_tool(ws, n, a) if n in (tools or []) else "error: tool not available"
            log.append((n, a, out))
            msgs.append({"role": "tool", "tool_name": n, "content": out})
    return {"final": final or "(empty)", "tool_log": log, "turns": turn, "msgs": msgs, "rc": rc}


def tool_payload(log):
    return "\n".join("### tool %s %s\n%s" % (n, json.dumps(a), o) for n, a, o in log)


def full_payload(res, label):
    return "## %s final message\n%s\n## %s tool results\n%s" % (label, res["final"], label, tool_payload(res["tool_log"]) or "(none)")


# ---------------- workflow ----------------
SYS = {
    "A": "You are Agent A, a context gatherer for a Python repo. Use the tools (few calls) to collect facts needed for the task. When done, reply with a concise findings summary.",
    "B": "You are Agent B, planner/implementer. Using the context given, write a short numbered plan for the task.",
    "B1": "You are Agent B1. Write or adjust the requested unit test file using write_file (path under tests/). Then reply with one short line.",
    "B2": "You are Agent B2. Run the named test file with run_pytest, then report pass/fail and the key output lines.",
    "C": "You are Agent C, verifier. From the context given, write a short final report: what was done, test outcome, caveats.",
}
TASKS = {
    "t1": dict(task="Explain why the test `test_ttl_expiry_removes_entry` in tests/test_cache.py passes and summarize what the cache tests cover.",
               b1="Write a small probe test file tests/test_probe_t1.py that checks the TTL expiry behaviour described in the plan.", test="tests/test_probe_t1.py"),
    "t2": dict(task="tokenopt/utils/messages.py has a helper `get_user_query` with no unit tests. Add a small unit test for it.",
               b1="Write tests/test_messages_util.py with 3-4 small tests of get_user_query (last user message, no user message, non-string content).", test="tests/test_messages_util.py"),
    "t3": dict(task="The test tests/test_injected_failure.py is failing. Triage: find out why it fails and whether the test or the code is wrong.",
               b1="Rewrite tests/test_injected_failure.py so the expectation matches the real behaviour of the helper (as determined in the plan).", test="tests/test_injected_failure.py"),
}
INJECT = '''from tokenopt.utils.token_counter import truncate_to_tokens


def test_truncate_keeps_two_tokens():
    assert truncate_to_tokens("alpha beta gamma delta", 2) == "alpha beta gamma"
'''


def run_task(tid):
    T = TASKS[tid]
    ws = make_ws(tid)
    if tid == "t3":
        (ws / "tests" / "test_injected_failure.py").write_text(INJECT)
    ctx = dict(session="session-%s" % tid, task=tid, rows=[])
    out_path = HERE / "traces" / ("%s.jsonl" % tid)
    info = {}
    try:
        A = run_agent(ctx, tid, None, "A", SYS["A"], "TASK: " + T["task"], ["read_file", "grep", "list_dir", "run_pytest"], 5, ws)
        pa = full_payload(A, "A")
        # B turn 1 (plan, no tools)
        B = run_agent(ctx, tid, None, "B", SYS["B"], "TASK: " + T["task"] + "\nProduce the plan.", [], 1, ws, handoff=("A", "forward", pa))
        # nested sub-workflow launched by B: B1 -> B2 (naive: B1 gets B's plan plus the whole payload B received)
        sub = tid + ".B-sub"
        B1 = run_agent(ctx, sub, tid, "B1", SYS["B1"], "SUBTASK: " + T["b1"], ["read_file", "write_file"], 4, ws,
                       handoff=("B", "forward", "## B plan\n" + B["final"] + "\n## context B received\n" + pa))
        B2 = run_agent(ctx, sub, tid, "B2", SYS["B2"], "Run %s and report." % T["test"], ["run_pytest"], 3, ws,
                       handoff=("B1", "forward", full_payload(B1, "B1")))
        # B continuation: naive = full nested result appended to B's conversation (returned handoff)
        rc = B["rc"]
        hid, blk = handoff_block("B2", "return", full_payload(B2, "B2"))
        msgs = B["msgs"] + [{"role": "user", "content": "Sub-workflow finished. Result:\n" + blk + "\nNow write your final implementation summary."}]
        rc.update(step=2, handoff={"from": "B2", "kind": "return", "id": hid, "payload_tokens": ntok(full_payload(B2, "B2")), "used_tokens": None})
        m = chat(rc, msgs, None)
        Bfinal = m.get("content") or "(empty)"
        pb = "## B final message\n%s\n## B sub-workflow results\n%s\n%s" % (Bfinal, full_payload(B1, "B1"), full_payload(B2, "B2"))
        C = run_agent(ctx, tid, None, "C", SYS["C"], "TASK: " + T["task"] + "\nVerify and report.", [], 1, ws, handoff=("B", "forward", pb))
        info = {"finals": {"A": A["final"][:300], "B": Bfinal[:300], "B1": B1["final"][:200], "B2": B2["final"][:300], "C": C["final"][:400]},
                "turns": {"A": A["turns"], "B": 2, "B1": B1["turns"], "B2": B2["turns"], "C": 1}}
        status = "ok"
    except Stop as e:
        status = "STOPPED: %s" % e
    # fill handoff.used_tokens (t=0.5 estimate) and write
    for r in ctx["rows"]:
        h = r.get("handoff")
        if h and r.get("response"):
            same = [x for x in ctx["rows"] if x["workflow_id"] == r["workflow_id"] and x["agent"] == r["agent"] and x["seq"] >= r["seq"] and x.get("response")]
            payload, rest = extract_payload(r["request"]["messages"], h["id"])
            sysm = " ".join(m["content"] or "" for m in r["request"]["messages"] if m["role"] == "system")
            h["used_tokens"] = classify(payload, sysm + "\n" + rest, outputs_text(same), 0.5)["used"]
            h["used_tokens_note"] = "ESTIMATE: lexical match, threshold 0.5, see measure_handoff.py"
    out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in ctx["rows"]) + "\n", encoding="utf-8")
    print("%s: %s | rows=%d | calls so far=%d | %.1f min" % (tid, status, len(ctx["rows"]), STATE["calls"], (time.time() - T0) / 60), flush=True)
    (HERE / "results" / ("run_%s.json" % tid)).write_text(json.dumps({"status": status, **info}, indent=2))
    return status


if __name__ == "__main__":
    print("BUDGET: <=%d model calls (retries count), <=%d min wall, local Ollama %s only, $0; orchestrator = harness code (0 calls)" % (MAX_CALLS, MAX_SECONDS // 60, MODEL), flush=True)
    for tid in (sys.argv[1:] or list(TASKS)):
        if not run_task(tid).startswith("ok"):
            break
