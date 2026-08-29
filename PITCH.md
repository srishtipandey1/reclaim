# Reclaim

**Revenue recovery, prioritized — starting exactly where Razorpay's own automation gives up.**

## The pitch (say this close to verbatim to open the video)

> Razorpay's own subscription billing retries a failed payment automatically — four times — then
> gives up completely, even though it keeps billing the customer every cycle after. That's real
> revenue, disappearing silently. Reclaim is the system that starts exactly where Razorpay's
> automation stops.
>
> For every subscription that reaches that give-up point, Reclaim works out why the payment is
> actually failing, picks one safe and bounded way to try to recover it — never more attempts than
> policy allows, never outside business hours — takes the action for real against Razorpay's own
> API, and logs exactly what it did, why, and what happened. It's not a chatbot that talks about
> payments. It's a system that takes one real, limited action and can show you the receipts for
> every one of them.
>
> It's built as the first fully-working piece of something bigger: right now, if a business hires
> separate point-agents for subscriptions, disputes, and returns, nothing tells them which one to
> actually fix first when cash is tight this week. Reclaim is that layer — subscription recovery is
> the module proven end to end.
>
> In testing, it recovered **[X]%** of at-risk revenue across a **[N]**-subscription batch, with a
> **[0]%** unsafe-action rate — it never once took an action outside its own limits.

Fill in the bracketed numbers from the real Prompt 6 output. Do not estimate them ahead of time.

## Switching altitude — what to expand on when someone leans in

**Non-technical follow-up** → go deeper on money and guardrails: the recovered-value number, the
fact it structurally cannot exceed its own limits, that every action is logged and explainable in
plain language, the contact-hour policy borrowed from RBI's own recovery-conduct rules.

**Technical follow-up** → go deeper on architecture: the model only ever recommends, a separate
deterministic policy engine decides, malformed model output is rejected outright rather than
interpreted, the evaluation set was frozen before any policy tuning happened, low-confidence
classifications auto-escalate to a human queue instead of guessing.

Same pitch either way — only the second layer changes, because both halves are true.

## Positioning against Razorpay's own Agent Studio / Agentic Payments (if asked)

Razorpay's Agentic Payments platform is real and verified: UPI Reserve Pay live, UPI Circle coming,
40+ MCP APIs, built with NPCI, Vodafone Idea, and bigbasket as named partners. If Agent Studio's
marketplace includes a point-agent for subscription recovery, the honest answer is: a marketplace of
independently-hired point-agents cannot, by construction, tell a business which of five problems to
fix first when cash position is actually at risk this week. That requires a layer above the
marketplace with cross-domain visibility and one shared guardrail standard — that's what Reclaim is
built as, with subscription recovery as the first fully-implemented, fully-evaluated domain, and one
proof-of-generalization stub domain showing the architecture isn't a one-off.

## Demo production checklist

- Record five short clips, not one continuous take: hook, architecture, two live cases (one
  recovered, one escalated), batch metrics reveal, close.
- Walk the "live case" segment through already-executed `run_eval.py` output, not a live API call —
  identically honest, zero live-failure risk on camera.
- Bump the terminal font size up before recording; default sizes rarely read back clearly on video.
- Close all notifications. Clean desktop. Pre-load everything before hitting record.
- Rehearse out loud, stopwatch running, at least twice before recording anything.
- Simple hard cuts between clips. A two-second title card — "Reclaim" plus the tagline — is worth
  making. Further editing polish is not worth the remaining time.
- Target finishing the recording on the day already budgeted for it, with a day of buffer left
  before submission, not exactly at the deadline.
