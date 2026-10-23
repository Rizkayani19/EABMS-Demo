from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import AuditLog, FinancialYear


def validate_opening_balance_edit(*, opening_balance, new_amount):
    if opening_balance.is_confirmed and new_amount != opening_balance.balance_amount:
        raise ValidationError("Confirmed Opening Balance cannot be changed directly. Use a controlled correction.")


def confirm_opening_balance(*, opening_balance, actor=None):
    if opening_balance.is_confirmed:
        return opening_balance
    opening_balance.is_confirmed = True
    opening_balance.confirmed_by = actor if actor and actor.is_authenticated else None
    opening_balance.confirmed_at = timezone.now()
    opening_balance.save(update_fields=["is_confirmed", "confirmed_by", "confirmed_at", "updated_at"])
    AuditLog.objects.create(
        actor=actor if actor and actor.is_authenticated else None,
        account=opening_balance.account,
        action="CONFIRM_OPENING_BALANCE",
        model_name="OpeningBalance",
        record_id=str(opening_balance.pk),
        record_repr=str(opening_balance)[:255],
        old_values={"is_confirmed": False},
        new_values={"is_confirmed": True, "confirmed_at": opening_balance.confirmed_at.isoformat()},
    )
    return opening_balance


def validate_financial_year_is_open(financial_year):
    if financial_year.status != FinancialYear.Status.OPEN:
        raise ValidationError("Financial Year is closed or archived. New financial mutations are not permitted.")
    return financial_year


def validate_financial_record_period(*, financial_year, transaction_date=None):
    validate_financial_year_is_open(financial_year)
    if transaction_date and not (financial_year.start_date <= transaction_date <= financial_year.end_date):
        raise ValidationError("Transaction date must fall within the selected Financial Year.")
    return financial_year
