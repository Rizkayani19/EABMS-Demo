from __future__ import annotations

from decimal import Decimal

from .future_budget_allocation import FutureBudgetAllocationService

ZERO = Decimal("0.00")

COMPONENT_COLUMNS = (
    "Recurring Baseline",
    "Routine Adjustment",
    "Continuing Requirement",
    "Management Additional",
    "Known Changes",
    "Personnel Effect",
    "One-Time / Discontinued",
    "System Suggested",
    "Management Proposed",
    "Approved Amount",
)


def _decimal(value):
    return Decimal(str(value or ZERO)).quantize(Decimal("0.01"))


def calculation_detail_row(line):
    """Build the workbook's canonical calculation-detail row from SSOT data."""
    breakdown = line.suggestion_breakdown or {}
    return {
        "Account Head": line.account_head.name,
        "Previous Budget": _decimal(line.previous_budget),
        "Previous Actual": _decimal(line.previous_actual),
        "Recurring Baseline": _decimal(breakdown.get("previous_actual", line.previous_actual)),
        "Routine Adjustment": _decimal(breakdown.get("routine_adjustment")),
        "Continuing Requirement": _decimal(breakdown.get("continuing_requirement", line.continuing_amount)),
        "Management Additional": _decimal(
            breakdown.get("management_additional_requirement", line.addl_amount)
        ),
        "Known Changes": _decimal(breakdown.get("known_changes", line.known_change_amount)),
        "Personnel Effect": _decimal(breakdown.get("personnel_effect", line.personnel_amount)),
        "One-Time / Discontinued": _decimal(
            breakdown.get("onetime_deduction", line.onetime_amount)
        ),
        "System Suggested": _decimal(line.system_suggested),
        "Management Proposed": _decimal(line.user_proposed) if line.user_proposed is not None else None,
        "Approved Amount": _decimal(line.approved_amount) if line.approved_amount is not None else None,
        "Approved": _decimal(line.approved_amount) if line.approved_amount is not None else None,
    }


def allocation_control_row(line):
    result = FutureBudgetAllocationService.reconcile(line)
    return {
        "Account Head": line.account_head.name,
        "Target Amount": result["target"],
        "Allocated Amount": result["allocated"],
        "Difference": result["difference"],
        "Status": result["status"],
    }


def build_controls(lines):
    """Return deterministic workbook control rows; contains no business formula."""
    controls = []
    for line in lines:
        result = FutureBudgetAllocationService.reconcile(line)
        controls.append({
            "control": line.account_head.name,
            "value": result["target"],
            "status": result["status"],
            "detail": f"Allocated: {result['allocated']}; Diff: {result['difference']}",
        })
        if line.approved_amount is not None and line.user_proposed is None:
            controls.append({
                "control": line.account_head.name,
                "value": None,
                "status": "EXCEPTION: APPROVED WITHOUT PROPOSAL",
                "detail": "",
            })
    return controls


# Exporter-facing adapter names. Keep these as thin aliases so the workbook
# exporter depends on the canonical contract implementation rather than
# duplicating calculation logic.
def build_calculation_detail_row(line):
    return calculation_detail_row(line)


def build_workbook_controls(future_budget):
    return build_controls(future_budget.lines.select_related("account_head").all())
