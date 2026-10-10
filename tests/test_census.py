from __future__ import annotations

import json
from pathlib import Path

import pytest

from tokenopt import census as c

ROOT = Path(__file__).resolve().parent.parent
TRACES = ROOT / "experiments" / "agent_benchmark" / "traces"
BASE = ROOT / "experiments" / "cost_model" / "results" / "baseline_variance"


def _row(prompt: int, cached: int, extra: dict | None = None) -> dict:
    r = {
        "trace_version": "agent-trace/v1",
        "request": {
            "messages": [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]
        },
        "response": {
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": 10,
                "prompt_tokens_details": {"cached_tokens": cached},
            }
        },
    }
    r.update(extra or {})
    return r


def _write(tmp_path: Path, rows: list[dict]) -> Path:
    (tmp_path / "t.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return tmp_path


def test_classifier() -> None:
    assert c.classify("Read", {}, "x") == "tr_file_reads"
    assert c.classify("Bash", {"command": "python -m pytest"}, "") == "tr_test_ci"
    assert c.classify("Bash", {"command": "git diff"}, "") == "tr_diffs"
    assert c.classify("Bash", {"command": "curl x"}, '{"a": 1}') == "tr_json_logs"
    assert c.classify("Edit", {}, "ok") == "tr_other"


def test_accounting_identities() -> None:
    s = {
        "aegis": False,
        "turns": [(1000, 0, 50), (1250, 1000, 10)],
        "ctx": [
            [(c.STATIC, 1000, None)],
            [(c.STATIC, 1000, None), (c.HIST, 50, None), ("tr_file_reads", 200, ("t", 1))],
        ],
    }
    a = c.pool([c.account(s)])
    sh = c.shares(a)
    assert abs(sum(v["w"] for v in sh["rows"].values()) - 1) < 1e-9
    fr = sh["rows"]["tr_file_reads"]
    assert abs(fr["first_w"] + fr["rebill_w"] - fr["w"]) < 1e-9


def test_v1_rows_without_workflow_fields_give_unknown_handoff(tmp_path: Path) -> None:
    sh = c.census(_write(tmp_path, [_row(100, 0), _row(150, 100)]))
    assert sh is not None and sh["handoff"] is None
    assert sh["levers"][-1]["lever"] == "handoff payload" and sh["levers"][-1]["w_ub"] is None
    assert "UNKNOWN" in c.render("x", sh)


def test_handoff_payload_share(tmp_path: Path) -> None:
    extra = {
        "workflow_id": "w",
        "parent_workflow_id": None,
        "agent": "a",
        "step": 1,
        "handoff": {"payload_tokens": 40, "used_tokens": 10},
    }
    sh = c.census(_write(tmp_path, [_row(100, 0, extra)]))
    assert sh is not None and sh["handoff"]["used_tokens"] == 10
    assert abs(sh["handoff"]["share"] - 40 / 110) < 1e-9


def test_aegis_run_dir_detected(tmp_path: Path) -> None:
    run = tmp_path / "runs" / "r1"
    (run / "raw").mkdir(parents=True)
    ev = [
        {"input_tokens": 500, "cached_prefix_tokens": 0, "output_tokens": 5},
        {"input_tokens": 700, "cached_prefix_tokens": 500, "output_tokens": 5},
    ]
    (run / "events.jsonl").write_text("\n".join(json.dumps(e) for e in ev), encoding="utf-8")
    stream = [
        {
            "type": "assistant",
            "message": {
                "id": "m1",
                "content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}],
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "hello"}]
            },
        },
        {
            "type": "assistant",
            "message": {"id": "m2", "content": [{"type": "text", "text": "done"}]},
        },
    ]
    (run / "raw" / "stream.jsonl").write_text(
        "\n".join(json.dumps(e) for e in stream), encoding="utf-8"
    )
    sh = c.census(tmp_path)
    assert sh is not None and sh["n_turns"] == 2 and sh["rows"]["tr_file_reads"]["tok"] > 0


@pytest.mark.skipif(not TRACES.is_dir() or not BASE.is_dir(), reason="real trace dirs absent")
def test_reproduces_experiment_census() -> None:
    oc = c.census(TRACES)
    assert oc is not None
    r = oc["rows"]
    assert r["tr_file_reads"]["tok"] == pytest.approx(0.638, abs=0.005)
    assert r["tr_file_reads"]["w"] == pytest.approx(0.679, abs=0.005)
    assert oc["break_w"] == pytest.approx(0.222, abs=0.005)
    assert r["output"]["tok"] == pytest.approx(0.007, abs=0.005)
    assert r["output"]["w"] == pytest.approx(0.079, abs=0.005)
    bv = c.census(BASE)
    assert bv is not None and bv["n_sessions"] == 10 and bv["n_turns"] == 106
    assert bv["rows"]["output"]["w"] == pytest.approx(0.4505, abs=0.005)
    assert bv["rows"]["tr_test_ci"]["tok"] == pytest.approx(0.0773, abs=0.005)
