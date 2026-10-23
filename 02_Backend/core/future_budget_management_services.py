from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from .future_budget_management_models import FutureBudgetManagementInput

ZERO = Decimal('0.00')


def active_management_inputs(future_budget, account_head=None, input_type=None):
    qs = FutureBudgetManagementInput.objects.filter(
        future_budget=future_budget,
        status=FutureBudgetManagementInput.Status.ACTIVE,
    )
    if account_head is not None:
        qs = qs.filter(account_head=account_head)
    if input_type is not None:
        qs = qs.filter(input_type=input_type)
    return qs


def management_input_totals(future_budget, account_head=None):
    """Return explicit management amounts without mixing them with historical actuals."""
    qs = active_management_inputs(future_budget, account_head=account_head)
    rows = qs.values('input_type').annotate(total=Sum('amount'))
    totals = {
        FutureBudgetManagementInput.InputType.CONTINUING: ZERO,
        FutureBudgetManagementInput.InputType.ADDITIONAL: ZERO,
        FutureBudgetManagementInput.InputType.OTHER: ZERO,
    }
    for row in rows:
        totals[row['input_type']] = row['total'] or ZERO
    return totals


def validate_management_input(instance):
    """Run model validation plus explicit business checks used by UI/import layers."""
    instance.full_clean()
    if instance.status == FutureBudgetManagementInput.Status.ACTIVE and not instance.justification.strip():
        raise ValidationError({'justification': 'An active management input requires justification.'})
    return instance


def save_management_input(*, future_budget, account_head, input_type, description,
                          amount, justification, user=None, units=None,
                          internal_sections=None, reference='', effective_date=None,
                          end_date=None, status=FutureBudgetManagementInput.Status.DRAFT,
                          remarks=''):
    """Create one explicit management requirement with optional multi-org attribution."""
    instance = FutureBudgetManagementInput(
        future_budget=future_budget,
        account_head=account_head,
        input_type=input_type,
        description=description,
        amount=amount,
        justification=justification,
        reference=reference,
        effective_date=effective_date,
        end_date=end_date,
        status=status,
        remarks=remarks,
        created_by=user,
        updated_by=user,
    )
    validate_management_input(instance)
    instance.save()
    if units is not None:
        instance.units.set(units)
    if internal_sections is not None:
        instance.internal_sections.set(internal_sections)
    return instance


def management_input_breakdown(future_budget):
    """Return report-ready rows, retaining Unit and Section attribution."""
    rows = []
    for item in active_management_inputs(future_budget).select_related('account_head'):
        rows.append({
            'id': item.pk,
            'account_head': item.account_head.name,
            'input_type': item.get_input_type_display(),
            'amount': item.amount,
            'description': item.description,
            'justification': item.justification,
            'reference': item.reference,
            'units': list(item.units.values_list('name', flat=True)),
            'internal_sections': list(item.internal_sections.values_list('name', flat=True)),
            'effective_date': item.effective_date,
            'end_date': item.end_date,
        })
    return rows
