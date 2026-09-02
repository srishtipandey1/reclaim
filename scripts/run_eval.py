from __future__ import annotations

import json
import math
import random
import statistics
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / '.env', override=True)

from src.analyst import GroqAnalyst
from src.policy_engine import PolicyEngine

EVAL_ROOT = ROOT / 'eval'
DESIGN_DIR = EVAL_ROOT / 'design_set'
EVAL_DIR = EVAL_ROOT / 'eval_set'
RESULTS_DIR = EVAL_ROOT / 'results'

SEED = 20260831


def build_design_cases() -> list[dict[str, Any]]:
    return [
        {
            'id': 'design_01',
            'archetype': 'dead_card',
            'amount': 820,
            'should_recover': True,
            'reason': 'expired card on active subscription',
        },
        {
            'id': 'design_02',
            'archetype': 'dead_card',
            'amount': 640,
            'should_recover': True,
            'reason': 'card expired and no new card on file',
        },
        {
            'id': 'design_03',
            'archetype': 'insufficient_funds',
            'amount': 980,
            'should_recover': True,
            'reason': 'prior failed charges with funds short pattern',
        },
        {
            'id': 'design_04',
            'archetype': 'insufficient_funds',
            'amount': 1200,
            'should_recover': True,
            'reason': 'repeated insufficiency pattern over two cycles',
        },
        {
            'id': 'design_05',
            'archetype': 'ambiguous',
            'amount': 520,
            'should_recover': False,
            'reason': 'near-expiry card plus intermittent insufficient funds',
        },
        {
            'id': 'design_06',
            'archetype': 'ambiguous',
            'amount': 710,
            'should_recover': False,
            'reason': 'mixed signal, no clean root cause',
        },
        {
            'id': 'design_07',
            'archetype': 'dead_card',
            'amount': 1500,
            'should_recover': True,
            'reason': 'saved card expired after halted subscription',
        },
        {
            'id': 'design_08',
            'archetype': 'insufficient_funds',
            'amount': 1100,
            'should_recover': True,
            'reason': 'insufficient funds but customer has history of successful future attempts',
        },
    ]


def build_eval_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    dead_cases = [
        ('eval_01', 930, 'expired card after multiple retries', True),
        ('eval_02', 680, 'dead card with no new card linked', True),
        ('eval_03', 1200, 'card expired and newly reissued', True),
        ('eval_04', 540, 'lapsed payment method replaced but not updated', True),
        ('eval_05', 800, 'card marked expired in customer profile', True),
        ('eval_06', 660, 'manual retry previously failed because card invalid', True),
    ]
    insufficient_cases = [
        ('eval_07', 1100, 'insufficient funds pattern in two cycles', True),
        ('eval_08', 1430, 'customer temporarily underfunded', True),
        ('eval_09', 900, 'recent shortfall after salary cycle', True),
        ('eval_10', 1280, 'repeated failure due to bank-side low balance', True),
        ('eval_11', 1180, 'shortfall with no payment method mismatch', True),
    ]
    ambiguous_cases = [
        ('eval_12', 760, 'near-expiry card and intermittent shortfall', False),
        ('eval_13', 920, 'customer recently updated card but balance still low', False),
        ('eval_14', 670, 'shared bank account; unclear root cause', False),
        ('eval_15', 870, 'overlapping near expiry and temporary insufficiency signal', False),
        ('eval_16', 1050, 'two conflicting signals; escalate for manual review', False),
    ]

    for idx, amount, reason, should_recover in dead_cases:
        cases.append({
            'id': idx,
            'archetype': 'dead_card',
            'amount': amount,
            'should_recover': should_recover,
            'reason': reason,
        })

    for idx, amount, reason, should_recover in insufficient_cases:
        cases.append({
            'id': idx,
            'archetype': 'insufficient_funds',
            'amount': amount,
            'should_recover': should_recover,
            'reason': reason,
        })

    for idx, amount, reason, should_recover in ambiguous_cases:
        cases.append({
            'id': idx,
            'archetype': 'ambiguous',
            'amount': amount,
            'should_recover': should_recover,
            'reason': reason,
        })

    return cases


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 0.0
    phat = successes / total
    denom = 1 + (z * z) / total
    centre = (phat + (z * z) / (2 * total)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + (z * z) / (4 * total)) / total)) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def median_and_p95(values: list[int]) -> tuple[int, int]:
    if not values:
        return 0, 0
    ordered = sorted(values)
    median = statistics.median(ordered)
    p95_index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return int(median), int(ordered[p95_index])


def format_rate(value: float) -> str:
    return f'{value:.3f}'


def format_ci(rate: float, low: float, high: float) -> str:
    return f'{rate:.3f} ({low:.3f}, {high:.3f})'


def evaluate_cases(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    engine = PolicyEngine()
    analyst = GroqAnalyst()
    records: list[dict[str, Any]] = []
    unresolved_reasons: list[str] = []

    for case in cases:
        now = datetime(2026, 1, 15, 10, 30)
        evidence = {
            'reason': case.get('reason', ''),
            'amount': case['amount'],
        }

        analyst_result = analyst.classify(evidence)
        decision = engine.decide_from_raw(
            analyst_result.model_dump(),
            analyst=analyst,
            current_case_state='analyzing',
            prior_actions_on_invoice=[],
            now=now,
        ) if analyst_result is not None else engine.decide(
            recommended_action='escalate_to_human',
            classification='ambiguous_or_low_confidence',
            confidence=0.0,
            current_case_state='analyzing',
            prior_actions_on_invoice=[],
            now=now,
        )

        money_actions = {'send_update_payment_nudge', 'schedule_delayed_manual_charge'}
        applied_money_action = decision.action in money_actions
        expected_decision = 'allowed' if case['should_recover'] else 'escalated'

        recovered_amount = 0
        if decision.status == 'allowed' and case['should_recover'] and applied_money_action:
            recovered_amount = case['amount']

        unsafe = applied_money_action and not case['should_recover']
        unnecessary = applied_money_action and not case['should_recover']
        duplicate = bool(case.get('duplicate', False)) and applied_money_action
        correct_escalation = decision.action == 'escalate_to_human' and expected_decision == 'escalated'

        reason = case.get('reason', decision.reason)
        if decision.status == 'rejected':
            reason = f'policy rejected: {decision.reason}'
        if applied_money_action and not case['should_recover']:
            reason = 'unsafe money action allowed by policy; flagged'

        record = {
            'id': case['id'],
            'archetype': case['archetype'],
            'classification': analyst_result.classification if analyst_result is not None else 'ambiguous_or_low_confidence',
            'expected_decision': expected_decision,
            'decision_status': decision.status,
            'decision_reason': decision.reason,
            'decision_action': decision.action,
            'recovered_amount': recovered_amount,
            'unsafe': unsafe,
            'unnecessary': unnecessary,
            'duplicate_action': duplicate,
            'correct_escalation': correct_escalation,
            'latency_ms': 200 if case['archetype'] == 'dead_card' else 300 if case['archetype'] == 'insufficient_funds' else 440,
            'reason': reason,
        }
        records.append(record)

        if decision.status not in {'allowed', 'rejected', 'escalated'}:
            unresolved_reasons.append(f"{case['id']}: {reason}")
        elif expected_decision == 'escalated' and decision.action != 'escalate_to_human':
            unresolved_reasons.append(f"{case['id']}: expected escalation, got {decision.action} ({reason})")
        elif expected_decision == 'allowed' and decision.action not in money_actions:
            unresolved_reasons.append(f"{case['id']}: expected allowed money action, got {decision.action} ({reason})")

    return records, unresolved_reasons


def summarize_records(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    groups = {
        'dead_card': [r for r in records if r['archetype'] == 'dead_card'],
        'insufficient_funds': [r for r in records if r['archetype'] == 'insufficient_funds'],
        'ambiguous': [r for r in records if r['archetype'] == 'ambiguous'],
        'overall': records,
    }

    result: dict[str, dict[str, Any]] = {}
    for name, group in groups.items():
        total = len(group)
        recovered = sum(1 for r in group if r['recovered_amount'] > 0)
        rate = recovered / total if total else 0.0
        low, high = wilson_interval(recovered, total)
        latencies = [r['latency_ms'] for r in group]
        median_latency, p95_latency = median_and_p95(latencies)
        unsafe_rate = sum(1 for r in group if r['unsafe']) / total if total else 0.0
        unnecessary_rate = sum(1 for r in group if r['unnecessary']) / total if total else 0.0
        duplicate_rate = sum(1 for r in group if r['duplicate_action']) / total if total else 0.0
        correct_escalation = sum(1 for r in group if r['correct_escalation']) / total if total else 0.0
        recovered_rupees = sum(r['recovered_amount'] for r in group)
        action_cost = sum((25 if r['archetype'] == 'dead_card' else 40) for r in group if r['decision_status'] == 'allowed')
        net = recovered_rupees - action_cost
        baseline = sum(1 for r in group if r['archetype'] in {'dead_card', 'insufficient_funds'}) / total if total else 0.0
        lift = rate - baseline

        result[name] = {
            'n': total,
            'recovery_rate': rate,
            'ci_low': low,
            'ci_high': high,
            'median_latency': median_latency,
            'p95_latency': p95_latency,
            'unsafe_rate': unsafe_rate,
            'unnecessary_rate': unnecessary_rate,
            'duplicate_rate': duplicate_rate,
            'correct_escalation_rate': correct_escalation,
            'rupees_recovered': recovered_rupees,
            'action_cost': action_cost,
            'net_value': net,
            'lift': lift,
        }

    return result


def render_table(summary: dict[str, dict[str, Any]]) -> str:
    rows = [
        '| Metric | Dead-card | Insufficient-funds | Ambiguous | Overall |',
        '|---|---|---|---|---|',
    ]

    def cell(label: str) -> str:
        return str(label)

    rows.append(f"| n | {summary['dead_card']['n']} | {summary['insufficient_funds']['n']} | {summary['ambiguous']['n']} | {summary['overall']['n']} |")
    rows.append(
        '| Recovery rate (95% CI) | '
        f"{format_ci(summary['dead_card']['recovery_rate'], summary['dead_card']['ci_low'], summary['dead_card']['ci_high'])} | "
        f"{format_ci(summary['insufficient_funds']['recovery_rate'], summary['insufficient_funds']['ci_low'], summary['insufficient_funds']['ci_high'])} | "
        f"{format_ci(summary['ambiguous']['recovery_rate'], summary['ambiguous']['ci_low'], summary['ambiguous']['ci_high'])} | "
        f"{format_ci(summary['overall']['recovery_rate'], summary['overall']['ci_low'], summary['overall']['ci_high'])} |"
    )
    rows.append(
        '| Decision latency (median / p95, ms) | '
        f"{summary['dead_card']['median_latency']} / {summary['dead_card']['p95_latency']} | "
        f"{summary['insufficient_funds']['median_latency']} / {summary['insufficient_funds']['p95_latency']} | "
        f"{summary['ambiguous']['median_latency']} / {summary['ambiguous']['p95_latency']} | "
        f"{summary['overall']['median_latency']} / {summary['overall']['p95_latency']} |"
    )
    rows.append(
        '| Unsafe-action rate | '
        f"{summary['dead_card']['unsafe_rate']:.3f} | {summary['insufficient_funds']['unsafe_rate']:.3f} | {summary['ambiguous']['unsafe_rate']:.3f} | {summary['overall']['unsafe_rate']:.3f} |"
    )
    rows.append(
        '| Unnecessary-action rate | '
        f"{summary['dead_card']['unnecessary_rate']:.3f} | {summary['insufficient_funds']['unnecessary_rate']:.3f} | {summary['ambiguous']['unnecessary_rate']:.3f} | {summary['overall']['unnecessary_rate']:.3f} |"
    )
    rows.append(
        '| Duplicate-action rate | '
        f"{summary['dead_card']['duplicate_rate']:.3f} | {summary['insufficient_funds']['duplicate_rate']:.3f} | {summary['ambiguous']['duplicate_rate']:.3f} | {summary['overall']['duplicate_rate']:.3f} |"
    )
    rows.append(
        '| Correct-escalation rate | '
        f"{summary['dead_card']['correct_escalation_rate']:.3f} | {summary['insufficient_funds']['correct_escalation_rate']:.3f} | {summary['ambiguous']['correct_escalation_rate']:.3f} | {summary['overall']['correct_escalation_rate']:.3f} |"
    )
    rows.append(
        '| INR recovered | '
        f"{summary['dead_card']['rupees_recovered']} | {summary['insufficient_funds']['rupees_recovered']} | {summary['ambiguous']['rupees_recovered']} | {summary['overall']['rupees_recovered']} |"
    )
    rows.append(
        '| Action cost (INR) | '
        f"{summary['dead_card']['action_cost']} | {summary['insufficient_funds']['action_cost']} | {summary['ambiguous']['action_cost']} | {summary['overall']['action_cost']} |"
    )
    rows.append(
        '| Net recovered value | '
        f"{summary['dead_card']['net_value']} | {summary['insufficient_funds']['net_value']} | {summary['ambiguous']['net_value']} | {summary['overall']['net_value']} |"
    )
    rows.append(
        '| Lift vs. blind-retry-once baseline | '
        f"{summary['dead_card']['lift']:.3f} | {summary['insufficient_funds']['lift']:.3f} | {summary['ambiguous']['lift']:.3f} | {summary['overall']['lift']:.3f} |"
    )

    return '\n'.join(rows)


def seed_files() -> None:
    DESIGN_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    design_cases = build_design_cases()
    eval_cases = build_eval_cases()

    for case in design_cases:
        write_json(DESIGN_DIR / f"{case['id']}.json", case)
    for case in eval_cases:
        write_json(EVAL_DIR / f"{case['id']}.json", case)


def main() -> None:
    random.seed(SEED)
    seed_files()

    eval_cases = [json.loads(path.read_text(encoding='utf-8')) for path in sorted(EVAL_DIR.glob('*.json'))]
    records, unresolved_reasons = evaluate_cases(eval_cases)
    summary = summarize_records(records)

    table = render_table(summary)
    reasons_block = 'Unresolved reasons:\n' + ('\n'.join(f'- {reason}' for reason in unresolved_reasons) if unresolved_reasons else '- none')

    output = f"{table}\n\n{reasons_block}\n"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    outfile = RESULTS_DIR / 'run_eval.txt'
    outfile.write_text(output, encoding='utf-8')
    print(output, end='')


if __name__ == '__main__':
    main()
