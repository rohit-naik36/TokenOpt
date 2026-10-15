"""Post-hoc diagnosis of unparseable review outputs in Stage 2 phase A (descriptive only).

Reads full_s2_outputs.jsonl and full_s2_scored.jsonl. Does not change any gate,
threshold or scored value. Run from this folder: python stage2_json_diagnosis.py
"""
import collections
import json
import re

import score as s1

GT = json.load(open("tickets/ground_truth.json", encoding="utf-8"))["tickets"]
ARMS = ["control", "A", "H", "AH"]


def load():
    sc = {}
    for line in open("full_s2_scored.jsonl", encoding="utf-8"):
        r = json.loads(line)
        sc[r["run_id"]] = r
    out = collections.defaultdict(dict)
    for line in open("full_s2_outputs.jsonl", encoding="utf-8"):
        r = json.loads(line)
        out[r["run_id"]][r["stage"]] = r["output"]
    return sc, out


def junction(text):
    """The characters between the last '}' of the findings list and the '"summary"' key."""
    i = text.rfind('"summary"')
    if i < 0:
        return None
    head = text[:i].rstrip()
    m = re.search(r"\}([^{}]*)$", head)
    return m.group(1).strip() if m else None


def tail_repair(text):
    """Cut at the last '"summary"' key, force the findings list closed, re-add the summary."""
    i = text.rfind('"summary"')
    if i < 0:
        return None
    head = text[:i].rstrip()
    m = re.search(r"^(.*\})[^{}]*$", head, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1) + '], "summary": "(repaired)"}')
    except json.JSONDecodeError:
        return None


def ticket_of(rid):
    return re.search(r"-(T\d\d)-", rid).group(1)


def main():
    sc, out = load()
    inv = {a: [] for a in ARMS}
    for rid, st in out.items():
        try:
            json.loads(st["review"])
        except json.JSONDecodeError:
            inv[sc[rid]["arm"]].append(rid)
    print("| arm | invalid reviews | junction is `]]`/`]\"`/`])`/`].` etc. before summary | other | recovered by tail repair | defect-hit strict | defect-hit after tail repair |")
    print("|---|---|---|---|---|---|---|")
    for a in ARMS:
        rids = inv[a]
        weird = sum(1 for r in rids if junction(out[r]["review"]) not in (None, "]", "],", ""))
        rec = 0
        hit_strict = sum(1 for r in sc if sc[r]["arm"] == a and sc[r]["defect_hit"])
        hit_rep = hit_strict
        for r in rids:
            d = tail_repair(out[r]["review"])
            if d is not None:
                rec += 1
                if s1.defect_hit(d, GT[ticket_of(r)])[0]:
                    hit_rep += 1
        print(f"| {a} | {len(rids)} | {weird} | {len(rids) - weird} | {rec} | {hit_strict}/40 | {hit_rep}/40 |")
    # valid JSON whose summary key is missing or misnamed
    print()
    print("| arm | valid JSON, `summary` key missing | key named ' summary' |")
    print("|---|---|---|")
    for a in ARMS:
        miss = mis = 0
        for rid, st in out.items():
            if sc[rid]["arm"] != a:
                continue
            try:
                d = json.loads(st["review"])
            except json.JSONDecodeError:
                continue
            if "summary" not in d:
                miss += 1
                if " summary" in d:
                    mis += 1
        print(f"| {a} | {miss} | {mis} |")
    print()
    c = collections.Counter(junction(out[r]["review"]) for a in ARMS for r in inv[a])
    print("junction strings before \"summary\" (invalid reviews):", dict(c.most_common(8)))


if __name__ == "__main__":
    main()
