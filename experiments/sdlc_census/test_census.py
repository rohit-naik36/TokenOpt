"""Small asserts: classifier, accounting identities. Run: .venv/Scripts/python.exe experiments/sdlc_census/test_census.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import census as c  # noqa: E402


def test_classifier():
    assert c.classify("Read", {}, "x") == "tr_file_reads"
    assert c.classify("Bash", {"command": "python -m pytest -v"}, "...") == "tr_test_ci"
    assert c.classify("Bash", {"command": "git diff HEAD"}, "...") == "tr_diffs"
    assert c.classify("Bash", {"command": "curl x"}, '{"a": 1}') == "tr_json_logs"
    assert c.classify("Edit", {}, "File updated") == "tr_other"
    assert c.content_class("diff --git a/x b/x\n@@ -1,2 +1,2 @@") == "tr_diffs"


def test_accounting_identities():
    # 2 turns, static 1000 + one 200-token file read entering turn 2; turn 2 cached 1000 (clean extension)
    s = {"aegis": False, "turns": [(1000, 0, 50), (1250, 1000, 10)],
         "ctx": [[(c.STATIC, 1000, None)], [(c.STATIC, 1000, None), (c.HIST, 50, None), ("tr_file_reads", 200, ("t", 1))]]}
    a = c.account(s)
    assert a["P"] == 2250 and a["C"] == 1000 and a["O"] == 60
    assert abs(a["W"] - (1000 + 250 + 100 + 4 * 60)) < 1e-6                 # uncached 1000 + 250, cached 1000*0.1, output 4*60
    assert a["breaks"] == []
    sh = c.shares(a)
    tot = sum(v["w_share"] for v in sh["rows"].values())
    assert abs(tot - 1) < 1e-9                                               # categories + output partition the weighted cost
    fr = sh["rows"]["tr_file_reads"]
    assert abs(fr["first_w_share"] + fr["rebill_w_share"] - fr["w_share"]) < 1e-9


def test_break_detected():
    s = {"aegis": False, "turns": [(2000, 0, 10), (2500, 100, 10)],           # extends previous but only 100 cached -> break
         "ctx": [[(c.STATIC, 2000, None)], [(c.STATIC, 2000, None), (c.HIST, 500, None)]]}
    a = c.account(s)
    assert len(a["breaks"]) == 1 and a["breaks"][0]["shortfall_tokens"] == 1900


if __name__ == "__main__":
    test_classifier()
    test_accounting_identities()
    test_break_detected()
    print("test_census: 3 passed")
