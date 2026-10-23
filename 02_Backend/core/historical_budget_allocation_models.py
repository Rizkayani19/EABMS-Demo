from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class HistoricalBudgetAllocation(models.Model):
    """Explicit organisational attribution of an existing/historical BudgetLine.

    This is separate from Transaction attribution so historical budget figures are
    never inferred from narrative text or Unit master relationships. One budget line
    may be allocated across multiple Units and/or Internal Sections.
    """
    budget_line = models.ForeignKey(
        'core.BudgetLine', related_name='historical_allocations', on_delete=models.CASCADE,
    )
    unit = models.ForeignKey(
        'core.Unit', null=True, blank=True, related_name='historical_budget_allocations',
        on_delete=models.PROTECT,
    )
    internal_section = models.ForeignKey(
        'core.InternalSection', null=True, blank=True,
        related_name='historical_budget_allocations', on_delete=models.PROTECT,
    )
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit__name', 'internal_section__name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['budget_line', 'unit', 'internal_section'],
                name='uniq_hist_budget_line_org_allocation',
            ),
        ]
        verbose_name = 'Historical Budget Allocation'
        verbose_name_plural = 'Historical Budget Allocations'

    def clean(self):
        if self.allocated_amount is None or self.allocated_amount <= Decimal('0.00'):
            raise ValidationError({'allocated_amount': 'Allocated amount must be greater than zero.'})
        if self.budget_line_id:
            if self.unit_id and self.budget_line.unit_id and self.unit_id != self.budget_line.unit_id:
                raise ValidationError({'unit': 'Allocation Unit conflicts with the Budget Line Unit.'})

    def __str__(self):
        unit = self.unit.name if self.unit else 'All Units'
        section = self.internal_section.name if self.internal_section else 'All Sections'
        return f'{unit} / {section}: Rs {self.allocated_amount:,.2f}'
