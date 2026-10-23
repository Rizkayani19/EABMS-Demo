from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models


class BudgetInflowLine(models.Model):
    """Dedicated inflow-side budget plan, kept separate from legacy outflow BudgetLine."""

    budget = models.ForeignKey(
        'core.Budget', on_delete=models.CASCADE, related_name='inflow_lines'
    )
    account_head = models.ForeignKey(
        'core.AccountHead', on_delete=models.PROTECT, null=True, blank=True, related_name='inflow_budget_lines'
    )
    major_head = models.ForeignKey(
        'core.MajorHead', on_delete=models.PROTECT, null=True, blank=True, related_name='inflow_budget_lines'
    )
    unit = models.ForeignKey(
        'core.Unit', on_delete=models.PROTECT, null=True, blank=True, related_name='inflow_budget_lines'
    )
    budget_type = models.ForeignKey(
        'core.BudgetType', on_delete=models.PROTECT, related_name='inflow_budget_lines'
    )
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['budget', 'account_head', 'major_head']
        verbose_name = 'Inflow Budget Line'
        verbose_name_plural = 'Inflow Budget Lines'
        constraints = [
            models.UniqueConstraint(
                fields=['budget', 'account_head', 'budget_type', 'unit'],
                condition=models.Q(account_head__isnull=False),
                name='unique_inflow_budget_line_with_unit',
            ),
            models.UniqueConstraint(
                fields=['budget', 'account_head', 'budget_type'],
                condition=models.Q(account_head__isnull=False, unit__isnull=True),
                name='unique_inflow_budget_line_without_unit',
            ),
            models.UniqueConstraint(
                fields=['budget', 'major_head', 'budget_type', 'unit'],
                condition=models.Q(account_head__isnull=True, major_head__isnull=False),
                name='unique_inflow_budget_line_sf_with_unit',
            ),
            models.UniqueConstraint(
                fields=['budget', 'major_head', 'budget_type'],
                condition=models.Q(account_head__isnull=True, major_head__isnull=False, unit__isnull=True),
                name='unique_inflow_budget_line_sf_without_unit',
            ),
        ]

    def __str__(self):
        head_name = self.account_head.name if self.account_head else (self.major_head.name if self.major_head else 'Unnamed')
        btype = self.budget_type.name if self.budget_type else 'Inflow'
        return f'{head_name} - {btype}: Rs {self.amount:,.2f}'

    def clean(self):
        if not self.account_head and not self.major_head:
            raise ValidationError("Either Account Head or Sub-Fund must be specified for an Inflow Budget Line.")
        if self.budget_id and self.account_head_id:
            if self.account_head.account_id != self.budget.account_id:
                raise ValidationError({'account_head': "Account Head must belong to the Budget's Account."})
            if self.account_head.head_type not in ('INFLOW', 'BOTH'):
                raise ValidationError({'account_head': 'This Account Head is not enabled for inflows.'})
        if self.budget_id and self.major_head_id:
            if self.major_head.account_id != self.budget.account_id:
                raise ValidationError({'major_head': "Sub-Fund must belong to the Budget's Account."})
        if self.amount is not None and self.amount < 0:
            raise ValidationError({'amount': 'Inflow budget amount cannot be negative.'})
