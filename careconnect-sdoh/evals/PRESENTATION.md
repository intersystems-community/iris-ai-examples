# CareConnect Evals — Presentation Demo Script

**Duration:** 15–20 min  
**Setup:** Terminal + Jupyter side-by-side (or terminal only)  
**Key claim:** Every technique for making an agent better is hill-climbing. You can't hill-climb without a hill. **The eval is the hill.**

---

## Before You Start (5 minutes before go time)

```bash
cd ~/ws/iris-ai-examples/careconnect-sdoh/evals

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
to connect patients with services. It's a *hybrid* system, and that's why
evals are interesting here."

Draw this on the board or point to the first notebook cell:

```
  LLM orchestration  ──►  deterministic tools  ──►  real side effects
  (which tool to call,    (rule-based scoring,      (IRIS Interop workflow,
   in what order,          care plan drafting)        audit trail in
   with what args)                                    Ens.MessageHeader)
```

**Say:** "Evals earn their keep exactly at the *seams* between these parts.
The seam between the LLM and the rule is where the first failure lives."

---

## Act 2 — Run the suite (3 min)

```bash
python run_evals.py
```

**Expected output:**

```
CareConnect SDoH Agent — Eval Report
provider=mock model=None cases=4

CASE                             L1 rule   L2 traj   L3 out    L4 qual   recall
------------------------------------------------------------------------------------
maria-complete                   PASS      PASS      PASS      PASS        1.0
james-complete                   PASS      PASS      PASS      PASS        0.5
sarah-assess-only                PASS      PASS      PASS      PASS      0.667
maria-paraphrase-adversarial     FAIL      PASS      PASS      PASS        0.0  [adversarial]

Layer pass rates:
  L1_rule_regression     3/4
  L2_trajectory          4/4
  L3_outcome             4/4
  L4_quality             4/4

L5 care-plan differentiation: FAIL (1 distinct plan(s) across 3 patients) — ALL IDENTICAL

Clinician-truth micro recall:    0.75
Clinician-truth micro precision: 1.0
```

**Say:** "We have three failures. Let me show you what they are, why they matter,
and how we found them — because none of them are visible in the polished demo
walkthrough."

---

## Act 3 — Three Real Defects (8 min)

### Defect 1: The adversarial case (L1 FAIL)

**Say:** "Maria Garcia is our canonical success story — URGENT priority,
food/housing/transport risk, all the right flags. The demo shows her working
perfectly. But what happens if the LLM paraphrases her note slightly?"

```python
# Paste in terminal or show in notebook
import sys; sys.path.insert(0, '.')
from careconnect_evals.tools_local import LocalToolClient

c = LocalToolClient()

# The original note — scores URGENT
result1 = c.AssessSDoHRisk("maria-garcia-001",
    "Lost her job, relies on food bank, no transportation to clinic")
print("Original:", result1[:80])

# A paraphrase — identical meaning, different words
result2 = c.AssessSDoHRisk("maria-garcia-001",
    "Lost her position, uses community pantry, cannot travel to appointments")
print("Paraphrase:", result2[:80])
```

**Point to the output.** Priority flips from URGENT to ROUTINE. Food bank → community pantry,
lost job → lost position — same patient, same reality, opposite outcome.

**Say:** "The rule keyword-matches on the string *the LLM writes*. The variance hides in
the seam. A deterministic scorer is only as deterministic as its inputs."

---

### Defect 2: The rule has blind spots (recall 0.75)

**Say:** "The L1 regression is green for most cases. But green against *what*?
Against the spec. The spec might be wrong."

Show the recall column: James scores 0.5, Sarah 0.667.

```python
import json
with open('golden_cases.json') as f:
    cases = json.load(f)

james = next(c for c in cases if c['id'] == 'james-complete')
print("Rule says Economic =", james['rule_expected']['domains']['Economic'])
print("Clinician says Economic =", james['human_label']['domains']['Economic'])
```

**Say:** "James is skipping medications due to cost and living in subsidized housing.
The rule says Economic = LOW. A clinician says HIGH. Precision is perfect — it
never cries wolf — but recall is 0.75. It misses one in four genuine social needs.
That's not a bug you'd ever find by eyeballing the demo."

---

### Defect 3: The care plans aren't personalized (L5 FAIL)

**Say:** "This one is my favorite. The demo looks beautifully personalized.
Maria gets a care plan. James gets a care plan. Sarah gets a care plan.
Are they different?"

```python
from careconnect_evals.tools_local import LocalToolClient
c = LocalToolClient()

plans = {}
for pid in ['maria-garcia-001', 'james-okafor-002', 'sarah-chen-003']:
    summary = c.FetchPatientSummary(pid)
    scored = c.AssessSDoHRisk(pid, summary)
    plans[pid] = c.DraftCarePlan(pid, scored)

for pid, plan in plans.items():
    print(f"\n{pid}:\n{plan[:120]}...")

# Are they the same?
vals = list(plans.values())
print("\nAll identical?", vals[0] == vals[1] == vals[2])
```

**Say:** "`DraftCarePlan` branches on the *presence of domain names* in the output string —
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

with open('golden_cases.json') as f:
    cases = json.load(f)

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

print(f'Clinician recall:  0.75 -> {tp/(tp+fn):.2f}')
print(f'Care plan diff:    FAIL -> {\"PASS\" if diff[\"passed\"] else \"FAIL\"} ({diff[\"distinct_plans\"]} distinct plans)')
print(f'James priority:    HIGH -> {james_pri}')
"
```

**Expected output:**
```
Clinician recall:  0.75 -> 1.00
Care plan diff:    FAIL -> PASS (3 distinct plans)
James priority:    HIGH -> URGENT
```

**Say:** "Fix 1: broaden the risk lexicon — 'cost', 'uninsured', 'food insecure',
'skipping meds'. Recall goes from 0.75 to 1.0. James' priority corrects from HIGH to URGENT.
Fix 2: read domain *values* instead of domain *names*. Care plans are now distinct.
Same eval, better system. That is the entire discipline."

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

| Problem | Fix |
|---|---|
| `ModuleNotFoundError` | `cd` into `evals/` before running — it's on `sys.path` via `sys.path.insert(0, '.')` |
| Jupyter can't find kernel | `python -m ipykernel install --user` |
| Test failures | `python -m pytest tests/test_harness.py -v` — all 6 should pass in 0.02s |
| Need a real LLM | `CARECONNECT_EVAL_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... python run_evals.py` |

---

## Repository Location

```
~/ws/iris-ai-examples/careconnect-sdoh/evals/
```

Committed at `5ea5993`. All 6 tests pass. No API key required.
