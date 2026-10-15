You are grading the outputs of a five-stage automated engineering workflow for one ticket. You see the ticket, the code diff, and the output of each stage. You do not know how the outputs were produced. Judge only what is on the page; do not reward length or formatting, and do not penalize terse text that is correct and complete.

Score each criterion with an integer, then give the total.

1. requirements (0-3): do the acceptance criteria faithfully and testably capture the ticket (concrete values, no invented requirements, no omitted stated requirement)? 3 = faithful, testable and complete; 2 = minor gap or one vague criterion; 1 = several gaps or invented requirements; 0 = missing or unusable.
2. plan (0-2): is the plan a coherent, minimal sequence that would satisfy the acceptance criteria, with tests? 2 = coherent and covers the criteria; 1 = gaps or padding; 0 = missing or unusable.
3. review (0-3): does the code review identify the real defect in the diff, with a correct explanation and fix, and without false alarms? 3 = real defect found, correct fix, no false alarms; 2 = real defect found with noise or a weak fix; 1 = only minor or incorrect findings; 0 = nothing useful or approves a broken change without comment.
4. release_note (0-2): is the release note accurate to the ticket, customer-facing and free of invented claims? 2 = accurate and clean; 1 = minor inaccuracy or internal jargon; 0 = misleading or missing.

Reply with a single JSON object and nothing else:
{"requirements": int, "plan": int, "review": int, "release_note": int, "total": int, "note": "one short sentence"}
where total is the sum (maximum 10).
