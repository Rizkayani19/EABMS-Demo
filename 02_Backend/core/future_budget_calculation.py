from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def money(value):
    return (value or ZERO).quantize(Decimal("0.01"))


@dataclass(frozen=True)
class FutureBudgetCalculation:
    """Auditable, schema-independent result of one Future Budget calculation."""

    previous_actual: Decimal
    routine_adjustment: Decimal
    routine_adjustment_pct: Decimal
    continuing_requirement: Decimal
    management_additional_requirement: Decimal
    known_changes: Decimal
    personnel_effect: Decimal
    onetime_deduction: Decimal
    system_suggested: Decimal

    @property
    def breakdown(self):
        return {
            "previous_actual": str(money(self.previous_actual)),
            "routine_adjustment": str(money(self.routine_adjustment)),
            "routine_adjustment_pct": str(self.routine_adjustment_pct),
            "continuing_requirement": str(money(self.continuing_requirement)),
            "management_additional_requirement": str(money(self.management_additional_requirement)),
            "known_changes": str(money(self.known_changes)),
            "personnel_effect": str(money(self.personnel_effect)),
            "onetime_deduction": str(money(self.onetime_deduction)),
            "system_suggested": str(money(self.system_suggested)),
        }


def calculate_future_budget_components(
    previous_actual,
    routine_adj_pct,
    continuing_amount,
    known_change_amount,
    personnel_amount,
    onetime_amount,
    additional_management_amount=ZERO,
):
    """Canonical Future Budget arithmetic; callers provide already-classified inputs."""
    previous_actual = money(previous_actual)
    routine_adj_pct = money(routine_adj_pct)
    continuing_amount = money(continuing_amount)
    known_change_amount = money(known_change_amount)
    personnel_amount = money(personnel_amount)
    onetime_amount = money(onetime_amount)
    additional_management_amount = money(additional_management_amount)

    routine_adjustment = money(previous_actual * routine_adj_pct / HUNDRED)
    system_suggested = max(
        money(
            previous_actual
            + routine_adjustment
            + continuing_amount
            + additional_management_amount
            + known_change_amount
            + personnel_amount
            - onetime_amount
        ),
        ZERO,
    )

    return FutureBudgetCalculation(
        previous_actual=previous_actual,
        routine_adjustment=routine_adjustment,
        routine_adjustment_pct=routine_adj_pct,
        continuing_requirement=continuing_amount,
        management_additional_requirement=additional_management_amount,
        known_changes=known_change_amount,
        personnel_effect=personnel_amount,
        onetime_deduction=onetime_amount,
        system_suggested=system_suggested,
    )
