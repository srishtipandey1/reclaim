# AGENTS.md — Reclaim: Razorpay AI Buildathon Revenue Recovery Engine

> Read this entire file before writing, editing, or reviewing any code in this repository.
> This is the single source of truth. If a task prompt ever conflicts with this file, this file wins.
> If you are an AI coding agent (Codex, OpenCode, or any other), your task assignment is in Section 10.

---

## 1. What this project is, and why every decision below exists

This is a submission to the Razorpay AI Buildathon, a student program that doubles as a hiring
funnel for Razorpay's AI Builder Intern role. There is no numeric leaderboard rank — the mechanism
is a signal-based filter into a human panel interview. The deliverable is exactly three artifacts:
a public GitHub repository, a 5-minute pitch video, and an architecture explanation. Nothing else
is graded directly, but everything else (code quality, honesty of results, how failures are
handled) determines whether those three artifacts create signal.

Every track's official grading language converges on the same four demands, independent of track:
quantified results on a batch/held-out set (never a cherry-picked demo), a persisted audit trail,
bounded and gated autonomous actions with explicit stopping rules, and an honest account of what
the system could not resolve. The Revenue Recovery track specifically asks for measured money
recovered across a batch, with compliant escalation, stopping rules, and an audit trail.

Deadline: submissions close September 5. Build must be feature-frozen by September 3, leaving two
days for recording and buffer. Treat every remaining day as scarce. Do not add scope that isn't in
this file or explicitly approved by the human running this project.

## 2. The idea, and the one sentence that is the entire pitch

Razorpay's own platform already retries a failed subscription charge automatically, once a day, up
to four times, before giving up and moving the subscription to `halted`. This system does not
rebuild that automation. It starts exactly where Razorpay's own automation stops. Say this sentence
near-verbatim in the video: it is the strongest "you understood the actual platform, not just the
prompt" signal available in this submission.

Scope, precisely: for every subscription that reaches `halted`, classify why (with a confidence
score, not a hard label), select one bounded recovery action from a fixed policy based on that
classification, execute it for real against Razorpay's test-mode API, verify the outcome from the
resulting webhook, log everything, and stop after a hard-capped number of attempts rather than
retrying indefinitely.

Do not extend this to one-time Orders/Payments failures, UPI Autopay mandates specifically, or
settlement-level reconciliation. Those are real, correct next steps — name them in the README as
future work. Do not build them now.

## 3. Non-negotiable design principles

- **The LLM never directly executes a money action.** It classifies and recommends. A separate,
  deterministic, LLM-free policy engine decides allowed/rejected. Only an approved decision may
  reach the Razorpay API. This is the single most important architectural rule in this project.
- **Malformed or out-of-schema model output is rejected outright, never "interpreted."** A failed
  validation routes straight to human escalation. Do not write code that tries to salvage or
  reinterpret a bad model response.
- **Every subscription has two independent state fields, never one conflated chain**: `razorpay_state`
  (mirrors Razorpay's real lifecycle exactly, written only by verified webhook processing, never by
  application logic) and `case_state` (this agent's own internal pipeline: `new → analyzing →
  policy_checked → action_pending → verified → resolved | escalated`). Razorpay's state can change
  independently of where your pipeline is — do not assume they move in lockstep.
- **Hard stopping rules, enforced at the database level**, not just in application code that a
  future bug could bypass: capped attempts and capped customer nudges per invoice, then mandatory
  human escalation.
- **Customer-facing contact is restricted to 08:00–19:00 IST**, enforced as a runtime check against
  wall-clock time before any nudge is permitted — never something the model is trusted to remember.
  This window is borrowed by design from RBI's Fair Practices Code for recovery-agent contact hours,
  the closest real regulatory analogue in Indian financial services, even though this system is not
  literally a loan-recovery agent. State this distinction honestly if asked — borrowed-by-design,
  not legally mandated for this exact use case.
- **The evaluation set is frozen and never used to tune the policy.** Generate the full scenario
  batch first. Hand-tune policy thresholds against a small, separately-named design subset only.
  Report headline metrics only on the untouched remainder. Violating this order invalidates every
  number this project reports.
- **Every decision is logged twice**: once before execution (classification, confidence, evidence,
  policy result) and once after (action taken, API response, resulting webhook outcome) — so a
  crash mid-execution is still fully auditable.
- **Concurrency-safe by construction**: before executing any action, re-read `case_state`
  immediately beforehand and abort if it has changed since it was last read. Idempotency (event-ID
  deduplication) is not sufficient on its own — a batch re-run and a live webhook can race each
  other.
- **Webhook processing is order-independent.** Razorpay does not guarantee delivery order. Derive
  current state from the full set of events received, never from "whichever arrived most recently."

## 4. Verified Razorpay platform facts — checked directly against live docs, do not override from memory

- Full subscription lifecycle: `created → authenticated → active ⇄ pending → halted →
  (active | cancelled) `, with `paused` and `expired` also valid states outside this main path.
  Treat `paused`/`expired` as valid, out-of-scope states to skip cleanly, not errors.
- A failed charge moves a subscription `active → pending` and fires `subscription.pending`. Each
  failure increments an attempt count and pushes the next automatic retry forward by one day. Four
  consecutive failures exhaust retries and move the subscription to `halted`, firing
  `subscription.halted`. Razorpay then stops automatic charging on the saved card entirely, though
  invoices keep being generated on schedule.
- From `halted`, a manual charge attempt on a specific issued invoice does not count against the
  subscription's automatic retry budget. If the customer supplies a new card, Razorpay auto-charges
  it and moves the subscription back to `active`.
- **Critical, easy to miss**: once a subscription moves from `halted` back to `active`, previous
  unpaid invoices are NOT retroactively re-attempted — only future billing cycles resume
  automatically. If a subscription was halted across multiple cycles, there are multiple unpaid
  invoices, and recovering the subscription's status is not the same as recovering all outstanding
  money. The action executor must enumerate every currently-unpaid invoice for a halted subscription
  and attempt each individually. This directly affects the correctness of the ₹-recovered metric.
- Webhook signature: header `X-Razorpay-Signature`, algorithm HMAC-SHA256, computed over the RAW
  request body using the webhook secret as key. Never parse the body before verifying.
- Idempotency: header `x-razorpay-event-id`, unique per event. Enforce deduplication with a UNIQUE
  database constraint, not just an application-level check.
- Webhook delivery order is not guaranteed by Razorpay. Design accordingly.
- For local development, use `zrok` to tunnel the webhook receiver. Do NOT use ngrok — Razorpay
  explicitly blacklists `ngrok.io` (and `loca.lt`) as a webhook URL domain.
- Setting up a webhook in test mode prompts for an OTP in the dashboard; the default test-mode OTP
  is `754081`.
- Confirmed via Prompt 1's own research: test-mode charge-failure simulation is dashboard-only, not
  scriptable via the REST API or the official Python SDK (verified against the full Subscriptions
  API reference and the SDK source directly). The dashboard's manual test-charge trigger applies
  immediately, not bound to the real once-a-day retry cadence — confirmed directly from Razorpay's
  own Test Subscriptions documentation. Plan creation and Subscription creation remain fully
  API-scriptable regardless.

## 5. Architecture

**Stack**: Python 3.12+, FastAPI, SQLite in WAL mode with explicit CHECK constraints, Pydantic,
the official Razorpay Python SDK, pytest, structured JSON logging.

**Explicitly do NOT introduce**, unless this file is updated first to approve it: PostgreSQL,
Docker, SQLAlchemy, Redis, Kubernetes, Kafka, microservices, LangChain, any vector database, or a
separate Next.js frontend. None of these are justified by this workload (tens of records, single
process, one solo builder, an eight-day clock). Adding them is negative engineering for this
project specifically, regardless of their merit elsewhere.

**Pipeline**: `Webhook received → signature verified → deduplicated → persisted → (on
subscription.halted) failure history aggregated + unpaid invoices enumerated → Analyst classifies
with confidence + evidence (schema-validated, malformed output rejected) → Planner proposes one
action → Policy engine (pure function, config-driven, zero LLM calls inside it) approves or rejects
→ approved action executed with a compare-and-swap state check → outcome verified via the resulting
webhook → full trace logged → stopping rule checked before any further action is permitted.`

**Dashboard**: build last, and build it as a single static HTML page a Python script renders
directly from SQLite. Do not stand up a separate frontend project for this.

## 6. Folder structure

```
razorpay-recovery-agent/
├── AGENTS.md
├── README.md                  (written day 7, human-facing)
├── policy.yaml
├── requirements.txt
├── .env.example
├── docs/
│   ├── state_machine.md       (both state spaces documented separately)
│   └── architecture.md        (diagram, written day 7)
├── src/
│   ├── main.py                 FastAPI entrypoint
│   ├── db.py                   SQLite connection, WAL mode, schema init
│   ├── schema.sql
│   ├── models.py                Pydantic models incl. Analyst output schema
│   ├── razorpay_client.py       SDK wrapper
│   ├── webhooks.py              signature verification, dedup, receiver
│   ├── state_machine.py         dual state transition logic, CHECK-enforced
│   ├── aggregation.py           failure history + unpaid invoice enumeration
│   ├── analyst.py               LLM classification call + schema validation
│   ├── policy_engine.py         pure function, reads policy.yaml, no LLM calls
│   ├── executor.py              action execution, CAS guard, audit log writes
│   └── dashboard.py             static HTML generator (day 7)
├── scripts/
│   ├── seed_subscriptions.py    creates design_set + eval_set, seeded/reproducible
│   └── run_eval.py              one command, regenerates every reported number
├── tests/
│   ├── test_webhooks.py
│   ├── test_policy_engine.py
│   ├── test_state_machine.py
│   └── test_executor.py
├── eval/
│   ├── design_set/              used to tune policy.yaml thresholds only
│   ├── eval_set/                frozen, never used for tuning
│   └── results/                 generated metrics output, one command reproduces this
└── data/
    └── recovery.db              gitignored
```

## 7. Evaluation methodology

Freeze `eval_set` before any policy tuning begins. Tune only against `design_set`. Report headline
numbers only from `eval_set`.

**Two data cohorts, both required, each case labeled with a `data_source` field** (`fixture` or
`live_dashboard`). Razorpay's test-mode charge-failure simulation is dashboard-only, not
API-scriptable. A small cohort of 8-12 subscriptions is created via API and manually driven through
real dashboard-triggered failures to `halted`; the full pipeline runs against these for real —
classification, policy decision, API execution, webhook verification — proving the system works end
to end against live test infrastructure. The larger scenario battery below is fixture-based: failure
history and context constructed directly as realistic local data rather than organically driven
through the dashboard, since that's where the statistical rigor actually lives and constructing
evaluation data this way is standard practice. State this split explicitly in the README.

Scenario battery: 20–30 total.

**Classifier inputs must never include ground-truth label fields.** Every eval case has evidence
fields (what a classifier is allowed to see — reason, amount, and in the full system the
RecoveryContext's failure/payment history) and label fields (archetype, should_recover — used only
to score output after classification runs). A classifier that reads a label field directly isn't
being evaluated, it's being handed the answer. Found the hard way: an early rules-based classifier
checked archetype directly for two of three archetypes, meaning those cases were never actually
classified at all — only the third, where the check didn't short-circuit, forced real reasoning,
and that's precisely where it broke. Keep evidence and label fields in separate objects at
construction time so this can't recur silently. Include the clean, cleanly-classifiable cases (dead/expired card,
insufficient-funds pattern, one-off technical decline, already-manually-attempted, already-resolved,
duplicate webhook, unknown-subscription-ID) AND at least 4–5 deliberately ambiguous cases with
overlapping signals (e.g. a near-expiry card on an account with an intermittent insufficient-funds
pattern). Report that performance is honestly worse on the ambiguous stratum — do not smooth this
over.

Report, on the frozen eval set only, stratified by failure archetype and with a 95% confidence
interval on the headline recovery rate:

| Metric | Dead-card | Insufficient-funds | Ambiguous | Overall |
|---|---|---|---|---|
| n | | | | |
| Recovery rate (95% CI) | | | | |
| Decision latency (median / p95, ms) | | | | |
| Unsafe-action rate | | | | |
| Unnecessary-action rate | | | | |
| Duplicate-action rate | | | | |
| Correct-escalation rate | | | | |
| ₹ recovered | | | | |
| Action cost (₹) | | | | |
| Net recovered value | | | | |
| Lift vs. blind-retry-once baseline | | | | |

Unsafe-action rate is the single most important number in this table and should be 0. A system that
recovers money but occasionally double-charges or acts outside policy is a bad system regardless of
its recovery rate.

`scripts/run_eval.py` must seed all randomness explicitly and regenerate every number in this table
from a single command. If two runs don't produce identical output, something is non-deterministic
and must be fixed before this number goes in the README.

## 8. Anti-slop rules — follow these regardless of which tool you are

- Work one bounded task at a time, exactly as scoped in Section 11. Never expand scope to "while
  I'm at it" additions — new files, new endpoints, new dependencies beyond what a task specifies are
  not your call to make.
- Write tests alongside every task. A task is not done until its tests exist and pass.
- Verify real SDK method names and signatures against the installed package or the official API
  reference before calling them. Do not pattern-match to a plausible-sounding method name — this is
  the most common failure mode in agent-generated code against a real third-party SDK.
- If a task's definition of done cannot be met, stop and report why rather than producing something
  that superficially runs but doesn't actually satisfy it.
- Do not silently work around a failing test by weakening the test.
- After completing a task, state in plain language what you built and why, in two or three
  sentences. If you cannot explain it simply, the implementation is probably more complex than it
  needs to be.

## 9. `policy.yaml` — create this exact file at the project root

```yaml
policy_version: "1.0"
evaluation_set_frozen: true

contact_rules:
  allowed_hours_local: ["08:00", "19:00"]
  timezone: "Asia/Kolkata"
  max_nudges_per_subscription: 2
  min_hours_between_nudges: 48
  channels_covered: ["sms", "email", "whatsapp"]

action_rules:
  - cause: "dead_or_expired_card"
    confidence_threshold: 0.75
    action: "send_update_payment_nudge"
    max_attempts: 1
    fallback: "escalate_to_human"
  - cause: "insufficient_funds_pattern"
    confidence_threshold: 0.70
    action: "schedule_delayed_manual_charge"
    delay_days: 3
    max_attempts: 1
    fallback: "send_update_payment_nudge"
  - cause: "ambiguous_or_low_confidence"
    confidence_threshold: 0.0
    action: "escalate_to_human"
    max_attempts: 0

hard_constraints:
  never_exceed_total_actions_per_invoice: 3
  never_act_outside_allowed_hours: true
  never_skip_audit_log_write: true
```

## 10. Which tool runs what, and how to stay inside free-tier limits

There is no Codex in this setup. **OpenCode is the sole coding agent with repository access** and
owns Sections 5, 6, 9, and all of Section 11's Prompts 1–6, run strictly in order, one at a time. It
does not proceed to the next prompt until the current one's definition of done is met and the human
has reviewed the diff.

**Google AI Studio still does not touch this repository.** Its only role is iterating on the
Analyst's classification prompt and output schema in isolation, against hand-built RecoveryContext
examples, before that prompt is handed to OpenCode for Prompt 4. Its Build mode is not used for this
project — it is specialized toward Android/Kotlin and React app generation, not this stack.

**Confirmed model allocation**, using the Gemini and Groq free-tier access actually available:

| Role | Model | Why |
|---|---|---|
| OpenCode's own driving model | GPT-OSS-120B (Groq) | Strong open-weight reasoning and tool use, fast inference, and a quota completely separate from anything Gemini-based, so the coding agent's high call volume never competes with the Analyst or the AI Studio sandbox. |
| Analyst production calls (Prompt 4 runtime) | Gemini Flash (Flash Latest / 3.5 Flash) | Flash-tier free quotas run meaningfully higher than Pro-tier, and Flash is sufficient for a bounded structured-classification task. Consistent with where the prompt is hardened in AI Studio. |
| AI Studio prompt-hardening (interactive, low-volume) | Gemini 2.5 Pro | Best available reasoning for occasional, human-paced iteration, where Pro's tighter quota isn't a bottleneck because usage is occasional, not batch. |
| One-time model-comparison check (Section 12) | Llama 3.3 70B (Groq) | A third, genuinely independent lineage from both Gemini (Analyst) and GPT-OSS (OpenCode) — real diversity, not the same family twice. |
| Independent review pass before Day 8 freeze | Llama 3.3 70B or Qwen3.6 27B (Groq), fresh session | A different model actually reading the code, not the builder re-reading its own work. |
| RAG Tier-2 embeddings, if built | Gemini Embedding 2 | Purpose-built, directly available. |
| Defense-in-depth on any free-text fields (see note below) | Llama Prompt Guard 2, 22M (Groq) | Purpose-built prompt-injection classifier, negligible latency/quota cost. |

Everything else in the available model list — Veo, Nano Banana, Lyria, Deep Research, Computer Use,
Robotics-ER, the TTS and Whisper variants, ALLaM, Orpheus — is media generation, voice, or an
unrelated agentic product. None of it is relevant to this project. Ignore it.

**A guardrail this access makes cheap to add**: if `aggregation.py` (Prompt 3) ever pulls a Razorpay
`notes` field or any other merchant- or customer-editable free-text field into the RecoveryContext,
run that text through Llama Prompt Guard 2 before it reaches the Analyst, and strip or flag anything
classified as an injection attempt. `notes` fields are exactly the kind of semi-external text an
attacker could use to try to influence a money decision through the prompt rather than the actual
payment data. If the aggregation never includes free text at all, skip this and say so in the
README rather than adding an unused defense.

**Free-tier rate limits, updated**: Gemini's free tier runs roughly 5–15 requests per minute with a
daily cap that varies by model and tier, tighter on Pro than on Flash. Groq has historically offered
materially more generous free limits, though there is no verified current 2026 figure here — check
the actual number in the Groq console before relying on it for the full batch in Prompt 6. The
stub-first approach in Prompt 4 (build the Analyst behind a hardcoded stub before wiring in the real
call) is still worth keeping regardless — it's good practice independent of how comfortable the
quota turns out to be.

**On independent review**: this is now concretely achievable, not a fallback. The frozen design/eval
split in Section 7 still depends on the human not exposing `eval_set` contents during Prompts 4–5,
not on tool diversity — that was never at risk. What confirmed Groq access restores is genuine
model-diverse code review: run the final pass in a fresh OpenCode session configured with Llama 3.3
70B or Qwen3.6 27B, not the same GPT-OSS session that built everything.

## 11. The six build prompts

### Prompt 1 — Lifecycle proof + skeleton
```
Before writing application code, verify whether Razorpay's Subscriptions API lets
me script the create → authenticate → simulate-charge-failure → halted flow
programmatically, or whether the failure-outcome simulation is dashboard-only.
Check the Subscriptions API reference directly and report back what you find
before proceeding — do not assume.

Then scaffold the project exactly per AGENTS.md Section 6 (folder structure) and
Section 5 (stack — Python, FastAPI, SQLite WAL, Pydantic, the official Razorpay
SDK, pytest, no Postgres/Docker/Redis). Read RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET
/ RAZORPAY_WEBHOOK_SECRET from environment variables.

Implement src/schema.sql with two separate state columns on subscriptions:
razorpay_state (CHECK constraint restricting to: created, authenticated, active,
pending, halted, cancelled, paused, expired, completed) and case_state (CHECK
constraint restricting to: none, analyzing, policy_checked, action_pending,
verified, resolved, escalated). razorpay_state may only be written by verified
webhook processing.

Write docs/state_machine.md documenting both state spaces separately per AGENTS.md
Section 3 — they are independent and must never be conflated into one chain.

Definition of done: schema created with constraints enforced (attempt an invalid
state value and confirm the DB rejects it), and your report on API-vs-dashboard
scriptability of test failures.
```

### Prompt 2 — Webhook layer
```
Implement POST /webhooks/razorpay per AGENTS.md Section 4 exactly:
1. Read the raw request body before any parsing.
2. Verify X-Razorpay-Signature using HMAC-SHA256 over the raw body with the
   webhook secret as key. Reject with 400 on mismatch. Never parse before
   verifying.
3. Deduplicate using x-razorpay-event-id, enforced by a UNIQUE constraint on that
   column in webhook_events.
4. Return 2xx immediately, then hand the event to a background task — no
   expensive work inline in the request handler.
5. Design processing to be order-independent per AGENTS.md Section 3 — derive
   current razorpay_state from the full set of events received, never from "the
   last one that arrived."
6. Use zrok, not ngrok, to expose this locally. Note the test-mode dashboard OTP
   is 754081 when registering the webhook URL.

Definition of done: a duplicate event delivered twice produces one row; an
out-of-order pair resolves to the correct final state; an invalid signature is
rejected with the raw body logged.
```

### Prompt 3 — Failure aggregation + invoice enumeration
```
On any transition to razorpay_state = halted, implement:
1. A function pulling the full webhook/invoice history for that subscription and
   enumerating every currently-unpaid invoice — not just the most recent. Per
   AGENTS.md Section 4: recovering a subscription to active does not retroactively
   collect older unpaid invoices, so each needs its own recovery decision.
2. The RecoveryContext object (bounded size) — subscription summary, the specific
   invoice under consideration, payment_history, failure_history, prior
   recovery_actions for this subscription, and policy_limits from policy.yaml.

Definition of done: a subscription with 2+ unpaid invoices returns all of them
individually, each ready to become its own RecoveryContext.
```

### Prompt 4 — Analyst/Planner + policy engine
```
1. Implement the Analyst behind a clear interface, in two steps. First, a
   hardcoded stub implementation returning a fixed classification — wire the
   policy engine against this stub and validate all five test cases below at
   zero real model-call cost. Only once that's solid, implement the real call:
   given a RecoveryContext, call the LLM with a strict Pydantic schema —
   classification (enum), confidence (0-1), evidence (list of strings),
   recommended_action (enum). On schema validation failure, do not repair or
   reinterpret — reject and route to escalated, per AGENTS.md Section 3. Respect
   free-tier rate limits when testing the real call: space requests out, don't
   loop rapidly.
   [If a hardened prompt was developed in Google AI Studio per Section 10, use
   that exact prompt text here rather than writing a new one from scratch.]
2. Implement the policy engine as a pure function with zero LLM calls inside it,
   reading policy.yaml, returning allowed/rejected given: recommended action,
   current case_state, prior actions on this invoice, and current wall-clock time
   against allowed_hours_local. Confidence below the configured threshold routes
   to escalated regardless of the model's recommendation.
3. Create policy.yaml exactly as specified in AGENTS.md Section 9.

Definition of done: five hand-constructed test cases — one per action type plus
one deliberately malformed model response — each produce the correct
allowed/rejected/escalated result, with no LLM call occurring inside the policy
function itself.
```

### Prompt 5 — Action executor + audit + concurrency safety
```
1. Only a policy-approved action may call the Razorpay API. Nothing else may.
2. Before executing, re-read case_state for that invoice and abort if it changed
   since last read (compare-and-swap) — prevents two concurrent triggers acting
   on the same invoice.
3. Write to agent_decisions before execution (classification, confidence,
   evidence, policy result) and again after (action taken, API response,
   resulting webhook outcome).
4. Enforce the stopping rule (max_nudges_per_subscription, max_attempts from
   policy.yaml) as a database-level check against recovery_actions for that
   invoice, not application logic alone.

Definition of done: triggering the same action twice near-simultaneously results
in exactly one execution and one clean abort, both logged.
```

### Prompt 6 — Evaluation harness (ideally in a fresh session per Section 10)
```
1. Build 20-30 scenarios as seed data per AGENTS.md Section 7: split into a
   design set (8-10, used to tune policy.yaml) and a frozen evaluation set (the
   rest, untouched during tuning). Include the clean cases plus 4-5 deliberately
   ambiguous ones with overlapping signals.
2. Seed all randomness with a fixed seed; the batch and every result must be
   exactly reproducible from scripts/run_eval.py. Space Analyst calls out with a
   short delay rather than firing them concurrently, to respect free-tier rate
   limits — run the full batch deliberately once the classifier is stable, not
   repeatedly while debugging.
3. Compute, on the evaluation set only: recovery rate with 95% Wilson confidence
   interval stratified by archetype; median and p95 decision latency (wall-clock
   from webhook received to decision logged); unsafe-action rate;
   unnecessary-action rate; duplicate-action rate; correct-escalation rate; ₹
   recovered; net recovered value after a stated per-action cost; and lift
   against a naive blind-retry-once baseline computed on the same set.
4. Output results in exactly the table shape in AGENTS.md Section 7.
5. Optional, only if the design-set Analyst prompt is already finalized: run the
   same prompt and schema once against a second model on the design set only —
   never the eval set — and report the agreement rate plus one honest line on
   where the two models diverged.

Definition of done: run_eval.py run twice produces byte-identical output, and
every unresolved case in the eval set has a logged reason, not a silent drop.
```

## 12. How this maps to what the AI Builder role actually asks for

The role's own language (careers page, job description) asks for one person to decompose a
business problem from first principles, design and build the full system, ship it to production
and own the outcome, and switch altitude between technical depth and business/stakeholder framing —
explicitly naming fine-tuning, RAG, eval, guardrails, hallucinations, tokenization, latency,
orchestration, and comparing models as areas of expected fluency. This project already demonstrates
most of this. What's listed here is what changed as a result, so nothing gets built or skipped by
accident.

**Already strong, no change needed:** eval (Section 7's full metric taxonomy and frozen split),
guardrails (the policy engine and hard stopping rules), hallucination-handling (schema validation
with reject-not-repair, and the LLM-never-executes-money rule), orchestration (the Analyst → Planner
→ Policy pipeline).

**Added, because it's cheap and genuine:** decision latency is now instrumented and reported
(Section 7, Prompt 6). A one-time model-comparison run against a second model on the design set only
is now part of Prompt 6, optional and design-time only — it must never touch the frozen eval set.

**Deliberately not built — the README must say so explicitly, not stay silent:** fine-tuning. There
is no dataset here large enough to fine-tune responsibly in this window, and a prompt-plus-schema
approach is more auditable for a financial decision than a fine-tuned model would be at this stage.
State this as a reasoned rejection in the README, with "fine-tune once real production volume
accumulates labeled outcomes" as the named future-work line.

**Optional, Tier 2, only if Day 6 finishes on schedule:** retrieval of the 2-3 most similar
previously-logged cases from `agent_decisions` as few-shot grounding context for the Analyst when it
classifies a new halted subscription — a motivated extension of logging every outcome, not a
bolted-on feature. Do not attempt this before Prompts 1-5 are solid.

**README and video requirement, not a code requirement:** one explicit build-vs-buy-vs-defer
paragraph, surfacing decisions already made through this project — reusing Razorpay's own retry
automation instead of rebuilding it, choosing prompting over fine-tuning, deferring one-time-payment
recovery and settlement-level reconciliation to future work. One explicit paragraph translating the
headline metrics into the language a CFO or Head of Finance would want, not engineering language —
this is the "switch altitude" signal the role names directly, and it costs a paragraph, not a
feature.

## 13. Positioning against Razorpay's own Agent Studio / Agentic Payments platform

Verified directly from razorpay.com/agentic-payments/: UPI Reserve Pay is live (consent-based,
pre-authorized agent payments within approved spending limits), UPI Circle is coming soon
(delegated/shared authorizations), and there are 40+ AI-ready MCP APIs, full-stack payment methods,
and PCI DSS Level 1 compliance, publicly partnered with NPCI, Vodafone Idea, and bigbasket. Razorpay
is also reported (not independently confirmed by this project, treat as likely but unverified) to run
"Agent Studio," a marketplace of purpose-built agents including one named for subscription recovery.

This does not invalidate the project. It changes the pitch. Do not claim "nobody has built subscription
recovery at Razorpay" — that claim is unverifiable and risky if wrong. The defensible claim is
narrower and true regardless: a marketplace of independently-hired point-agents (Subscription
Recovery, Dispute Responder, RTO Shield, Cashflow Forecaster, etc., each solving one problem) cannot,
by construction, answer which lever to pull first across domains when cash position is actually at
risk — that requires a layer above the marketplace with cross-domain visibility and one shared
guardrail standard. This project is built as that layer, with the halted-subscription engine as its
first fully-implemented, fully-evaluated domain.

Concrete, scoped addition to make this real rather than a README claim:
- A `RecoveryDomain` interface (`detect_candidates()`, `build_context()`, `classify()`) that the
  existing subscription engine implements without changing its internals.
- A thin `Orchestrator` that ranks at-risk value across every registered domain.
- One toy second domain — explicitly labeled in code and the README as a proof-of-generalization
  stub, backed by 5-10 fixture records, not a fully evaluated system — to prove the abstraction
  actually works with running code.

This is roughly half a day of work on top of the existing build, not a second project. It does not
change the track (still Revenue Recovery), does not change Prompts 1-6, and does not add real
coverage of disputes, RTO, or cashflow forecasting — those remain named future work, not built
systems. If time is short, skip the stub domain entirely and keep the `RecoveryDomain` interface
as the only addition; the interface alone is enough to make the architecture claim honest.