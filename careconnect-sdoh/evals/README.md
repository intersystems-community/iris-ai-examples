# CareConnect SDoH — Agent Evals

A small, **provider-agnostic, runs-offline** evaluation suite for the
careconnect-sdoh agent. Built to demonstrate the broadly applicable lessons of
evaluating agentic AI in a digital-health setting.

> **Read [`EVALS.md`](./EVALS.md) for the why** — the five evaluation layers,
> the three real defects this suite finds in the shipped tools, and the
> measure → fix → re-measure loop. This README is just how to run it.

## Quickstart (no API key, no Docker)

```bash
cd careconnect-sdoh/evals
python run_evals.py
```

The default `mock` provider runs a scripted agent against an in-process port of
the tools, so the whole suite — including the failure-detection demos — runs
instantly and deterministically. Expected headline:

```
L1_rule_regression     3/4      ← adversarial paraphrase flips URGENT→ROUTINE
L2_trajectory          4/4
L3_outcome             4/4
L5 differentiation     FAIL     ← every patient gets an identical care plan
clinician recall       0.75     ← rule misses 1-in-4 genuine needs (precision 1.0)
```

`run_evals.py` exits non-zero when a regression-style layer (L1/L2/L3) fails, so
it drops straight into CI as a gate on prompt/tool changes.

## Run against a real model

The agent loop and the LLM-as-judge are provider-agnostic — pick one with an env
var:

```bash
CARECONNECT_EVAL_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-ant-…  python run_evals.py
CARECONNECT_EVAL_PROVIDER=openai    OPENAI_API_KEY=sk-…          python run_evals.py
```

Optional overrides: `CARECONNECT_EVAL_MODEL`, `CARECONNECT_EVAL_JUDGE_MODEL`.
Install the provider SDK you need from `requirements.txt`.

## The presentation walkthrough

```bash
pip install -r requirements.txt
jupyter notebook notebooks/careconnect_evals_demo.ipynb
```

The notebook walks the five layers one at a time, charts the results, surfaces
the three defects, then applies the proposed fixes and shows the metrics move.

## Tests

```bash
pip install pytest
pytest                          # offline; pins the suite's findings
IRIS_HOST=localhost pytest tests/test_parity.py   # port vs live IRIS (needs stack)
```

## Layout

```
evals/
├── EVALS.md                       the lessons / speaker notes (start here)
├── golden_cases.json              4-case golden set, two ground truths each
├── run_evals.py                   CLI + CI gate
├── careconnect_evals/
│   ├── tools_local.py             faithful offline port of the 9 tools
│   ├── providers.py               mock / Claude / OpenAI agent loop + judge
│   ├── scorers.py                 the five evaluation layers
│   ├── harness.py                 load → run → score → report
│   └── improved.py                the fixes the evals justify
├── notebooks/careconnect_evals_demo.ipynb
└── tests/                         test_harness.py, test_parity.py
```
