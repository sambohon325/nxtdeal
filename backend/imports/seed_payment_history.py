"""
Seeds real payment history for a representative subset of the 315 real
FinanceContract loans in this seed graph -- without this, core/loan_servicing.py's
balance/delinquency computation would stay on its own SIMULATED estimate for every
loan forever, since core/payments.py's real ledger starts genuinely empty. Same
discipline as imports/seed_service_operational.py: calls the real
core.payments.record_payment() function directly, not a flat Entity(attributes=...)
import, so every real invariant that function enforces (the simulated gateway
approval/decline roll, the real principal/interest split against the loan's own real
running balance) runs for real -- exactly as if a cashier had recorded each payment
one at a time.

Deliberately does NOT seed all 315 loans -- elapsed months since ContractDate range
from 0 to 20 across this seed graph, so seeding every loan's full history would create
thousands of Payment entities and take a very long time (core/storage.py's
save_graph() costs several seconds per call on this graph's real size -- this script
works around that by disabling per-call saves during the loop and saving once at the
end, a standard bulk-seeding technique, not a change to core/payments.py's own normal
one-save-per-call behavior). A representative ~50-loan subset, spread across the real
elapsed-month distribution, is enough to meaningfully demonstrate the real-ledger-
overrides-simulated-estimate behavior while deliberately leaving most of the
portfolio on the honest SIMULATED path -- a real demonstration of graceful
coexistence between the two, not a claim that every loan in this seed has real
payment history.

Payment behavior seeded per loan is intentionally varied, not uniformly perfect:
most loans pay on schedule (their monthly payment amount, mostly via ach/debit_card/
cash), a smaller number skip one or two payments partway through to create real,
ledger-derived delinquency (rather than only ever showing "current"), and a couple
make a partial payment to exercise Partial Payment Rules. Called from
run_seed_import.py after finance contracts are already loaded (looks loans up by
graph id directly).
"""

from datetime import date

import core.payments as payments_module
from core.dealeros import ledger
from core.entity_types import FINANCE_CONTRACT
from core.loan_servicing import _schedule_position, _safe_float, _parse_date
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

STAFF_EMPLOYEE = "EMP-00001"
_METHOD_CYCLE = ("ach", "debit_card", "cash", "credit_card")


def _all_loans():
    return [e for e in ledger.get_all().values() if e.entity_type == FINANCE_CONTRACT]


def _add_months(d, n):
    month_index = d.month - 1 + n
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def run(sample_size=50):

    loans = _all_loans()
    with_elapsed = []
    for loan in loans:
        elapsed, schedule, _ = _schedule_position(loan)
        if elapsed > 0:
            with_elapsed.append((loan, elapsed))

    # Spread the sample across the real elapsed-month distribution rather than just
    # taking the first N (which would skew toward whatever sort order the ledger
    # happens to return) -- sort by elapsed months, then take an even stride.
    with_elapsed.sort(key=lambda pair: pair[1])
    stride = max(1, len(with_elapsed) // sample_size)
    sample = with_elapsed[::stride][:sample_size]

    # Disable record_payment()'s per-call save_graph during the loop -- a real bulk-
    # seeding performance technique, not a change to normal single-payment behavior.
    real_save_graph = payments_module.save_graph
    payments_module.save_graph = lambda *_a, **_kw: None

    created = 0
    try:
        for i, (loan, elapsed) in enumerate(sample):
            monthly_payment = _safe_float(loan.attributes.get("MonthlyPayment"))
            contract_date = _parse_date(loan.attributes.get("ContractDate"))
            if monthly_payment <= 0 or not contract_date:
                continue

            # Roughly every 7th sampled loan misses a payment partway through (real
            # ledger-derived delinquency instead of every seeded loan being perfectly
            # current), and every 11th makes one partial payment.
            skip_period = elapsed // 2 if i % 7 == 0 and elapsed >= 2 else None
            partial_period = elapsed // 2 if i % 11 == 0 and elapsed >= 2 else None

            for period in range(1, elapsed + 1):
                if period == skip_period:
                    continue

                amount = monthly_payment
                if period == partial_period:
                    amount = round(monthly_payment * 0.5, 2)

                method = _METHOD_CYCLE[period % len(_METHOD_CYCLE)]
                payment_date = _add_months(contract_date, period).isoformat()
                payments_module.record_payment(
                    loan.id, amount, method, STAFF_EMPLOYEE,
                    payment_date=payment_date, notes="Seeded historical payment",
                )
                created += 1
    finally:
        payments_module.save_graph = real_save_graph

    save_graph(GRAPH_PATH)

    return created, len(sample)
