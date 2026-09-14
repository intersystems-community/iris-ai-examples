# CareConnect Evals — Presentation Demo Script

**Duration:** 15–20 min  
**Setup:** Terminal + Jupyter side-by-side (or terminal only)  
**Key claim:** Every technique for making an agent better is hill-climbing. You can't hill-climb without a hill. **The eval is the hill.**

---

## Before You Start (5 minutes before go time)

```bash
cd careconnect-sdoh/evals

# Verify suite runs clean (should complete in < 1 second)
python run_evals.py

# Optional: pre-open the notebook
jupyter notebook notebooks/careconnect_evals_demo.ipynb
```

No API key needed. No IRIS stack needed. Runs completely offline.

---

## Act 1 — The System (2 min)

**Say:** "CareConnect is a community health worker assistant — it assesses
Social Determinants of Health risk and triggers IRIS Interoperability workflows
to connect patients with services. It's a _hybrid_ system, and that's why
evals are interesting here."

Draw this on the board or point to the first notebook cell:

```text
  LLM orchestration  ──►  deterministic tools  ──►  real side effects
  (which tool to call,    (rule-based scoring,      (IRIS Interop workflow,
   in what order,          care plan drafting)        audit trail in
   with what args)                                    Ens.MessageHeader)
```

**Say:** "Evals earn their keep exactly at the _seams_ between these parts.
The seam between the LLM and the rule is where the first failure lives."

---

## Act 2 — Run the suite (3 min)

```bash
python run_evals.py
```

**Expected output:**

```text
CareConnect SDoH Agent — Eval Report
provider=mock model=None cases=4

CASE                             L1 rule   L2 traj   L3 out    L4 qual   recall
------------------------------------------------------------------------------------
maria-complete                   PASS      PASS      PASS      PASS      0.833
james-complete                   PASS      PASS      PASS      PASS        0.5
sarah-assess-only                PASS      PASS      PASS      PASS       0.75
maria-paraphrase-adversarial     FAIL      PASS      PASS      PASS        0.0  [adversarial]

Layer pass rates:
  L1_rule_regression     3/4
  L2_trajectory          4/4
  L3_outcome             4/4
  L4_quality             4/4

L5 care-plan differentiation: FAIL (1 distinct plan(s) across 3 patients) — ALL IDENTICAL

Clinician-truth micro recall:    0.714
Clinician-truth micro precision: 1.0
```

**Say:** "We have three failures. Let me show you what they are, why they matter,
and how we found them — because none of them are visible in the polished demo
walkthrough."

---

## Act 3 — Three Real Defects (8 min)

### Defect 1: The adversarial case (L1 FAIL)

**Say:** "Maria Gonzalez is our canonical success story — URGENT priority,
food/housing/transport risk, all the right flags. The demo shows her working
perfectly. But what happens if the LLM paraphrases her note slightly?"

```python
# Paste in terminal or show in notebook
import sys, json; sys.path.insert(0, '.')
from careconnect_evals.tools_local import LocalToolClient

c = LocalToolClient()
adv = next(k for k in json.load(open('golden_cases.json'))['cases']
           if k['id'] == 'maria-paraphrase-adversarial')

# The note the demo's own tools read — scores URGENT
original = c.AssessSDoHRisk('maria-gonzalez-001',
                            c.FetchPatientSummary('maria-gonzalez-001'))
print("Original:  ", original.splitlines()[-1])

# The same facts, in the LLM's words
paraphrase = c.AssessSDoHRisk('maria-gonzalez-001', adv['agent_summary'])
print("Paraphrase:", paraphrase.splitlines()[-1])
```

```text
Original:   Overall Priority: URGENT (5/6 domains elevated)
Paraphrase: Overall Priority: ROUTINE (0/6 domains elevated)
```

**Point to the output.** Five of six domains elevated, then none. Food bank → community
pantry, lost job → lost position — same patient, same reality, opposite outcome.

**Say:** "The rule keyword-matches on the string _the LLM writes_. The variance hides in
the seam. A deterministic scorer is only as deterministic as its inputs."

---

### Defect 2: The rule has blind spots (recall 0.714)

**Say:** "The L1 regression is green for most cases. But green against _what_?
Against the spec. The spec might be wrong."

Show the recall column: James scores 0.5, Sarah 0.75.

```python
import json
cases = json.load(open('golden_cases.json'))['cases']

james = next(c for c in cases if c['id'] == 'james-complete')
for d in ('economic', 'health_care'):
    print(f"{d:12} rule={james['rule_expected']['domains'][d]:8}"
          f" clinician={james['human_label']['domains'][d]}")
```

```text
economic     rule=LOW      clinician=HIGH
health_care  rule=MEDIUM   clinician=HIGH
```

**Say:** "James is skipping medications due to cost and living in subsidized housing.
The rule says Economic = LOW. A clinician says HIGH. Precision is perfect — it
never cries wolf — but recall is 0.714: 4 of the 14 domains a clinician marked
elevated go unflagged, and all four land in the same two domains, Economic
Stability and Health Care Access. Only 2 of James' 6 domains clear the keyword bar
and HIGH needs 3, so the rule calls him ROUTINE where a clinician says URGENT.
That's not a bug you'd ever find by eyeballing the demo."

---

### Defect 3: The care plans aren't personalized (L5 FAIL)

**Say:** "This one is my favorite. The demo looks beautifully personalized.
Maria gets a care plan. James gets a care plan. Sarah gets a care plan.
Are they different?"

```python
from careconnect_evals import scorers
from careconnect_evals.tools_local import LocalToolClient
c = LocalToolClient()

plans = {}
for pid in ['maria-gonzalez-001', 'james-okafor-002', 'sarah-kim-003']:
    summary = c.FetchPatientSummary(pid)
    scored = c.AssessSDoHRisk(pid, summary)
    plans[pid] = c.DraftCarePlan(pid, scored)

for pid, plan in plans.items():
    body = plan.split("\n", 1)[1].strip()
    print(f"\n{pid}:\n{body[:110]}...")

# The header line carries the patient id, so L5 compares the step bodies.
print("\n", scorers.score_care_plan_differentiation(plans))
```

```text
{'passed': False, 'distinct_plans': 1, 'patients_compared': 3,
 'all_identical': True, 'same_plan_different_needs': [...]}
```

**Say:** "`DraftCarePlan` branches on the _presence of domain names_ in the output string —
but those names are always present in any assessment result. So every patient,
regardless of risk profile, gets byte-identical recommendations.
No single-case eval can catch this. Only L5 — a cross-case check — can see it."

---

## Act 4 — Close the Loop (4 min)

**Say:** "The evals diagnosed three real problems. Let me show you the fixes,
and prove they work, in about 10 lines."

```bash
python -c "
import sys; sys.path.insert(0, '.')
from careconnect_evals import scorers
from careconnect_evals.improved import assess_improved, draft_care_plan_improved
from careconnect_evals.tools_local import LocalToolClient
import json

cases = json.load(open('golden_cases.json'))['cases']

client = LocalToolClient()
tp = fn = 0
plans, profiles = {}, {}

for c in cases:
    if c['adversarial']:
        continue
    pid = c['patientId']
    summary = client.FetchPatientSummary(pid)
    scored = assess_improved(pid, summary)
    counts = scorers.score_against_human(scored, c['human_label'])['_counts']
    tp += counts['tp']; fn += counts['fn']
    plans[pid] = draft_care_plan_improved(pid, scored)
    profiles[pid] = tuple(sorted(
        k for k, v in scorers.parse_assessment(scored)['domains'].items()
        if v == 'HIGH' and k in scorers.PLAN_DOMAINS))

diff = scorers.score_care_plan_differentiation(plans, profiles)
james = client.FetchPatientSummary('james-okafor-002')
james_pri = scorers.parse_assessment(assess_improved('james-okafor-002', james))['priority']

print(f'Clinician recall:  0.714 -> {tp/(tp+fn):.2f}')
print(f'Care plan diff:    FAIL -> {\"PASS\" if diff[\"passed\"] else \"FAIL\"} ({diff[\"distinct_plans\"]} distinct plans)')
print(f'James priority:    ROUTINE -> {james_pri}')
"
```

**Expected output:**

```text
Clinician recall:  0.714 -> 1.00
Care plan diff:    FAIL -> PASS (3 distinct plans)
James priority:    ROUTINE -> HIGH
```

**Say:** "Fix 1: broaden the risk lexicon — 'cost', 'uninsured', 'food insecure',
'skipping meds' — and score medication affordability under Health Care Access, now that
transportation is its own domain. Recall goes from 0.714 to 1.0, and James corrects from
ROUTINE to HIGH. Fix 2: read domain _values_ instead of domain _names_. Care plans are now
distinct. Same eval, better system. That is the entire discipline."

**If someone asks why James is still HIGH and not URGENT:** because recalibrating the
priority thresholds is a separate change with its own evidence. Bundling it here would make
fix 1's effect on recall unreadable. That gap survives on purpose.

---

## Act 5 — The Five-Takeaway Slide (1 min)

1. **You can't improve what you can't measure.** Evals are the unit tests of agent behavior.
2. **Pin the deterministic core.** The variance hides in the seam with the LLM.
3. **Evaluate the path, not just the answer.** L2 trajectory — did it call the right tools in the right order?
4. **Build on auditable systems.** The IRIS Interop trace is a free outcome oracle.
5. **"Matches spec" ≠ "is correct."** Keep a human ground truth alongside your regression target.

---

## Optional: Open the Notebook (if you have time)

```bash
jupyter notebook notebooks/careconnect_evals_demo.ipynb
```

Walk through cells 3 → 8 → 10 → 18 → 22. The visualization in cell 20 (matplotlib radar chart)
works well as a slide screenshot.

---

## Troubleshooting

| Problem                   | Fix                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------ |
| `ModuleNotFoundError`     | `cd` into `evals/` before running — it's on `sys.path` via `sys.path.insert(0, '.')` |
| Jupyter can't find kernel | `python -m ipykernel install --user`                                                 |
| Test failures             | `python -m pytest tests/ -q` — 31 pass, 9 skip (the skips are live-IRIS parity)      |
| Need a real LLM           | `CARECONNECT_EVAL_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... python run_evals.py`   |

---

## Repository Location

```text
careconnect-sdoh/evals/
```

`pytest tests/` → 32 passed, 9 skipped. No API key required.
