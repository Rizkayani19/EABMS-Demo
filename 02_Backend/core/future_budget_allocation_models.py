from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class FutureBudgetAllocation(models.Model):
    """True monetary allocation of a future-budget line to Units and/or Internal Sections.

    This is deliberately separate from transaction attribution. The amount stored here
    is a real future-budget allocation and must reconcile to the selected parent amount.
    """
    future_budget_line = models.ForeignKey(
        'core.FutureBudgetLine', related_name='allocations', on_delete=models.CASCADE,
    )
    unit = models.ForeignKey(
        'core.Unit', null=True, blank=True, related_name='future_budget_allocations',
        on_delete=models.PROTECT,
    )
    internal_section = models.ForeignKey(
        'core.InternalSection', null=True, blank=True,
        related_name='future_budget_allocations', on_delete=models.PROTECT,
    )
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2)
    justification = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'auth.User', null=True, blank=True,
        related_name='future_budget_allocations_created', on_delete=models.SET_NULL,
    )
    updated_by = models.ForeignKey(
        'auth.User', null=True, blank=True,
        related_name='future_budget_allocations_updated', on_delete=models.SET_NULL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['unit__name', 'internal_section__name', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['future_budget_line', 'unit', 'internal_section'],
                name='uniq_future_budget_line_org_allocation',
            ),
        ]
        verbose_name = 'Future Budget Allocation'
        verbose_name_plural = 'Future Budget Allocations'

    def clean(self):
        if self.allocated_amount is None or self.allocated_amount <= Decimal('0.00'):
            raise ValidationError({'allocated_amount': 'Allocated amount must be greater than zero.'})

    def __str__(self):
        unit = self.unit.name if self.unit else 'All Units'
        section = self.internal_section.name if self.internal_section else 'All Sections'
        return f'{unit} / {section}: Rs {self.allocated_amount:,.2f}'
