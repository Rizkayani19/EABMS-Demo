from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Sum

from .models import AccountHead, MajorHead, SubHead, Transaction
from .services import get_opening_balance, get_sub_fund_distribution_summary

ZERO = Decimal("0.00")


def _money(value):
    return (value or ZERO).quantize(Decimal("0.01"))


def _movement(qs):
    inflows = qs.filter(direction=Transaction.Direction.INFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    outflows = qs.filter(direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    difference = inflows - outflows
    return _money(inflows), _money(outflows), _money(difference)


def _base_queryset(account, financial_year, as_of=None):
    qs = Transaction.objects.filter(
        account=account,
        financial_year=financial_year,
        status=Transaction.Status.ACTIVE,
    )
    if as_of:
        qs = qs.filter(transaction_date__lte=as_of)
    return qs


def _row(name, code, opening, inflows, outflows):
    opening = _money(opening)
    inflows = _money(inflows)
    outflows = _money(outflows)
    difference = _money(inflows - outflows)
    present = _money(opening + difference)
    return {
        "name": name,
        "code": code,
        "opening_balance": opening,
        "total_inflows": inflows,
        "total_outflows": outflows,
        "difference": difference,
        "present_balance": present,
    }


def _totals(rows):
    return _row(
        "TOTAL",
        "",
        sum((r["opening_balance"] for r in rows), ZERO),
        sum((r["total_inflows"] for r in rows), ZERO),
        sum((r["total_outflows"] for r in rows), ZERO),
    )


def _opening_by_subfund(account, financial_year):
    data = get_sub_fund_distribution_summary(account, financial_year)
    return {str(r["id"]): _money(r["opening_balance"]) for r in data.get("sub_funds", [])}


def build_sub_fund_report(account, financial_year, as_of=None):
    """Present balance by Sub Fund (Major Head), reconciled to fund balance."""
    qs = _base_queryset(account, financial_year, as_of)
    opening_map = _opening_by_subfund(account, financial_year)
    rows = []
    for sf in MajorHead.objects.filter(account=account, is_active=True).order_by("display_order", "name"):
        in_qs = qs.filter(major_head=sf, direction=Transaction.Direction.INFLOW)
        out_qs = qs.filter(major_head=sf, direction=Transaction.Direction.OUTFLOW)
        inflows = in_qs.aggregate(v=Sum("amount"))["v"] or ZERO
        outflows = out_qs.aggregate(v=Sum("amount"))["v"] or ZERO
        rows.append(_row(sf.name, sf.code, opening_map.get(str(sf.id), ZERO), inflows, outflows))
    totals = _totals(rows)
    unallocated_in = qs.filter(major_head__isnull=True, direction=Transaction.Direction.INFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    unallocated_out = qs.filter(major_head__isnull=True, direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    if unallocated_in > ZERO or unallocated_out > ZERO:
        rows.append(_row("Unallocated Sub Fund", "DIRECT", ZERO, unallocated_in, unallocated_out))
        totals = _totals(rows)
    fund_opening = _money(get_opening_balance(account, financial_year))
    fund_present = _money(fund_opening + totals["difference"])
    return {
        "level": "Sub Fund",
        "rows": rows,
        "totals": totals,
        "fund_opening": fund_opening,
        "fund_present": fund_present,
        "opening_reconciled": totals["opening_balance"] == fund_opening,
    }


def build_account_head_report(account, financial_year, as_of=None):
    """Present balance by Account Head. Opening balance remains explicitly unallocated."""
    qs = _base_queryset(account, financial_year, as_of)
    rows = []
    for ah in AccountHead.objects.filter(account=account, is_active=True).select_related("major_head").order_by("major_head__display_order", "display_order", "name"):
        inflows = qs.filter(account_head=ah, direction=Transaction.Direction.INFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
        outflows = qs.filter(account_head=ah, direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
        rows.append(_row(ah.name, ah.code, ZERO, inflows, outflows))
    unallocated_in = qs.filter(account_head__isnull=True, direction=Transaction.Direction.INFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    unallocated_out = qs.filter(account_head__isnull=True, direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    if unallocated_in > ZERO or unallocated_out > ZERO:
        rows.append(_row("Unallocated Account Head", "DIRECT", ZERO, unallocated_in, unallocated_out))
    opening = _money(get_opening_balance(account, financial_year))
    rows.insert(0, _row("Unallocated Opening Balance", "OPENING", opening, ZERO, ZERO))
    totals = _totals(rows)
    return {"level": "Account Head", "rows": rows, "totals": totals, "fund_opening": opening, "fund_present": _money(opening + totals["difference"]), "opening_reconciled": True}


def build_sub_account_head_report(account, financial_year, as_of=None):
    """Present balance by Sub Account Head (Sub Head). Opening balance is explicit and unallocated."""
    qs = _base_queryset(account, financial_year, as_of)
    rows = []
    subheads = SubHead.objects.filter(account=account, is_active=True).select_related("major_head", "account_head").order_by("major_head__display_order", "account_head__display_order", "display_order", "name")
    for sh in subheads:
        inflows = qs.filter(sub_head=sh, direction=Transaction.Direction.INFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
        outflows = qs.filter(sub_head=sh, direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
        rows.append(_row(sh.name, sh.code, ZERO, inflows, outflows))
    unallocated_in = qs.filter(sub_head__isnull=True, direction=Transaction.Direction.INFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    unallocated_out = qs.filter(sub_head__isnull=True, direction=Transaction.Direction.OUTFLOW).aggregate(v=Sum("amount"))["v"] or ZERO
    if unallocated_in > ZERO or unallocated_out > ZERO:
        rows.append(_row("Direct / Unallocated Sub Head", "DIRECT", ZERO, unallocated_in, unallocated_out))
    opening = _money(get_opening_balance(account, financial_year))
    rows.insert(0, _row("Unallocated Opening Balance", "OPENING", opening, ZERO, ZERO))
    totals = _totals(rows)
    return {"level": "Sub Account Head", "rows": rows, "totals": totals, "fund_opening": opening, "fund_present": _money(opening + totals["difference"]), "opening_reconciled": True}
