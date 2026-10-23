"""Budget analysis engine for ABMS.

N6/N12 baseline: existing-FY budget-vs-actual analysis and auditable inputs for
future-FY planning. Historical actuals are always calculated from Transaction,
the financial Single Source of Truth.
"""
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Sum

from core.models import Transaction, Budget, BudgetLine, AccountHead, Unit, InternalSection
from core.historical_budget_allocation_models import HistoricalBudgetAllocation

ZERO = Decimal("0.00")
HUNDRED = Decimal("100")


def money(value):
    return (value or ZERO).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _actual_queryset(account, financial_year):
    return Transaction.objects.filter(
        account=account,
        financial_year=financial_year,
        direction=Transaction.Direction.OUTFLOW,
        status=Transaction.Status.ACTIVE,
    )


def _budget_lines(account, financial_year):
    budget = Budget.objects.filter(
        account=account,
        financial_year=financial_year,
        status__in=[Budget.Status.DRAFT, Budget.Status.APPROVED, Budget.Status.CLOSED],
    ).order_by("-created_at").first()
    return budget, (budget.lines.all() if budget else BudgetLine.objects.none())


def actual_total(account, financial_year):
    return money(_actual_queryset(account, financial_year).aggregate(t=Sum("amount"))["t"])


def budget_total(account, financial_year):
    budget, lines = _budget_lines(account, financial_year)
    return money(lines.aggregate(t=Sum("amount"))["t"]) if budget else ZERO


def analyse_budget(account, financial_year, allocation_basis=None):
    """Return a reconciliation-safe FY budget analysis by account head or sub-fund."""
    from core.models import MajorHead
    budget, lines = _budget_lines(account, financial_year)
    actuals = _actual_queryset(account, financial_year)
    
    basis = allocation_basis or getattr(budget, 'budget_allocation_basis', None) or getattr(account, 'budget_allocation_basis', 'ACCOUNT_HEAD')
    
    if basis == 'SUB_FUND':
        actual_by_sf = {r["major_head_id"]: money(r["total"]) for r in actuals.values("major_head_id").annotate(total=Sum("amount")) if r["major_head_id"]}
        budget_by_sf = {r["major_head_id"]: money(r["total"]) for r in lines.values("major_head_id").annotate(total=Sum("amount")) if r["major_head_id"]}
        sf_ids = list(OrderedDict.fromkeys(list(budget_by_sf) + list(actual_by_sf)))
        all_sfs = list(MajorHead.objects.filter(account=account, is_active=True).order_by('display_order', 'name'))
        for sf in all_sfs:
            if sf.id not in sf_ids:
                sf_ids.append(sf.id)
        sfs = {s.id: s for s in MajorHead.objects.filter(id__in=sf_ids)}
        rows = []
        for sf_id in sf_ids:
            budgeted = budget_by_sf.get(sf_id, ZERO)
            actual = actual_by_sf.get(sf_id, ZERO)
            variance = money(budgeted - actual)
            utilisation = money((actual * HUNDRED / budgeted) if budgeted else ZERO)
            rows.append({
                "major_head_id": sf_id,
                "account_head_id": sf_id,
                "account_head": sfs[sf_id].name if sf_id in sfs else str(sf_id),
                "major_head": sfs[sf_id].name if sf_id in sfs else str(sf_id),
                "code": sfs[sf_id].code if sf_id in sfs else "",
                "budget": budgeted,
                "actual": actual,
                "variance": variance,
                "utilisation_pct": utilisation,
                "status": "OVER" if actual > budgeted and budgeted else ("UNDER" if actual < budgeted else "ON/NO BUDGET"),
            })
        total_budget = money(sum((r["budget"] for r in rows), ZERO))
        total_actual = money(sum((r["actual"] for r in rows), ZERO))
        return {
            "account": account, "financial_year": financial_year, "budget": budget,
            "allocation_basis": "SUB_FUND",
            "rows": rows, "total_budget": total_budget, "total_actual": total_actual,
            "total_variance": money(total_budget - total_actual),
            "utilisation_pct": money((total_actual * HUNDRED / total_budget) if total_budget else ZERO),
            "reconciliation_difference": money(total_actual - actual_total(account, financial_year)),
        }

    actual_by_head = {r["account_head_id"]: money(r["total"]) for r in actuals.values("account_head_id").annotate(total=Sum("amount"))}
    budget_by_head = {r["account_head_id"]: money(r["total"]) for r in lines.values("account_head_id").annotate(total=Sum("amount"))}
    head_ids = list(OrderedDict.fromkeys(list(budget_by_head) + list(actual_by_head)))
    heads = {h.id: h for h in AccountHead.objects.filter(id__in=head_ids)}
    rows = []
    for head_id in head_ids:
        budgeted = budget_by_head.get(head_id, ZERO)
        actual = actual_by_head.get(head_id, ZERO)
        variance = money(budgeted - actual)
        utilisation = money((actual * HUNDRED / budgeted) if budgeted else ZERO)
        rows.append({"account_head_id": head_id, "account_head": heads[head_id].name if head_id in heads else str(head_id), "budget": budgeted, "actual": actual, "variance": variance, "utilisation_pct": utilisation, "status": "OVER" if actual > budgeted and budgeted else ("UNDER" if actual < budgeted else "ON/NO BUDGET")})
    total_budget = money(sum((r["budget"] for r in rows), ZERO))
    total_actual = money(sum((r["actual"] for r in rows), ZERO))
    return {"account": account, "financial_year": financial_year, "budget": budget, "allocation_basis": "ACCOUNT_HEAD", "rows": rows, "total_budget": total_budget, "total_actual": total_actual, "total_variance": money(total_budget - total_actual), "utilisation_pct": money((total_actual * HUNDRED / total_budget) if total_budget else ZERO), "reconciliation_difference": money(total_actual - actual_total(account, financial_year))}


def _historical_org_budget_maps(budget):
    """Return explicit historical budget allocations by Unit, Section and matrix.

    If no explicit allocations exist for a budget line, its legacy Unit field is
    retained as a Unit attribution. No Internal Section budget is inferred from
    the Unit's managed-by relationship because that would create artificial data.
    """
    allocations = HistoricalBudgetAllocation.objects.filter(
        budget_line__budget=budget
    ).select_related('budget_line', 'unit', 'internal_section')

    unit_budget = {}
    section_budget = {}
    matrix_budget = {}
    allocated_line_ids = set()
    for a in allocations.iterator():
        amount = money(a.allocated_amount)
        unit_name = a.unit.name if a.unit else 'Unattributed'
        section_name = a.internal_section.name if a.internal_section else 'Unattributed'
        unit_budget[unit_name] = unit_budget.get(unit_name, ZERO) + amount
        section_budget[section_name] = section_budget.get(section_name, ZERO) + amount
        key = (unit_name, section_name)
        matrix_budget[key] = matrix_budget.get(key, ZERO) + amount
        allocated_line_ids.add(a.budget_line_id)

    for line in budget.lines.select_related('unit'):
        if line.id in allocated_line_ids:
            continue
        unit_name = line.unit.name if line.unit else 'Unattributed'
        amount = money(line.amount)
        unit_budget[unit_name] = unit_budget.get(unit_name, ZERO) + amount
        matrix_budget[(unit_name, 'Unattributed')] = matrix_budget.get((unit_name, 'Unattributed'), ZERO) + amount

    return unit_budget, section_budget, matrix_budget


def build_existing_organisational_analysis(account, financial_year, units=None, internal_sections=None):
    """Compare existing-FY budget and actuals by Unit and Internal Section."""
    budget, lines = _budget_lines(account, financial_year)
    actuals = _actual_queryset(account, financial_year)
    unit_filter = [v for v in (units or []) if v]
    section_filter = [v for v in (internal_sections or []) if v]

    if unit_filter:
        actuals = actuals.filter(unit__name__in=unit_filter)
        lines = lines.filter(unit__name__in=unit_filter)
    if section_filter:
        actuals = actuals.filter(internal_section__name__in=section_filter)

    unit_budget_all, section_budget_all, matrix_budget_all = _historical_org_budget_maps(budget) if budget else ({}, {}, {})
    unit_budget = {k: v for k, v in unit_budget_all.items() if not unit_filter or k in unit_filter}
    section_budget = {k: v for k, v in section_budget_all.items() if not section_filter or k in section_filter}
    unit_actual = {r['unit__name']: money(r['total']) for r in actuals.values('unit__name').annotate(total=Sum('amount'))}
    section_actual = {r['internal_section__name']: money(r['total']) for r in actuals.values('internal_section__name').annotate(total=Sum('amount'))}

    names = set(unit_budget) | set(unit_actual)
    unit_rows = []
    for name in sorted(names, key=lambda x: x or 'Unattributed'):
        label = name or 'Unattributed'
        budgeted, actual = unit_budget.get(name, ZERO), unit_actual.get(name, ZERO)
        unit_rows.append({'unit': label, 'budget': budgeted, 'actual': actual, 'variance': money(budgeted - actual), 'utilisation_pct': money(actual * HUNDRED / budgeted) if budgeted else ZERO})

    section_names = set(section_budget) | set(section_actual)
    section_rows = []
    for name in sorted(section_names, key=lambda x: x or 'Unattributed'):
        label = name or 'Unattributed'
        budgeted, actual = section_budget.get(name, ZERO), section_actual.get(name, ZERO)
        section_rows.append({'internal_section': label, 'budget': budgeted, 'actual': actual, 'variance': money(budgeted - actual), 'utilisation_pct': money(actual * HUNDRED / budgeted) if budgeted else ZERO})

    matrix_actual = {}
    for row in actuals.values('unit__name', 'internal_section__name').annotate(total=Sum('amount')):
        key = (row['unit__name'] or 'Unattributed', row['internal_section__name'] or 'Unattributed')
        matrix_actual[key] = money(row['total'])
    matrix_keys = set(matrix_budget_all) | set(matrix_actual)
    if unit_filter:
        matrix_keys = {k for k in matrix_keys if k[0] in unit_filter}
    if section_filter:
        matrix_keys = {k for k in matrix_keys if k[1] in section_filter}
    matrix_rows = []
    for key in sorted(matrix_keys):
        budgeted, actual = matrix_budget_all.get(key, ZERO), matrix_actual.get(key, ZERO)
        matrix_rows.append({'unit': key[0], 'internal_section': key[1], 'budget': budgeted, 'actual': actual, 'variance': money(budgeted - actual)})

    return {
        'budget': budget, 'unit_rows': unit_rows, 'section_rows': section_rows, 'matrix_rows': matrix_rows,
        'unit_budget_total': money(sum(unit_budget.values(), ZERO)), 'unit_actual_total': money(sum(unit_actual.values(), ZERO)),
        'section_budget_total': money(sum(section_budget.values(), ZERO)), 'section_actual_total': money(sum(section_actual.values(), ZERO)),
        'historical_section_budget_available': bool(section_budget_all), 'historical_section_budget_total': money(sum(section_budget_all.values(), ZERO)),
        'filters': {'units': unit_filter, 'internal_sections': section_filter},
    }


def monthly_actuals(account, financial_year):
    qs = _actual_queryset(account, financial_year)
    result = []
    cursor = financial_year.start_date
    for _ in range(12):
        year, month = cursor.year, cursor.month
        total = qs.filter(transaction_date__year=year, transaction_date__month=month).aggregate(t=Sum("amount"))["t"]
        result.append({"year": year, "month": month, "amount": money(total)})
        cursor = cursor.replace(year=year + 1, month=1, day=1) if month == 12 else cursor.replace(month=month + 1, day=1)
    return result


def variance_flags(analysis, material_pct=Decimal("10.00")):
    flags = []
    for row in analysis["rows"]:
        if row["budget"] <= ZERO:
            if row["actual"] > ZERO:
                flags.append({**row, "flag": "UNBUDGETED ACTUAL"})
            continue
        if row["utilisation_pct"] > HUNDRED + material_pct:
            flags.append({**row, "flag": "MATERIAL OVER-UTILISATION"})
        elif row["utilisation_pct"] < HUNDRED - material_pct:
            flags.append({**row, "flag": "MATERIAL UNDER-UTILISATION"})
    return flags


def build_future_baseline(source_account, source_fy, target_fy, routine_adjustment_pct=ZERO):
    """Create/update a draft analytical future plan; never mutate an approved plan."""
    from core.models import FutureBudget
    from core.future_budget_services import build_future_budget_lines

    future_budget, created = FutureBudget.objects.get_or_create(
        account=source_account,
        target_fy=target_fy,
        source_fy=source_fy,
        defaults={
            "routine_adjustment_pct": routine_adjustment_pct,
            "status": FutureBudget.Status.DRAFT,
            "reference": "Analytical Future Budget Baseline",
        },
    )
    if future_budget.status == FutureBudget.Status.APPROVED:
        raise ValueError(
            f"Future Budget #{future_budget.pk} is already APPROVED; use the non-destructive planning preview."
        )
    future_budget.routine_adjustment_pct = routine_adjustment_pct
    future_budget.save(update_fields=["routine_adjustment_pct", "updated_at"])
    build_future_budget_lines(future_budget)
    return future_budget
