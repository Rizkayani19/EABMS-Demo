from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Sum

from core.models import Account, BudgetLine, Transaction
from core.services import (
    get_budget_consumed,
    get_budget_utilisation,
    get_opening_balance,
    get_pass_through_inflows,
    get_pass_through_outflows,
    get_total_actual_inflows,
    get_total_actual_outflows,
    get_total_approved_budget,
)

from .registry import ReportDefinition, registry
from . import services as base_services


def _month_start(value):
    return value.replace(day=1)


def _month_end(value):
    return value.replace(day=monthrange(value.year, value.month)[1])


def _effective_range(filters):
    start = filters.get("start_date")
    end = filters.get("end_date")
    fy = filters.get("financial_year")
    if not start and fy:
        start = fy.start_date
    if not end and fy:
        end = fy.end_date
    return start, end


def _month_sequence(start, end):
    if not start or not end or start > end:
        return []
    current = _month_start(start)
    last = _month_start(end)
    months = []
    while current <= last:
        months.append(current.strftime("%Y-%m"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1, day=1)
    return months


def _period_tx_queryset(filters, direction=None):
    qs = Transaction.objects.filter(status=Transaction.Status.ACTIVE)
    if direction:
        qs = qs.filter(direction=direction)
    return base_services.apply_filters(qs, filters)


def build_account_summary(filters):
    account = filters.get("account")
    fy = filters.get("financial_year")
    if not account or not fy:
        return []

    start = filters.get("start_date")
    end = filters.get("end_date")

    if start:
        prior_inflows = Transaction.objects.filter(
            account=account,
            financial_year=fy,
            direction=Transaction.Direction.INFLOW,
            status=Transaction.Status.ACTIVE,
            transaction_date__lt=start,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        prior_outflows = Transaction.objects.filter(
            account=account,
            financial_year=fy,
            direction=Transaction.Direction.OUTFLOW,
            status=Transaction.Status.ACTIVE,
            transaction_date__lt=start,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        period_opening = get_opening_balance(account, fy) + prior_inflows - prior_outflows
    else:
        period_opening = get_opening_balance(account, fy)

    inflows = get_total_actual_inflows(account, fy, start, end)
    outflows = get_total_actual_outflows(account, fy, start, end)
    period_closing = period_opening + inflows - outflows

    pt_in = get_pass_through_inflows(account, fy, start, end)
    pt_out = get_pass_through_outflows(account, fy, start, end)
    op_in = max(Decimal("0.00"), inflows - pt_in)
    op_out = max(Decimal("0.00"), outflows - pt_out)

    approved = get_total_approved_budget(account, fy)
    consumed = get_budget_consumed(account, fy)
    balance_budget = approved - consumed
    utilisation = get_budget_utilisation(account, fy)

    return [{
        "account": account.name,
        "opening_balance": period_opening,
        "operational_inflows": op_in,
        "pass_through_inflows": pt_in,
        "total_inflows": inflows,
        "operational_outflows": op_out,
        "pass_through_outflows": pt_out,
        "total_outflows": outflows,
        "balance_available": period_closing,
        "approved_budget": approved,
        "budget_consumed": consumed,
        "balance_of_budget": balance_budget,
        "budget_utilisation": utilisation,
    }]


def build_monthly_inflows(filters):
    start, end = _effective_range(filters)
    months = {
        month: {
            "month": month,
            "operational_inflows": Decimal("0.00"),
            "pass_through": Decimal("0.00"),
            "amount": Decimal("0.00"),
        }
        for month in _month_sequence(start, end)
    }
    qs = _period_tx_queryset(filters, direction=Transaction.Direction.INFLOW)
    for tx in qs.iterator():
        key = tx.transaction_date.strftime("%Y-%m")
        row = months.setdefault(
            key,
            {
                "month": key,
                "operational_inflows": Decimal("0.00"),
                "pass_through": Decimal("0.00"),
                "amount": Decimal("0.00"),
            },
        )
        if tx.pass_through:
            row["pass_through"] += tx.amount
        else:
            row["operational_inflows"] += tx.amount
        row["amount"] += tx.amount
    return [
        {
            "month": key,
            "operational_inflows": val["operational_inflows"],
            "pass_through": val["pass_through"],
            "amount": val["amount"],
        }
        for key, val in sorted(months.items())
    ]


def build_monthly_outflows(filters):
    start, end = _effective_range(filters)
    months = {
        month: {
            "month": month,
            "operational_outflows": Decimal("0.00"),
            "pass_through": Decimal("0.00"),
            "amount": Decimal("0.00"),
        }
        for month in _month_sequence(start, end)
    }
    qs = _period_tx_queryset(filters, direction=Transaction.Direction.OUTFLOW)
    for tx in qs.iterator():
        key = tx.transaction_date.strftime("%Y-%m")
        row = months.setdefault(
            key,
            {
                "month": key,
                "operational_outflows": Decimal("0.00"),
                "pass_through": Decimal("0.00"),
                "amount": Decimal("0.00"),
            },
        )
        if tx.pass_through:
            row["pass_through"] += tx.amount
        else:
            row["operational_outflows"] += tx.amount
        row["amount"] += tx.amount
    return [{"month": key, "operational_outflows": val["operational_outflows"], "pass_through": val["pass_through"], "amount": val["amount"]} for key, val in sorted(months.items())]


def _build_monthly_single(filters, direction):
    start, end = _effective_range(filters)
    months = {month: Decimal("0.00") for month in _month_sequence(start, end)}
    qs = _period_tx_queryset(filters, direction=direction)
    for tx in qs.iterator():
        key = tx.transaction_date.strftime("%Y-%m")
        months[key] = months.get(key, Decimal("0.00")) + tx.amount
    return [{"month": key, "amount": amount} for key, amount in sorted(months.items())]


def build_monthly_trend(filters):
    account = filters.get("account")
    fy = filters.get("financial_year")
    start, end = _effective_range(filters)

    if start and account and fy:
        prior_inflows = Transaction.objects.filter(
            account=account,
            financial_year=fy,
            direction=Transaction.Direction.INFLOW,
            status=Transaction.Status.ACTIVE,
            transaction_date__lt=start,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        prior_outflows = Transaction.objects.filter(
            account=account,
            financial_year=fy,
            direction=Transaction.Direction.OUTFLOW,
            status=Transaction.Status.ACTIVE,
            transaction_date__lt=start,
        ).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
        current_bal = (get_opening_balance(account, fy) if account and fy else Decimal("0.00")) + prior_inflows - prior_outflows
    elif account and fy:
        current_bal = get_opening_balance(account, fy)
    else:
        current_bal = Decimal("0.00")

    data = {
        month: {
            "month": month,
            "operational_inflows": Decimal("0.00"),
            "pass_through_inflows": Decimal("0.00"),
            "inflows": Decimal("0.00"),
            "operational_outflows": Decimal("0.00"),
            "pass_through": Decimal("0.00"),
            "outflows": Decimal("0.00"),
        }
        for month in _month_sequence(start, end)
    }

    for tx in _period_tx_queryset(filters, direction=Transaction.Direction.INFLOW).iterator():
        month = tx.transaction_date.strftime("%Y-%m")
        row = data.setdefault(
            month,
            {
                "month": month,
                "operational_inflows": Decimal("0.00"),
                "pass_through_inflows": Decimal("0.00"),
                "inflows": Decimal("0.00"),
                "operational_outflows": Decimal("0.00"),
                "pass_through": Decimal("0.00"),
                "outflows": Decimal("0.00"),
            },
        )
        if tx.pass_through:
            row["pass_through_inflows"] += tx.amount
        else:
            row["operational_inflows"] += tx.amount
        row["inflows"] += tx.amount

    for tx in _period_tx_queryset(filters, direction=Transaction.Direction.OUTFLOW).iterator():
        month = tx.transaction_date.strftime("%Y-%m")
        row = data.setdefault(
            month,
            {
                "month": month,
                "operational_inflows": Decimal("0.00"),
                "pass_through_inflows": Decimal("0.00"),
                "inflows": Decimal("0.00"),
                "operational_outflows": Decimal("0.00"),
                "pass_through": Decimal("0.00"),
                "outflows": Decimal("0.00"),
            },
        )
        if tx.pass_through:
            row["pass_through"] += tx.amount
        else:
            row["operational_outflows"] += tx.amount
        row["outflows"] += tx.amount

    rows = []
    for month in sorted(data):
        row = data[month]
        row["opening_balance"] = current_bal
        row["balance_movement"] = row["inflows"] - row["outflows"]
        row["closing_balance"] = current_bal + row["balance_movement"]
        current_bal = row["closing_balance"]
        rows.append(row)
    return rows


def build_budget_vs_actual(filters):
    # Approved budget remains the FY-approved amount; actual expenditure obeys
    # the selected Transaction Date range, aggregated cleanly at Account Head level.
    account = filters.get("account")
    fy = filters.get("financial_year")
    if not account or not fy:
        return []

    budget_qs = BudgetLine.objects.filter(
        budget__account=account,
        budget__financial_year=fy,
        budget__status="APPROVED",
    )
    budget_qs = base_services.apply_filters(budget_qs, filters)

    data = {}
    for line in budget_qs:
        key = line.account_head_id
        if not key:
            continue
        row = data.setdefault(
            key,
            {
                "account_head": line.account_head.name if line.account_head else "Other",
                "approved_budget": Decimal("0.00"),
                "budget_consumed": Decimal("0.00"),
            },
        )
        row["approved_budget"] += line.amount

    tx_qs = _period_tx_queryset(filters, direction=Transaction.Direction.OUTFLOW).filter(
        account=account,
        financial_year=fy,
        pass_through=False,
    )
    for tx in tx_qs.iterator():
        key = tx.account_head_id
        if not key:
            continue
        row = data.setdefault(
            key,
            {
                "account_head": tx.account_head.name if tx.account_head else "Other",
                "approved_budget": Decimal("0.00"),
                "budget_consumed": Decimal("0.00"),
            },
        )
        row["budget_consumed"] += tx.amount

    rows = []
    for row in data.values():
        row["balance_of_budget"] = row["approved_budget"] - row["budget_consumed"]
        row["utilisation_pct"] = (
            row["budget_consumed"] / row["approved_budget"] * Decimal("100.00")
            if row["approved_budget"] else None
        )
        rows.append(row)
    return sorted(rows, key=lambda row: row["account_head"])


def build_budget_utilisation(filters):
    account = filters.get("account")
    fy = filters.get("financial_year")
    if not account or not fy:
        return []

    budget_qs = BudgetLine.objects.filter(
        budget__account=account,
        budget__financial_year=fy,
        budget__status="APPROVED",
    )
    budget_qs = base_services.apply_filters(budget_qs, filters)

    data = {}
    for line in budget_qs:
        ah_name = line.account_head.name if line.account_head else "Other"
        row = data.setdefault(
            ah_name,
            {
                "account_head": ah_name,
                "approved_budget": Decimal("0.00"),
                "budget_consumed": Decimal("0.00"),
            },
        )
        row["approved_budget"] += line.amount

    tx_qs = _period_tx_queryset(filters, direction=Transaction.Direction.OUTFLOW).filter(
        account=account,
        financial_year=fy,
        pass_through=False,
    )
    for tx in tx_qs.iterator():
        ah_name = tx.account_head.name if tx.account_head else "Other"
        row = data.setdefault(
            ah_name,
            {
                "account_head": ah_name,
                "approved_budget": Decimal("0.00"),
                "budget_consumed": Decimal("0.00"),
            },
        )
        row["budget_consumed"] += tx.amount

    rows = []
    for ah_name, row in sorted(data.items()):
        row["balance_of_budget"] = row["approved_budget"] - row["budget_consumed"]
        row["utilisation_pct"] = (
            row["budget_consumed"] / row["approved_budget"] * Decimal("100.00")
            if row["approved_budget"] else None
        )
        rows.append(row)
    return rows


# Replace the date-sensitive definitions in the registry with the corrected,
# Transaction-Date-based builders. Existing reports keep their original
# definitions where no date-range behavior is promised.
def _replace(slug, builder, supported_filters=None, columns=None, totals=None):
    definition = registry.get_report(slug)
    if not definition:
        return
    definition.builder_func = builder
    if supported_filters is not None:
        definition.supported_filters = supported_filters
    if columns is not None:
        definition.columns = columns
    if totals is not None:
        definition.totals = totals


_date_filters = ["account", "financial_year", "start_date", "end_date"]

_replace("account-summary", build_account_summary, _date_filters)
_replace(
    "monthly-inflows",
    build_monthly_inflows,
    _date_filters,
    columns=[
        {"key": "month", "label": "Month"},
        {"key": "operational_inflows", "label": "Operational Inflows (Excl. Pass-Through)"},
        {"key": "pass_through", "label": "Pass-Through Inflows (Internal)"},
        {"key": "amount", "label": "Total Inflows (Gross)"},
    ],
    totals=["operational_inflows", "pass_through", "amount"],
)
_replace(
    "monthly-outflows",
    build_monthly_outflows,
    ["account", "financial_year", "start_date", "end_date", "major_head", "sub_head", "account_head"],
    columns=[
        {"key": "month", "label": "Month"},
        {"key": "operational_outflows", "label": "Operational Outflows (Excl. Pass-Through)"},
        {"key": "pass_through", "label": "Pass-Through Transfers (Internal)"},
        {"key": "amount", "label": "Total Outflows (Gross)"},
    ],
    totals=["operational_outflows", "pass_through", "amount"],
)
_replace(
    "monthly-trend",
    build_monthly_trend,
    _date_filters,
    columns=[
        {"key": "month", "label": "Month"},
        {"key": "opening_balance", "label": "Opening Balance"},
        {"key": "operational_inflows", "label": "Operational Inflows (Excl PT)"},
        {"key": "pass_through_inflows", "label": "PT Inflows"},
        {"key": "inflows", "label": "Total Inflows"},
        {"key": "operational_outflows", "label": "Operational Outflows (Excl PT)"},
        {"key": "pass_through", "label": "Pass-Through Tfrs"},
        {"key": "outflows", "label": "Total Outflows"},
        {"key": "balance_movement", "label": "Net Movement"},
        {"key": "closing_balance", "label": "Closing Balance"},
    ],
    totals=[
        "operational_inflows",
        "pass_through_inflows",
        "inflows",
        "operational_outflows",
        "pass_through",
        "outflows",
        "balance_movement",
    ],
)
_replace("budget-vs-actual", build_budget_vs_actual, [
    "account", "financial_year", "start_date", "end_date", "major_head", "account_head"
])
_replace(
    "budget-utilisation",
    build_budget_utilisation,
    ["account", "financial_year", "start_date", "end_date", "major_head", "account_head"],
    columns=[
        {"key": "account_head", "label": "Acct Head"},
        {"key": "approved_budget", "label": "Approved Budget"},
        {"key": "budget_consumed", "label": "Budget Consumed"},
        {"key": "balance_of_budget", "label": "Balance of Budget"},
        {"key": "utilisation_pct", "label": "Utilisation %"},
    ],
    totals=["approved_budget", "budget_consumed", "balance_of_budget"],
)
