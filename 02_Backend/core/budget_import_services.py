import csv
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Account, AccountHead, Budget, BudgetLine, BudgetType, FinancialYear
from .import_services import apply_ngl_head_mapping


MILLION = Decimal("1000000")


def _decimal_millions(value):
    text = str(value or "").strip().replace(",", "")
    if not text:
        return Decimal("0.00")
    try:
        return Decimal(text)
    except (InvalidOperation, TypeError) as exc:
        raise ValidationError(f"Invalid budget amount: {value!r}") from exc


def parse_ngl_budget_analysis_csv(file_path):
    """Parse the real NGL 2025-26 analysis CSV into outflow budget rows.

    The source workbook is a management-analysis sheet, not a normalized ABMS
    budget import format. Only the OUTFLOW HEADS section and its Budget column
    are imported. Values are stored in ABMS as rupees after million conversion.
    """
    rows = []
    section = None

    with open(file_path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, start=1):
            cells = [str(cell or "").strip() for cell in row]
            first = cells[0] if cells else ""

            if first.upper() == "OUTFLOW HEADS (RANKED HIGHEST TO LOWEST)":
                section = "OUTFLOW"
                continue
            if first.upper() == "INFLOW HEADS (RANKED HIGHEST TO LOWEST)":
                section = "INFLOW"
                continue
            if section != "OUTFLOW" or not first:
                continue
            if first.upper() == "TOTAL":
                continue

            # Expected source layout:
            # Head, Inflow Total, Inflow Avg/Month, Outflow Budget, Outflow Actual,
            # Variance, Net Position, Addl/Unforeseen Exp
            if len(cells) < 4:
                continue

            budget_millions = _decimal_millions(cells[3])
            rows.append(
                {
                    "source_row": row_number,
                    "legacy_head": first,
                    "budget_millions": budget_millions,
                    "budget_amount": (budget_millions * MILLION).quantize(Decimal("0.01")),
                    "remarks": cells[7] if len(cells) > 7 else "",
                }
            )
    return rows


def validate_ngl_budget_rows(rows, account):
    errors = []
    validated = []
    seen_heads = set()

    for row in rows:
        mapped_name = apply_ngl_head_mapping(row["legacy_head"])
        head = AccountHead.objects.filter(
            account=account,
            is_active=True,
            name__iexact=mapped_name,
        ).first()

        if not head:
            errors.append(
                f"Row {row['source_row']}: unknown Account Head "
                f"{row['legacy_head']!r} (mapped to {mapped_name!r})."
            )
            continue

        if head.id in seen_heads:
            errors.append(
                f"Row {row['source_row']}: duplicate Account Head {head.name!r}."
            )
            continue

        if row["budget_amount"] < 0:
            errors.append(
                f"Row {row['source_row']}: budget cannot be negative."
            )
            continue

        seen_heads.add(head.id)
        validated.append({**row, "account_head": head})

    return validated, errors


def import_ngl_budget(
    file_path,
    account,
    financial_year,
    budget_type,
    *,
    status=Budget.Status.DRAFT,
    reference="",
    remarks="Imported from NGL Budget 2025-26 analysis CSV.",
    user=None,
):
    source_rows = parse_ngl_budget_analysis_csv(file_path)
    validated, errors = validate_ngl_budget_rows(source_rows, account)
    if errors:
        raise ValidationError({"budget_import": errors})
    if not validated:
        raise ValidationError("No valid OUTFLOW budget rows were found.")

    if Budget.objects.filter(account=account, financial_year=financial_year).exists():
        raise ValidationError(
            f"A Budget already exists for {account.code} / {financial_year.code}."
        )

    source_total = sum((row["budget_amount"] for row in validated), Decimal("0.00"))

    with transaction.atomic():
        budget = Budget.objects.create(
            account=account,
            financial_year=financial_year,
            status=status,
            reference=reference,
            remarks=remarks,
            created_by=user,
        )

        for row in validated:
            head = row["account_head"]
            BudgetLine.objects.create(
                budget=budget,
                account_head=head,
                major_head=head.major_head,
                sub_head=head.sub_head,
                unit=None,
                budget_type=budget_type,
                amount=row["budget_amount"],
                remarks=(
                    f"Imported source row {row['source_row']}. "
                    f"{row['remarks']}".strip()
                ),
            )

    return {
        "budget": budget,
        "source_row_count": len(source_rows),
        "imported_line_count": len(validated),
        "source_total": source_total,
        "budget_total": budget.total_amount,
        "difference": budget.total_amount - source_total,
        "rows": validated,
    }


def resolve_budget_type(code_or_name):
    value = str(code_or_name or "").strip()
    if not value:
        raise ValidationError("Budget Type is required.")
    return (
        BudgetType.objects.filter(is_active=True, code__iexact=value).first()
        or BudgetType.objects.filter(is_active=True, name__iexact=value).first()
    )


def resolve_account(code):
    return Account.objects.get(code=code)


def resolve_financial_year(code):
    return FinancialYear.objects.get(code=code)
