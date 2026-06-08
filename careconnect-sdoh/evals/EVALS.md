# Evaluating the CareConnect SDoH Agent

> Speaker notes + design rationale for the "Agentic AI for Digital Health" demo.
> The runnable suite lives beside this file. `python run_evals.py` reproduces
> every number quoted below — offline, no API key.

## The one-slide argument

Memory, "dreaming," autonomous tool use — every technique for making an agent
better is a form of **hill-climbing**. None of it is safe, or even meaningful,
without an eval to tell you whether a change went up the hill or off a cliff.
**The eval is the hill.** This is the lesson the ChatGPT-memory post gestures at
and the one most healthcare AI demos skip.

CareConnect is an unusually good teaching case because it is a **hybrid** system,
and evals earn their keep exactly at the seams between the parts:

```
  LLM orchestration  ──►  deterministic tools  ──►  real side effects
  (which tool, what     (rule-based scoring,      (IRIS Interop workflow,
   order, what args)      care planning)            audit trail in MessageHeader)
```

## Five layers of evaluation (→ broadly applicable lessons)

Each layer is a scorer in `careconnect_evals/scorers.py`. Run against the
4-case golden set in `golden_cases.json`, today, with the shipped tools:

| Layer | Scorer | Result on shipped tools | Lesson |
|---|---|---|---|
| **L1 — Deterministic regression** | `score_rule_regression` | **3/4** | Pin the deterministic core with exact-match so the LLM is the only variable |
| **L1b — Spec vs reality** | `score_against_human` | recall **0.75**, precision **1.0** | A passing regression test doesn't mean the spec is *right* — check against ground truth |
| **L2 — Trajectory / tool-use** | `score_trajectory` | 4/4 | In agents you evaluate the **path**, not just the answer |
| **L3 — Outcome / side effect** | `score_outcome` | 4/4 | Build on **auditable** systems — the Interop trace *is* your ground truth |
| **L4 — LLM-as-judge (quality/safety)** | `score_quality` | advisory | Subjective + safety dims need a **judge + rubric**, calibrated to humans |
| **L5 — Cross-case differentiation** | `score_care_plan_differentiation` | **FAIL** | Some defects are only visible across cases, never in one |

### Why two ground truths per case

Every golden case carries **`rule_expected`** (what the shipped tool *should*
output for a given input — a regression target) **and** **`human_label`** (what's
*actually* true for the patient, per a clinician). The gap between them is the
point: L1 can be green while the system is still wrong, because the spec itself
under-calls risk. Conflating "matches spec" with "is correct" is the single most
common evals mistake.

## What the evals actually found (these are real, in this repo)

Running the suite surfaces three concrete defects — none of which the polished
`DEMO.md` walkthrough reveals:

1. **The "deterministic" scorer isn't, end-to-end (L1, adversarial case).**
   `AssessSDoHRisk` keyword-matches on a `clinicalSummary` string *the LLM
   writes*. The `maria-paraphrase-adversarial` case feeds a faithful paraphrase
   of Maria's note ("lost her position," "community pantry," "cannot travel")
   and her priority collapses **URGENT → ROUTINE** — all five domains flip to
   LOW because the keywords ("job," "food bank," "transport") are gone. The
   variance hides in the **seam** between the LLM and the rule. *(Source:
   `SDoHToolSet.cls:149`.)*

2. **The rule has clinical blind spots (L1b, recall 0.75).** James ("skipping
   medications due to cost," subsidized housing) and Sarah ("uninsured," "food
   insecure," "skipping meals") both have genuine Economic-stability risk that
   the rule scores **LOW**, because its lexicon misses how real notes phrase
   hardship. Precision is a perfect 1.0 (it never cries wolf) but recall is
   0.75 — **it misses a quarter of genuine needs, concentrated in one domain.**
   James' overall priority is under-called HIGH when a clinician would say
   URGENT.

3. **The care plans aren't personalized (L5, FAIL).** `DraftCarePlan` branches
   on the *presence of domain names* in the scores string — but those names are
   **always present** in an `AssessSDoHRisk` result. So every patient, of any
   risk profile, receives a **byte-identical** care plan. The demo looks
   tailored; it is not. No single-case eval can see this — only a cross-case
   check. *(Source: `SDoHToolSet.cls:171`.)*

## Closing the loop — the "improve" half

`careconnect_evals/improved.py` contains the fixes the evals justify, and the
notebook + `tests/test_harness.py::test_improvements_close_the_gaps` prove they
move the metrics:

- **Fix #1** broadens the keyword lexicon (`cost`, `uninsured`, `food insecure`,
  `skipping meds`, …). Clinician recall **0.75 → 1.0**; James' priority corrects
  to URGENT. *(The right long-term fix is an LLM extraction step gated by the
  deterministic scorer — but the eval justifies the cheap win first.)*
- **Fix #2** makes `DraftCarePlan` read domain **values** (HIGH) instead of
  names. Care plans now differ when risk profiles differ; L5 passes.

That is the entire discipline in one picture: **define the metric → run it →
read the failures → make the smallest change that moves the number → re-run.**
Evals are the regression suite for behavior, and they gate every prompt or tool
change in CI (`run_evals.py` exits non-zero on any L1/L2/L3 regression).

## The "dreaming" connection

The ChatGPT-memory post's "dreaming" is offline self-improvement: the model
generates and reflects on synthetic experience between sessions. The
prerequisite nobody headlines is an eval harness — *you cannot let a system
rewrite its own behavior unless you can measure whether each rewrite helped.*

L5 + the golden set are the seed of that loop here. The natural next step
(sketched, not built) is **synthetic case generation**: prompt an LLM to invent
new patients with known ground-truth SDoH flags — especially adversarial
paraphrases and edge cases — to grow coverage beyond three hand-written
patients and catch regressions a human would never think to write. The model
helps build its own exam; the harness keeps it honest.

## Provider-agnostic by design

The agent loop, tool schemas, and judge contract are identical across providers
(`careconnect_evals/providers.py`). The suite runs against a deterministic
**mock** (default — no key, instant, CI-friendly), or a real **Claude** or
**OpenAI** agent and judge, selected by one env var. The eval outlives the model
behind it — which is the point of writing it down.

```bash
python run_evals.py                                   # offline mock (default)
CARECONNECT_EVAL_PROVIDER=anthropic ANTHROPIC_API_KEY=… python run_evals.py
CARECONNECT_EVAL_PROVIDER=openai    OPENAI_API_KEY=…    python run_evals.py
```

## Talking points by audience

- **Technical:** the five scorers; two-ground-truths design; the audit trail as
  outcome oracle; CI gating on regression layers; the parity test that keeps the
  offline port honest against live ObjectScript.
- **Clinical / business:** recall 0.75 means 1-in-4 genuine social needs go
  unflagged — and the "personalized" care plan is identical for every patient.
  Evals are how you'd catch that *before* it reaches a community health worker.
- **AI-skeptical:** the failures here are found *by* AI evaluation tooling and
  fixed deterministically. Evals are the accountability layer that makes agentic
  AI defensible in a regulated domain.

## Files

| File | What it is |
|---|---|
| `golden_cases.json` | 4-case golden set; two ground truths per case |
| `careconnect_evals/tools_local.py` | Faithful offline port of the 9 ObjectScript tools |
| `careconnect_evals/providers.py` | Provider-agnostic agent loop + judge (mock/Claude/OpenAI) |
| `careconnect_evals/scorers.py` | The five evaluation layers |
| `careconnect_evals/harness.py` | Load → run → score → report |
| `careconnect_evals/improved.py` | The fixes the evals justify (the "improve" half) |
| `run_evals.py` | CLI entry point + CI gate |
| `notebooks/careconnect_evals_demo.ipynb` | The presentation walkthrough |
| `tests/test_harness.py` | Pins the suite's findings ("who evals the evals") |
| `tests/test_parity.py` | Port vs live IRIS parity (skipped without a stack) |
