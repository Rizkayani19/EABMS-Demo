from decimal import Decimal

from django.db.models import Sum

from core.models import Transaction
from masters.models import TransactionOrganisationAllocation
from .registry import registry, ReportDefinition


ORG_FILTER_KEYS = ("unit_ids", "internal_section_ids")


def _active_transactions(filters):
    qs = Transaction.objects.filter(status="ACTIVE")
    if filters.get("account"):
        qs = qs.filter(account=filters["account"])
    if filters.get("financial_year"):
        qs = qs.filter(financial_year=filters["financial_year"])
    if filters.get("start_date"):
        qs = qs.filter(transaction_date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(transaction_date__lte=filters["end_date"])
    if filters.get("direction"):
        qs = qs.filter(direction=filters["direction"])
    if filters.get("account_head"):
        qs = qs.filter(account_head=filters["account_head"])
    if filters.get("sub_head"):
        qs = qs.filter(sub_head=filters["sub_head"])
    if filters.get("major_head"):
        qs = qs.filter(major_head=filters["major_head"])
    if filters.get("outflow_nature"):
        qs = qs.filter(outflow_nature=filters["outflow_nature"])
    if filters.get("pass_through") is not None:
        qs = qs.filter(pass_through=filters["pass_through"])
    elif "pass_through" not in filters:
        qs = qs.filter(pass_through=False)
    return qs


def _allocation_queryset(filters):
    qs = TransactionOrganisationAllocation.objects.filter(transaction__status="ACTIVE")
    if filters.get("account"):
        qs = qs.filter(transaction__account=filters["account"])
    if filters.get("financial_year"):
        qs = qs.filter(transaction__financial_year=filters["financial_year"])
    if filters.get("start_date"):
        qs = qs.filter(transaction__transaction_date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(transaction__transaction_date__lte=filters["end_date"])
    if filters.get("direction"):
        qs = qs.filter(transaction__direction=filters["direction"])
    if filters.get("account_head"):
        qs = qs.filter(transaction__account_head=filters["account_head"])
    if filters.get("sub_head"):
        qs = qs.filter(transaction__sub_head=filters["sub_head"])
    if filters.get("major_head"):
        qs = qs.filter(transaction__major_head=filters["major_head"])
    if filters.get("outflow_nature"):
        qs = qs.filter(transaction__outflow_nature=filters["outflow_nature"])
    if filters.get("unit_ids"):
        qs = qs.filter(unit_id__in=filters["unit_ids"])
    if filters.get("internal_section_ids"):
        qs = qs.filter(internal_section_id__in=filters["internal_section_ids"])
    if filters.get("pass_through") is not None:
        qs = qs.filter(transaction__pass_through=filters["pass_through"])
    elif "pass_through" not in filters:
        qs = qs.filter(transaction__pass_through=False)
    return qs


def build_organisational_transactions(filters):
    """Return transaction-level organisational rows without double counting."""
    tx_qs = _active_transactions(filters).prefetch_related(
        "organisation_allocations__unit",
        "organisation_allocations__internal_section",
        "unit",
    ).order_by("transaction_date", "id")
    unit_filter = bool(filters.get("unit_ids"))
    section_filter = bool(filters.get("internal_section_ids"))
    rows = []
    for tx in tx_qs:
        allocations = list(tx.organisation_allocations.all())
        if allocations:
            for alloc in allocations:
                if unit_filter and alloc.unit_id not in filters["unit_ids"]:
                    continue
                if section_filter and alloc.internal_section_id not in filters["internal_section_ids"]:
                    continue
                rows.append({
                    "transaction_id": tx.transaction_number,
                    "date": tx.transaction_date,
                    "direction": tx.direction,
                    "account": tx.account.name,
                    "account_head": tx.account_head.name if tx.account_head else "",
                    "sub_head": tx.sub_head.name if tx.sub_head else "",
                    "unit": alloc.unit.name if alloc.unit else "",
                    "internal_section": alloc.internal_section.name if alloc.internal_section else "",
                    "amount": alloc.allocated_amount,
                    "transaction_amount": tx.amount,
                    "allocation_based": True,
                })
        elif not allocations:
            tx_u_id = getattr(tx, "unit_id", None)
            tx_sec_id = getattr(tx, "internal_section_id", None)
            if unit_filter and tx_u_id not in filters["unit_ids"]:
                continue
            if section_filter and tx_sec_id not in filters["internal_section_ids"]:
                continue
            if (unit_filter or section_filter) and not tx_u_id and not tx_sec_id:
                continue
            rows.append({
                "transaction_id": tx.transaction_number,
                "date": tx.transaction_date,
                "direction": tx.direction,
                "account": tx.account.name,
                "account_head": tx.account_head.name if tx.account_head else "",
                "sub_head": tx.sub_head.name if tx.sub_head else "",
                "unit": tx.unit.name if tx_u_id else "",
                "internal_section": tx.internal_section.name if tx_sec_id else "",
                "amount": tx.amount,
                "transaction_amount": tx.amount,
                "allocation_based": False,
            })
    return rows


def build_unit_summary(filters):
    qs = _allocation_queryset(filters)
    data = {}
    for row in qs.values("unit_id", "unit__name").annotate(total=Sum("allocated_amount")):
        key = row["unit_id"] or 0
        data[key] = {"unit": row["unit__name"] or "Unspecified Unit", "amount": row["total"] or Decimal("0.00")}

    # During migration, legacy transactions with no N3 allocation may still have
    # direct Transaction.unit attribution. Include them once, never alongside N3 rows.
    tx_qs = _active_transactions(filters).filter(organisation_allocations__isnull=True)
    if not filters.get("internal_section_ids"):
        if filters.get("unit_ids"):
            tx_qs = tx_qs.filter(unit_id__in=filters["unit_ids"])
        for row in tx_qs.values("unit_id", "unit__name").annotate(total=Sum("amount")):
            if not row["unit_id"]:
                continue
            key = row["unit_id"]
            data.setdefault(key, {"unit": row["unit__name"], "amount": Decimal("0.00")})
            data[key]["amount"] += row["total"] or Decimal("0.00")
    return sorted(data.values(), key=lambda x: x["unit"])


def build_internal_section_summary(filters):
    qs = _allocation_queryset(filters)
    data = {}
    for row in qs.values("internal_section_id", "internal_section__name").annotate(total=Sum("allocated_amount")):
        key = row["internal_section_id"] or 0
        data[key] = {"internal_section": row["internal_section__name"] or "Unspecified Section", "amount": row["total"] or Decimal("0.00")}

    # Include direct Transaction.internal_section for transactions without N3 allocation
    tx_qs = _active_transactions(filters).filter(organisation_allocations__isnull=True)
    if filters.get("internal_section_ids"):
        tx_qs = tx_qs.filter(internal_section_id__in=filters["internal_section_ids"])
    for row in tx_qs.values("internal_section_id", "internal_section__name").annotate(total=Sum("amount")):
        if not row["internal_section_id"]:
            continue
        key = row["internal_section_id"]
        data.setdefault(key, {"internal_section": row["internal_section__name"], "amount": Decimal("0.00")})
        data[key]["amount"] += row["total"] or Decimal("0.00")
    return sorted(data.values(), key=lambda x: x["internal_section"])


def build_unit_section_summary(filters):
    qs = _allocation_queryset(filters)
    data = {}
    for row in qs.values("unit_id", "unit__name", "internal_section_id", "internal_section__name").annotate(total=Sum("allocated_amount")):
        k = (row["unit__name"] or "Unspecified Unit", row["internal_section__name"] or "Unspecified Section")
        data[k] = {
            "unit": k[0],
            "internal_section": k[1],
            "amount": row["total"] or Decimal("0.00"),
        }

    # Include direct Transaction unit and internal_section combinations
    tx_qs = _active_transactions(filters).filter(organisation_allocations__isnull=True)
    if filters.get("unit_ids"):
        tx_qs = tx_qs.filter(unit_id__in=filters["unit_ids"])
    if filters.get("internal_section_ids"):
        tx_qs = tx_qs.filter(internal_section_id__in=filters["internal_section_ids"])

    for row in tx_qs.values("unit_id", "unit__name", "internal_section_id", "internal_section__name").annotate(total=Sum("amount")):
        u_name = row["unit__name"] or "Unspecified Unit"
        s_name = row["internal_section__name"] or "Unspecified Section"
        if u_name == "Unspecified Unit" and s_name == "Unspecified Section":
            continue
        k = (u_name, s_name)
        data.setdefault(k, {"unit": u_name, "internal_section": s_name, "amount": Decimal("0.00")})
        data[k]["amount"] += row["total"] or Decimal("0.00")

    return sorted(data.values(), key=lambda x: (x["unit"], x["internal_section"]))


_COMMON = ["account", "financial_year", "start_date", "end_date", "unit_ids", "internal_section_ids", "direction", "major_head", "sub_head", "account_head", "outflow_nature", "pass_through"]

registry.register(ReportDefinition(
    slug="organisational-transactions", title="Organisational Txns",
    description="Txn/allocation detail for Unit and Internal Sec analysis without double counting.",
    builder_func=build_organisational_transactions,
    columns=[
        {"key": "transaction_id", "label": "Txn ID"}, {"key": "date", "label": "Date"},
        {"key": "direction", "label": "Dir"}, {"key": "account", "label": "Acct"},
        {"key": "account_head", "label": "Acct Head"}, {"key": "sub_head", "label": "Sub Head"},
        {"key": "unit", "label": "Unit"}, {"key": "internal_section", "label": "Internal Sec"},
        {"key": "amount", "label": "Report Amount"}, {"key": "transaction_amount", "label": "Txn Amount"},
    ],
    supported_filters=_COMMON, totals=["amount", "transaction_amount"],
))

registry.register(ReportDefinition(
    slug="unit-summary", title="Unit-wise Summary",
    description="Fin totals by Unit using N3 allocation grain.",
    builder_func=build_unit_summary,
    columns=[{"key": "unit", "label": "Unit"}, {"key": "amount", "label": "Amount"}],
    supported_filters=_COMMON, totals=["amount"], display_in_millions=True,
))

registry.register(ReportDefinition(
    slug="internal-section-summary", title="Internal Sec-wise Summary",
    description="Fin totals by Internal Sec using N3 allocation grain.",
    builder_func=build_internal_section_summary,
    columns=[{"key": "internal_section", "label": "Internal Sec"}, {"key": "amount", "label": "Amount"}],
    supported_filters=_COMMON, totals=["amount"], display_in_millions=True,
))

registry.register(ReportDefinition(
    slug="unit-section-summary", title="Unit + Internal Sec Analysis",
    description="Explicit Unit and Internal Sec combinations from organisational allocations.",
    builder_func=build_unit_section_summary,
    columns=[{"key": "unit", "label": "Unit"}, {"key": "internal_section", "label": "Internal Sec"}, {"key": "amount", "label": "Amount"}],
    supported_filters=_COMMON, totals=["amount"], display_in_millions=True,
))
