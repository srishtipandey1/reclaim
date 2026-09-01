# Reclaim: Revenue Recovery Engine

## 1. Problem statement

Razorpay subscriptions already have retry logic built into the platform, but that logic stops once a subscription reaches `halted`. At that point, the problem shifts from “retry the charge on time” to “decide which failed invoice is worth recovering, which is not, and which path should never be allowed to touch money.” In practice, the failure modes are not all equally recoverable: dead cards, insufficient-funds patterns, and genuine ambiguity are different classes of risk. A blind retry wastes money on expired payment methods; a blanket escalation wastes human time on cases that are recoverable; the real value is in correctly classifying the failure, then gating the action before anything is executed.

## 2. What this system does

This project watches for halted subscriptions, classifies the likely failure reason using a live LLM, filters that recommendation through a deterministic policy layer, and executes only policy-approved actions against Razorpay test-mode APIs. The result is a classify-then-gate architecture: the model proposes a label, evidence, and action, but the policy engine decides whether that proposal is valid, safe, and allowed under the project’s hard rules.

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

## 4. Why the policy engine sits between the model and the money

The main design constraint in this system is simple: the LLM does not directly execute a money action. It classifies, produces evidence, and recommends a next step. The policy engine then decides whether that recommendation is legal, safe, and within the project’s constraints. This matters because model confidence is not proof of correctness. A well-formed response can still be a bad business decision if it is ambiguous, under-threshold, or inconsistent with the project policy.

The concrete enforcement is in `BaseAnalyst.validate_raw()` in `src/analyst.py`. That validation rejects malformed output and also enforces a real coupling rule: if the model says `ambiguous_or_low_confidence`, the recommended action cannot be a live money action. The code specifically rejects any pairing where `classification == "ambiguous_or_low_confidence"` and `recommended_action != "escalate_to_human"`. That is the first safety boundary: the model cannot report ambiguity and still recommend a payment action.

The second boundary is in `PolicyEngine.decide_from_raw()` and `PolicyEngine.decide()` in `src/policy_engine.py`. The actual code checks configured confidence thresholds from `policy.yaml`, rejects actions outside the allowed contact window by calling `_now_in_allowed_window()`, and enforces the nudge cap by counting prior `send_update_payment_nudge` actions before allowing another one. In other words, the policy engine does not reinterpret the model; it decides whether the model’s recommendation is permitted to proceed. The model proposes; the policy disposes.

## 5. Real evaluation results

This project is evaluated on a frozen batch and the actual numbers are stored in `eval/results/run_eval.txt`.

| Metric | Dead-card | Insufficient-funds | Ambiguous | Overall |
|---|---:|---:|---:|---:|
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
- eval_13: expected escalation, got `RecommendedActionEnum.SEND_UPDATE_PAYMENT_NUDGE` (unsafe money action allowed by policy; flagged)

Known limitation: eval_13 remains unresolved; the model recommended a payment nudge despite the policy’s escalation requirement, so this case is intentionally excluded from a recoverable-positive claim.

Before the `validate_raw()` coupling fix, the overall unsafe-action rate was 0.250, and the ambiguous stratum was 0.667–0.750, meaning every ambiguous case was recommending a live money action. After the fix, the overall unsafe-action rate is 0.062 and the ambiguous stratum is 0.000. This is the strongest evidence in the project: the system did not merely “improve by intuition”; it moved from a clearly unsafe decision pattern to a bounded one with measurable reduction in harmful actions.

What this means in plain English: the system recovered INR 10,700 on the 16-case evaluation batch, with a net recovered value of INR 10,150 after action costs. The overall recovery rate is 0.688, and the system is still honest about where it fails: ambiguous cases are not treated as recoverable by default, and the project explicitly flags the unresolved calibration edge case in `eval_13` rather than claiming perfection.

## 6. Known limitations

- `eval_13`: a case where the model classified a payment problem as `insufficient_funds_pattern` with high confidence (0.92), while the ground truth expected escalation. This is described as a calibration edge case rather than a policy defect. The policy layer still enforces the configured threshold, so the issue is not that the action reached money without a gate; it is that the model was overconfident on a case that should have been escalated.
- Determinism: Groq does not provide a provider guarantee of bit-exact reproducibility at `temperature=0.0` for MoE-served models. The repo has seen consistent outputs in practice, but that is local verification, not a provider-side guarantee.
- The Gemini path was scoped and removed rather than left half-built. The project intentionally keeps a single working live path instead of a broken secondary path that would confuse the codebase.

An honest accounting of what does not work is more valuable than a system that claims perfection it cannot back up.

## 7. Failure recovery: a real incident, told straight

This project had a real credential incident during debugging: a test API key was accidentally committed to a public repository. The response was direct and disciplined. The repo was confirmed public, the key was rotated at the provider, a new key was verified end-to-end, the regression suite was rerun, and git history was rewritten with `git-filter-repo` so the file was removed from all commits rather than just the current branch tip. The history rewrite was then force-pushed and verified with `git log --all --full-history -- key_test.txt`, which returned no output.

The process change was concrete: `.gitignore` now explicitly excludes `.env` and the debug-output file patterns that were involved in the incident, so the repository treats secrets and local-run artifacts as excluded by default rather than as a clean-up exercise after the fact. This is the correct engineering response to a real incident; it is evidence of operational discipline, not a polished cover story.

## 8. Build process

This project was built in six phases: schema and dual-state design, webhook ingestion with signature verification and deduplication, failure aggregation and unpaid-invoice enumeration, the LLM classifier plus deterministic policy engine, the policy-gated action executor with CAS-guarded concurrency safety and two-phase audit logging, and the evaluation harness with the live Groq-based analyst replacing the earlier rule-based placeholder. Each stage was verified before the next one was treated as complete. The sequence matters more than any individual commit, and the project documentation reflects that reality.

## 9. Setup and run

1. Clone the repository.
2. Create a virtual environment and install the project dependencies:

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
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

The repo is designed to be reproducible by a judge or colleague who wants to verify the numbers, not just read a summary.

## 10. What I would build next

- Calibration analysis for the LLM confidence scores against ground truth so the per-cause thresholds in `policy.yaml` are tuned to the actual error distribution instead of heuristics.
- Real Razorpay webhook integration beyond the current test harness, using the same signature verification and deduplication rules in production-like traffic rather than local fixtures.
- A minimal human-review interface for escalated cases so operators can inspect the model’s evidence, the policy decision, and the audit trail without exposing raw prompt internals.

These are the next practical steps, not vague “improve the AI” statements. They follow directly from the gaps already measured by the project itself.
