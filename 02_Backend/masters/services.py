from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from .models import TransactionOrganisationAllocation


def validate_transaction_organisation_allocations(transaction):
    """Validate final organisational allocation total before a workflow commits.

    Individual allocation rows may be entered incrementally. At the transaction
    entry/import/admin commit boundary, the completed allocation set must equal
    the authoritative transaction amount exactly.
    """
    total = (
        TransactionOrganisationAllocation.objects
        .filter(transaction=transaction)
        .aggregate(total=Sum('allocated_amount'))['total']
        or Decimal('0.00')
    )
    if total != transaction.amount:
        raise ValidationError(
            f'Organisational allocation total Rs {total:,.2f} must equal '
            f'transaction amount Rs {transaction.amount:,.2f}.'
        )
    return total
