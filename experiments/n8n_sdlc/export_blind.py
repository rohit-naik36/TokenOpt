"""Export anonymized judge packets. Usage: python export_blind.py runs.jsonl OUT_DIR MAP.json
Packets carry no arm label, run_id or rep; the id-to-run map goes to a separate file that must not be
opened until scoring is finished. Scores are joined to arms only afterwards."""
import json
import random
import secrets
import sys
from pathlib import Path

HERE = Path(__file__).parent
runs_path, out, mapping = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
rows = [json.loads(l) for l in runs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
ok = [r for r in rows if r["kind"] == "run" and r["status"] == "ok"]
stg = {}
for r in rows:
    if r["kind"] == "stage":
        stg.setdefault(r["run_id"], {})[r["stage"]] = r["output"]
random.Random(secrets.randbits(32)).shuffle(ok)
out.mkdir(parents=True, exist_ok=True)
m = {}
for run in ok:
    t = json.loads((HERE / "tickets" / f"{run['ticket_id']}.json").read_text(encoding="utf-8"))
    pid = secrets.token_hex(4)
    m[pid] = run["run_id"]
    diff = t.pop("diff")
    text = "## Ticket\n" + json.dumps(t, indent=2) + "\n\n## Diff\n" + diff
    for s in ("triage", "requirements", "plan", "review", "release_note"):
        text += f"\n\n## Stage output: {s}\n{stg[run['run_id']][s]}"
    (out / f"{pid}.md").write_text(text, encoding="utf-8")
mapping.write_text(json.dumps(m, indent=1), encoding="utf-8")
print(len(m), "packets")
