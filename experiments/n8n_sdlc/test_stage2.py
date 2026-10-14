"""Offline checks for Stage 2: cost arithmetic, runner retry/budget/resume logic, workflow key handling.

    python -m pytest experiments/n8n_sdlc/test_stage2.py -q      (or run this file directly)

No test here reaches the network: the webhook is replaced by a fake post function.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import stage2_cost as cost  # noqa: E402
import stage2_runner as runner  # noqa: E402

# Offline dummy for the runner's presence check. Not the real secret; no request leaves this process.
os.environ["BENCH_WEBHOOK_TOKEN"] = "offline-test-token"

PRICES = {
    "claude-haiku-5-5": {"input": 0.10, "output": 0.50, "cache_write_5m": "TODO", "cache_read": "TODO"},
}
REAL_PRICES = cost.load_prices()
USAGE = {"input_tokens": 1000, "output_tokens": 500, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}


def test_dollars_input_output_only():
    # 1000 * 0.10/1e6 + 500 * 0.50/1e6 = 0.00035
    assert abs(cost.dollars(USAGE, PRICES, "claude-haiku-5-5") - 0.00035) < 1e-12


def test_dollars_unknown_when_cache_unpriced():
    u = dict(USAGE, cache_read_input_tokens=10)
    assert cost.unpriced_units(PRICES, "claude-haiku-5-5", u) == ["cache_read"]
    assert cost.dollars(u, PRICES, "claude-haiku-5-5") is None


def test_over_100k_is_refused_not_priced_at_base_rate():
    # Base tier applies up to and including 100,000 input tokens (input + cache writes + cache reads).
    at_limit = dict(USAGE, input_tokens=99_000, cache_read_input_tokens=1_000)
    assert cost.dollars(at_limit, REAL_PRICES, "claude-haiku-5-5") is not None
    over = dict(USAGE, input_tokens=99_000, cache_read_input_tokens=1_001)
    try:
        cost.dollars(over, REAL_PRICES, "claude-haiku-5-5")
        raise AssertionError("expected ValueError above 100k input tokens")
    except ValueError as e:
        assert "100000" in str(e)


def test_runner_stops_on_over_100k_request():
    d, out, outputs = _workdir()
    try:
        big = _ok_stage(0)
        big["usage_raw"] = dict(USAGE, input_tokens=150_000)
        response = {"stages": {s: dict(big) for s in runner.STAGES}}
        calls = []

        def fake(url, body, timeout):
            calls.append(1)
            return 200, response, {}

        try:
            runner.main(["--tickets", "T01", "--arms", "control", "--cap", "5", "--sleep-scale", "0",
                         "--out", str(out), "--outputs", str(outputs)], post_fn=fake)
            raise AssertionError("expected the runner to stop")
        except SystemExit as e:
            assert "base-tier" in str(e)
        assert len(calls) == 1
        first_call = [r for r in _rows(out) if r["kind"] == "call"][0]
        assert first_call["cost_usd"] is None and "base-tier" in first_call["error"]
    finally:
        shutil.rmtree(d)


def test_webhook_401_stops_without_retry_or_billing():
    d, out, outputs = _workdir()
    try:
        calls = []

        def fake(url, body, timeout):
            calls.append(1)
            return 401, {"message": "unauthorized"}, {}

        try:
            runner.main(["--tickets", "T01", "--arms", "control", "--cap", "5", "--sleep-scale", "0",
                         "--out", str(out), "--outputs", str(outputs)], post_fn=fake)
            raise AssertionError("expected SystemExit on 401")
        except SystemExit as e:
            assert "401" in str(e)
        assert len(calls) == 1  # no retry
        rows = _rows(out)
        assert [r["kind"] for r in rows] == ["attempt_error"] and rows[0]["http_status"] == 401
        assert rows[0]["usage_known"] is False
    finally:
        shutil.rmtree(d)


def test_post_sends_token_header_from_env():
    seen = {}

    class FakeResp:
        status = 200
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(req, timeout=None):
        seen["token"] = req.get_header("X-bench-token")
        return FakeResp()

    real = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        runner.post("http://x/webhook", {}, 5)
    finally:
        urllib.request.urlopen = real
    assert seen["token"] == os.environ["BENCH_WEBHOOK_TOKEN"]


def test_census_weight():
    # census: uncached*1 + cached*0.1 + output*4 ; cache writes weighted 1 (census has no cache-write term)
    u = {"input_tokens": 100, "output_tokens": 10, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 1000}
    assert abs(cost.weighted(u) - (150 + 100 + 40)) < 1e-9


def test_census_turn_adapter():
    rows = [{"usage": {"input_tokens": 7, "output_tokens": 3, "cache_creation_input_tokens": 2,
                       "cache_read_input_tokens": 5}}]
    assert cost.census_turns(rows) == [(14, 5, 3)]  # prompt = input + write + read, cached = read


def _ok_stage(n):
    return {"http_status": 200, "request_id": f"req_{n}", "stop_reason": "end_turn", "latency_ms": 100,
            "usage_raw": dict(USAGE), "output": "{}"}


def _ok_response():
    return {"stages": {s: _ok_stage(i) for i, s in enumerate(runner.STAGES)}}


def _fail_500(completed, failed_stage="review"):
    payload = {"failed_stage": failed_stage, "http_status": 529, "error_type": "overloaded_error",
               "error_message": "Overloaded", "request_id": "req_fail", "retry_after": None,
               "completed": completed}
    return 500, {"message": "The workflow failed. SDLC_STAGE_FAILED " + json.dumps(payload)}, {}


def _workdir():
    d = Path(tempfile.mkdtemp(prefix="s2test_"))
    return d, d / "runs.jsonl", d / "outputs.jsonl"


def _rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_retry_logs_completed_stages_of_failed_attempt():
    d, out, outputs = _workdir()
    try:
        completed = {s: _ok_stage(i) for i, s in enumerate(runner.STAGES[:3])}  # triage..plan done, review 529
        seq = [_fail_500(completed), (200, _ok_response(), {})]
        calls = []

        def fake(url, body, timeout):
            calls.append(body["run_id"])
            return seq.pop(0)

        runner.main(["--tickets", "T01", "--arms", "control", "--reps", "1", "--cap-usd", "5", "--sleep-scale", "0",
                     "--out", str(out), "--outputs", str(outputs)], post_fn=fake)
        rows = _rows(out)
        assert len(calls) == 2
        attempts = [r for r in rows if r["kind"] == "attempt_error"]
        assert len(attempts) == 1 and attempts[0]["failed_stage"] == "review" and attempts[0]["usage_known"] is True
        calls_rows = [r for r in rows if r["kind"] == "call"]
        assert [r["attempt"] for r in calls_rows] == [1, 1, 1] + [2] * 5  # failed attempt's billed stages kept
        run = [r for r in rows if r["kind"] == "run"][-1]
        assert run["status"] == "ok" and run["attempts"] == 2
        assert run["usage_total"]["input_tokens"] == 1000 * 8
    finally:
        shutil.rmtree(d)


def test_budget_stop_before_any_call():
    d, out, outputs = _workdir()
    try:
        prices_path = d / "prices.json"
        prices_path.write_text(json.dumps(dict(PRICES)), encoding="utf-8")
        calls = []

        def fake(url, body, timeout):
            calls.append(1)
            return 200, _ok_response(), {}

        # worst-case run for max_tokens 2048 is 5*(20000*0.1 + 2048*0.5)/1e6 ~ $0.0106 > cap
        try:
            runner.main(["--tickets", "T01", "--arms", "control", "--cap-usd", "0.001", "--prices", str(prices_path),
                         "--out", str(out), "--outputs", str(outputs)], post_fn=fake)
            raise AssertionError("expected budget stop")
        except SystemExit as e:
            assert "cap" in str(e)
        assert calls == []
        assert _rows(out)[-1]["kind"] == "budget_stop"
    finally:
        shutil.rmtree(d)


def test_resume_skips_completed_runs():
    d, out, outputs = _workdir()
    try:
        argv = ["--tickets", "T01", "--arms", "control", "--cap-usd", "5", "--sleep-scale", "0",
                "--out", str(out), "--outputs", str(outputs)]
        runner.main(argv, post_fn=lambda u, b, t: (200, _ok_response(), {}))
        calls = []
        runner.main(argv, post_fn=lambda u, b, t: calls.append(b) or (200, _ok_response(), {}))
        assert calls == []
    finally:
        shutil.rmtree(d)


def test_workflow_never_contains_key_and_anthropic_body_has_no_sampling():
    wf = json.loads((HERE / "workflow_stage2.json").read_text(encoding="utf-8"))
    text = json.dumps(wf)
    assert "$env.ANTHROPIC_API_KEY" in text
    assert "sk-ant-" not in text
    assert "body.anthropic_base_url" not in text and "body.ollama_base_url" not in text
    for n in wf["nodes"]:
        expr = n.get("parameters", {}).get("jsonBody", "")
        if expr:
            assert "temperature" in expr  # ollama branch keeps it
            assert "thinking: { type: 'disabled' }" in expr  # anthropic branch disables thinking explicitly


AUTH_CASES = [
    # (token in n8n env, header sent, expected auth_ok)
    ("s3cret-value", "s3cret-value", True),
    ("s3cret-value", "s3cret-valuX", False),
    ("s3cret-value", "s3cret-value ", False),
    ("s3cret-value", "", False),
    ("", "", False),  # unset/empty token in the container rejects everything
]


def test_auth_gate_compares_token_and_fails_closed():
    # Runs the real Code node from the built workflow in node, with $env and $input stubbed.
    if shutil.which("node") is None:
        print("skipped: node not on PATH")
        return
    wf = json.loads((HERE / "workflow_stage2.json").read_text(encoding="utf-8"))
    code = next(n for n in wf["nodes"] if n["name"] == "auth")["parameters"]["jsCode"]
    driver = ("const code = process.argv[1]; const cases = JSON.parse(process.argv[2]);"
              "console.log(JSON.stringify(cases.map(c => new Function('$env', '$input', code)"
              "({BENCH_WEBHOOK_TOKEN: c.env}, {first: () => ({json: {headers: c.headers}})})[0].json.auth_ok)));")
    cases = [{"env": env, "headers": {"x-bench-token": got}} if got != "" else {"env": env, "headers": {}}
             for env, got, _ in AUTH_CASES]
    r = subprocess.run(["node", "-e", driver, code, json.dumps(cases)], capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == [want for *_, want in AUTH_CASES]


def test_auth_failure_only_reaches_401_and_api_nodes_only_after_auth():
    wf = json.loads((HERE / "workflow_stage2.json").read_text(encoding="utf-8"))
    conn = wf["connections"]
    assert next(n for n in wf["nodes"] if n["name"] == "Webhook")["parameters"]["responseMode"] == "responseNode"
    assert conn["Webhook"]["main"][0][0]["node"] == "auth"
    assert conn["if_auth"]["main"][1] == [{"node": "respond_401", "type": "main", "index": 0}]
    assert "respond_401" not in conn  # the 401 branch ends at the response

    def reach(start):
        seen, todo = set(), [start]
        while todo:
            name = todo.pop()
            for i, outs in enumerate(conn.get(name, {}).get("main", [])):
                if name == "if_auth" and i != 0:
                    continue
                for o in outs:
                    if o["node"] not in seen:
                        seen.add(o["node"])
                        todo.append(o["node"])
        return seen

    http_nodes = {n["name"] for n in wf["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"}
    assert http_nodes <= reach("Webhook")  # every stage is reachable...
    assert not (http_nodes & reach("respond_401"))  # ...and none is reachable from the 401 branch


def test_stage1_workflow_untouched():
    import subprocess
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(HERE / "workflow.json")], capture_output=True)
    assert r.returncode == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
