"""Export anonymized judge packets for Stage 2 (same packet format as export_blind.py).

    python stage2_export_blind.py OUT_DIR MAP.json

Packets carry no arm label, run_id or rep. The id-to-run map goes to a separate file that must not be opened
until the judge's scores are written to disk. Stage 2 rows are usage-shaped, so this reads full_s2_runs.jsonl
and full_s2_outputs.jsonl directly rather than going through export_blind.py.
"""
import json
import secrets
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
STAGES = ("triage", "requirements", "plan", "review", "release_note")


def main():
    out, mapping = Path(sys.argv[1]), Path(sys.argv[2])
    rows = [json.loads(l) for l in (HERE / "full_s2_runs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    outs = {}
    for o in (json.loads(l) for l in (HERE / "full_s2_outputs.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()):
        outs[(o["run_id"], o["stage"])] = o["output"]
    ok = [r for r in rows if r["kind"] == "run" and r["status"] == "ok"]
    if len(ok) != 160:
        sys.exit(f"expected 160 ok runs, found {len(ok)}")
    random.Random(secrets.randbits(32)).shuffle(ok)
    out.mkdir(parents=True, exist_ok=True)
    m = {}
    for run in ok:
        t = json.loads((HERE / "tickets" / f"{run['ticket']}.json").read_text(encoding="utf-8"))
        pid = secrets.token_hex(4)
        while pid in m:
            pid = secrets.token_hex(4)
        m[pid] = run["run_id"]
        diff = t.pop("diff")
        text = "## Ticket\n" + json.dumps(t, indent=2) + "\n\n## Diff\n" + diff
        for s in STAGES:
            text += f"\n\n## Stage output: {s}\n{outs[(run['run_id'], s)]}"
        (out / f"{pid}.md").write_text(text, encoding="utf-8")
    mapping.write_text(json.dumps(m, indent=1), encoding="utf-8")
    print(len(m), "packets")


if __name__ == "__main__":
    main()
