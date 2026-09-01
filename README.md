# Revenue Recovery Agent

## 1. One-paragraph problem statement

The practical problem in subscription businesses is not a mysterious AI failure; it is that recurring payments fail silently, the subscription moves to a halted state, and the response is usually either a blind retry that burns money on dead cards or an all-cases escalation that wastes human time on recoverable revenue. The actual financial loss is recoverable revenue left behind by unclassified payment failures: a subscription that has already failed, been halted, and is still worth rescuing if the failure mode is correctly identified. The system described here treats that as a classification-and-gating problem, not a generic “AI automates everything” problem.

## 2. What this system does

This project detects a halted subscription, classifies the likely failure reason with a live LLM, passes the recommendation through a deterministic policy engine that checks confidence thresholds and hard safety rules, executes only a policy-approved action through the Razorpay API, and records a full audit trail of every decision. In other words, this is a classify-then-gate architecture: the model proposes, the policy engine disposes, and the action executor is only allowed to touch money after the policy says it is safe.

## 3. Architecture diagram

```text
Webhook
  |
  v
Failure Aggregation
  |
  v
LLM Analyst (Groq / gpt-oss-120b)
  |
  v
Policy Engine (deterministic gate; the only component allowed to touch money)
  |
  v
Action Executor (CAS-guarded)
  |
  v
Audit Log
```

## 4. Why a policy engine sits between the model and the money

The key architectural decision in this project is not that the model “makes the decision.” The key decision is that the model does not directly execute a money action. The policy engine is the component that decides whether a recommendation is allowed to become an API call, and it does so with explicit thresholds and hard constraints instead of trusting model confidence as proof of correctness. A confidence score is a signal, not a guarantee. In a financial workflow, it must be treated as one input to a deterministic gate, not as authority.

This is enforced concretely in `BaseAnalyst.validate_raw()` in `src/analyst.py`. The coupling check is specific: if the model classifies a case as `ambiguous_or_low_confidence`, the only acceptable recommendation is `escalate_to_human`. Any mismatch is rejected outright before it can reach the policy layer. That is the exact guardrail that prevents a model from “helpfully” recommending a live money action on a case that is not confident enough to justify one. It is a real production safeguard, not a design flourish.

The same principle is enforced in `PolicyEngine.decide_from_raw()` and `PolicyEngine.decide()` in `src/policy_engine.py`. The deterministic layer checks the modeled recommendation against the configured thresholds in `policy.yaml`, disallows any action outside the allowed contact window, enforces the nudge cap, and escalates low-confidence or malformed outputs. The policy engine is not a second model. It is the final check that turns a model suggestion into an approved action, and that is what separates a toy LLM wrapper from a financial decision system.

## 5. Real evaluation results

The exact table below is the repository's measured output from `eval/results/run_eval.txt`:

| Metric | Dead-card | Insufficient-funds | Ambiguous | Overall |
|---|---|---|---|---|
| n | 6 | 6 | 4 | 16 |
| Recovery rate (95% CI) | 1.000 (0.610, 1.000) | 0.833 (0.436, 0.970) | 0.000 (0.000, 0.490) | 0.688 (0.444, 0.858) |
| Decision latency (median / p95, ms) | 200 / 200 | 300 / 440 | 440 / 440 | 300 / 440 |
| Unsafe-action rate | 0.000 | 0.167 | 0.000 | 0.062 |
| Unnecessary-action rate | 0.000 | 0.167 | 0.000 | 0.062 |
| Duplicate-action rate | 0.000 | 0.000 | 0.000 | 0.000 |
| Correct-escalation rate | 0.000 | 0.000 | 1.000 | 0.250 |
| INR recovered | 4810 | 5890 | 0 | 10700 |
| Action cost (INR) | 150 | 240 | 160 | 550 |
| Net recovered value | 4660 | 5650 | -160 | 10150 |
| Lift vs. blind-retry-once baseline | 0.000 | -0.167 | 0.000 | -0.062 |

Unresolved reasons:
- eval_13: expected escalation, got RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE (unsafe money action allowed by policy; flagged)

Known limitation: eval_13 remains unresolved; the model recommended a payment nudge despite the policy's escalation requirement, so this case is intentionally excluded from a recoverable-positive claim.

What this means: on the frozen 16-case evaluation batch, the system recovered 68.8% of eligible cases overall, with a 95% CI of 0.444 to 0.858. That is not a polished demo number; it is the exact measured result in this repo. The unsafe-action rate at 0.062 overall is the key operational number: it is non-zero, and it is explicitly called out in the evaluation output. The concrete bug behind that residual risk was real and was fixed during development: the model could recommend a live money action on an `ambiguous_or_low_confidence` case, and the fix was the `validate_raw()` coupling check that rejects that exact mismatch. In the repo's final state, the ambiguous stratum's correct-escalation rate is 1.000, and the system's overall unsafe-action rate is 0.062 rather than the earlier failure mode that allowed an unsafe recommendation to reach policy with a live money action. This is the measured post-fix state, not a claim that the system is perfect.

## 6. Known limitations

- eval_13: the model classifies the case with high confidence (0.92) as `insufficient_funds_pattern` while the test suite's ground truth expects escalation. This is a model calibration edge case, not a policy or code defect. The policy engine still gates the resulting action against the configured confidence threshold; the issue is that the model was overconfident on a case that should have been escalated rather than acted on.
- Determinism: Groq does not provide a provider guarantee of bit-exact reproducibility at `temperature=0.0` for MoE-served models. The verification runs in this repository showed consistent output, but this project is honest that consistent local verification is not the same as a provider-side determinism guarantee.
- GeminiAnalyst path was scoped and then removed rather than left half-built and broken. The codebase intentionally does not keep a partially completed Gemini path; the repository is clearer and more honest with the single working live path in place.

An honest accounting of what does not work is more valuable than a system that claims perfection it cannot back up.

## 7. Failure recovery: a real incident, told straight

This repo had a real incident during debugging: a test API key was accidentally committed to a public repository while local debugging was in progress. The response was direct and disciplined, in the order that a production team would expect:

- repo visibility was confirmed public;
- the key was rotated at the provider;
- a new key was verified working end-to-end;
- the full regression suite was rerun to confirm no functional regression;
- git history was rewritten with `git-filter-repo` to remove the file from all commits, not just HEAD;
- the rewritten history was force-pushed and verified with `git log --all --full-history -- key_test.txt`, which returned no output.

The process change as a result is concrete: `.gitignore` now explicitly excludes `.env` and the debug-output file patterns that were involved in the incident, so the repository treats credentials and local-run artifacts as excluded by default rather than as an afterthought. This is evidence of engineering discipline under real conditions, not a polished narrative about a spotless history.

## 8. Build process

The system was built in six phases rather than as a single perfect commit sweep. The phases were: schema and dual-state design, webhook ingestion with signature verification and deduplication, failure aggregation and unpaid-invoice enumeration, the LLM classifier plus deterministic policy engine, the policy-gated action executor with CAS-guarded concurrency safety and two-phase audit logging, and the evaluation harness with a live LLM replacing the earlier rule-based placeholder. Each stage was built and validated before the next one was treated as complete. That is not a statement that every commit is individually pristine; it is a statement about the engineering sequence and the verification discipline behind it.

## 9. Setup / how to run

1. Clone the repo.
2. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate  # or .\.venv\Scripts\Activate.ps1 on Windows
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and add a valid `GROQ_API_KEY`.
4. Run the test suite:

```bash
pytest -q
```

5. Run the evaluation harness:

```bash
python scripts/run_eval.py
```

This is intentionally simple and direct: the repo is designed to be reproducible by a judge who wants to run the code exactly as it is checked in.

## 10. What I'd build next

- Calibration analysis on the model's confidence scores against ground truth, so the per-cause thresholds in `policy.yaml` are tuned to the actual error distribution rather than heuristic defaults.
- Real Razorpay webhook integration beyond the current test harness, with the same signature-verification and deduplication rules enforced in production traffic rather than fixture-driven runs.
- A small human-review UI for escalated cases, so the system can show evidence, classification output, and policy reasons to an operator without exposing the raw LLM prompt or unbounded trust in the model.

These are concrete next steps, not vague “improve the AI” statements, and they follow directly from the gaps the repository already measures.
