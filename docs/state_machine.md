# State Machines

This project keeps two independent state domains for every subscription:

1. `razorpay_state` reflects Razorpay's actual subscription lifecycle as seen from verified webhook events.
2. `case_state` reflects the internal recovery workflow managed by this agent.

The two state machines must never be conflated into one chain.

## Razorpay state machine

Allowed values:

- `created`
- `authenticated`
- `active`
- `pending`
- `halted`
- `cancelled`
- `paused`
- `expired`
- `completed`

Business meaning:

- `created`: plan/subscription created, awaiting customer authentication
- `authenticated`: customer completed auth, subscription is ready to bill
- `active`: subscription is currently billing normally
- `pending`: a charge failed; Razorpay has deferred the next retry
- `halted`: automatic retries were exhausted; no more automatic charging on the saved card
- `cancelled`: subscription was cancelled
- `paused`: subscription was intentionally paused
- `expired`: subscription reached its end condition
- `completed`: subscription lifecycle is complete

Important rule:

- `razorpay_state` is written only by verified webhook processing.
- Application logic must never directly write this field.

## Case state machine

Allowed values:

- `none`
- `analyzing`
- `policy_checked`
- `action_pending`
- `verified`
- `resolved`
- `escalated`

This pipeline is internal to the recovery system:

- `none`: no case has been created yet
- `analyzing`: recovery context is being prepared and classified
- `policy_checked`: the model recommendation has been validated by the policy engine
- `action_pending`: a policy-approved action is queued for execution
- `verified`: the action has executed and the webhook outcome is being reconciled
- `resolved`: the invoice/subscription recovered successfully
- `escalated`: the system rejected the case for human review

Important rule:

- `razorpay_state` and `case_state` evolve independently.
- A subscription can be `active` in Razorpay while the agent is still `analyzing` a recovery case, or vice versa.

## Why this matters

The project must not assume that a change in one state implies a change in the other. A webhook-driven observation of Razorpay's lifecycle is authoritative for one domain, while the recovery case lifecycle lives in the other domain.
