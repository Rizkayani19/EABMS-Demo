from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .future_budget_allocation_models import FutureBudgetAllocation


class FutureBudgetAllocationService:
    """Canonical service for organisational Future Budget allocations."""

    @staticmethod
    def _validate_parent(allocation_or_line):
        line = getattr(allocation_or_line, "future_budget_line", allocation_or_line)
        if not getattr(line, "pk", None) or not line.future_budget_id:
            raise ValidationError("A persisted Future Budget line is required.")
        return line

    @staticmethod
    def _validate_organisation(line, unit=None, internal_section=None):
        if unit is None and internal_section is None:
            raise ValidationError("An allocation requires a Unit, Internal Section, or both.")
        account_id = line.future_budget.account_id
        # Organisational masters are intentionally global. They are therefore
        # validated for structural compatibility here rather than given an
        # artificial Account FK.
        if unit is not None and not getattr(unit, "pk", None):
            raise ValidationError("Unit must be a persisted organisational master.")
        if internal_section is not None and not getattr(internal_section, "pk", None):
            raise ValidationError("Internal Section must be a persisted organisational master.")
        return account_id

    @staticmethod
    def target_amount(line):
        """Return the amount against which allocations should reconcile."""
        if line.approved_amount is not None:
            return Decimal(line.approved_amount)
        if line.user_proposed is not None:
            return Decimal(line.user_proposed)
        return Decimal(line.system_suggested or Decimal("0.00"))

    @classmethod
    def totals(cls, line):
        line = cls._validate_parent(line)
        total = line.allocations.aggregate(total=Sum("allocated_amount"))["total"] or Decimal("0.00")
        target = cls.target_amount(line)
        difference = (target - total).quantize(Decimal("0.01"))
        return {
            "target": target,
            "allocated": Decimal(total).quantize(Decimal("0.01")),
            "difference": difference,
            "status": "RECONCILED" if difference == Decimal("0.00") else "UNRECONCILED",
        }

    @classmethod
    @transaction.atomic
    def allocate(cls, line, amount, actor=None, unit=None, internal_section=None, justification="", remarks=""):
        line = cls._validate_parent(line)
        cls._validate_organisation(line, unit, internal_section)
        amount = Decimal(str(amount))
        if amount <= Decimal("0.00"):
            raise ValidationError("Allocated amount must be greater than zero.")
        allocation = FutureBudgetAllocation(
            future_budget_line=line,
            unit=unit,
            internal_section=internal_section,
            allocated_amount=amount,
            justification=justification,
            remarks=remarks,
            created_by=actor,
            updated_by=actor,
        )
        allocation.full_clean()
        allocation.save()
        return allocation

    @classmethod
    @transaction.atomic
    def update_allocation(cls, allocation, amount=None, actor=None, unit=None, internal_section=None, justification=None, remarks=None):
        line = cls._validate_parent(allocation)
        unit = allocation.unit if unit is None else unit
        internal_section = allocation.internal_section if internal_section is None else internal_section
        cls._validate_organisation(line, unit, internal_section)
        if amount is not None:
            allocation.allocated_amount = Decimal(str(amount))
        allocation.unit = unit
        allocation.internal_section = internal_section
        if justification is not None:
            allocation.justification = justification
        if remarks is not None:
            allocation.remarks = remarks
        allocation.updated_by = actor
        allocation.full_clean()
        allocation.save()
        return allocation

    @classmethod
    @transaction.atomic
    def remove_allocation(cls, allocation):
        cls._validate_parent(allocation)
        allocation.delete()

    @classmethod
    def reconcile(cls, line):
        return cls.totals(line)
