# Reclaim architecture

Reclaim starts when Razorpay's own subscription retries have exhausted and a subscription reaches `halted`.

```mermaid
flowchart TD
    A[Verified Razorpay webhook] --> B[Persist and deduplicate]
    B --> C[Aggregate failures and unpaid invoices]
    C --> D[Analyst: classify and recommend]
    D --> E[Schema validation]
    E --> F[Deterministic policy engine]
    F --> G[CAS-guarded executor]
    G --> H[Razorpay test-mode API]
    H --> I[Webhook outcome and audit log]
```

`razorpay_state` is written from verified webhook events. `case_state` tracks this agent's pipeline independently. The LLM can propose a classification and action, but only the policy engine can approve an action and the executor rechecks state immediately before dispatch.
