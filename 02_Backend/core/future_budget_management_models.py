from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models

from .models import AccountHead, FutureBudget, InternalSection, Unit


class FutureBudgetManagementInput(models.Model):
    """Explicit management input used to shape a future-budget proposal.

    This is deliberately separate from historical actuals and from the system
    suggestion.  It records what management says should continue or be added.
    Unit/section attribution is optional and many-to-many because a requirement
    may legitimately span several organisations.
    """

    class InputType(models.TextChoices):
        CONTINUING = "CONTINUING", "Continuing Requirement"
        ADDITIONAL = "ADDITIONAL", "Additional Requirement"
        OTHER = "OTHER", "Other Management Input"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        REJECTED = "REJECTED", "Rejected"
        CLOSED = "CLOSED", "Closed"

    future_budget = models.ForeignKey(
        FutureBudget, on_delete=models.CASCADE, related_name="management_inputs"
    )
    account_head = models.ForeignKey(
        AccountHead, on_delete=models.PROTECT, related_name="future_budget_management_inputs"
    )
    input_type = models.CharField(max_length=20, choices=InputType.choices)
    description = models.CharField(max_length=300)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    justification = models.TextField()
    reference = models.CharField(max_length=255, blank=True)
    effective_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    units = models.ManyToManyField(Unit, blank=True, related_name="future_budget_management_inputs")
    internal_sections = models.ManyToManyField(
        InternalSection, blank=True, related_name="future_budget_management_inputs"
    )
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="future_budget_management_inputs_created"
    )
    updated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="future_budget_management_inputs_updated"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["input_type", "account_head__name", "-created_at"]
        indexes = [
            models.Index(fields=["future_budget", "input_type", "status"]),
            models.Index(fields=["future_budget", "account_head", "status"]),
        ]

    def clean(self):
        if self.amount is not None and self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Management input amount must be greater than zero."})
        if self.end_date and self.effective_date and self.end_date < self.effective_date:
            raise ValidationError({"end_date": "End date cannot be before effective date."})
        if self.account_head_id and self.future_budget_id:
            if self.account_head.account_id != self.future_budget.account_id:
                raise ValidationError({"account_head": "Account Head must belong to the Future Budget's Account."})

    def __str__(self):
        return f"{self.get_input_type_display()}: {self.account_head.name} — Rs {self.amount:,.2f}"


class FutureBudgetDecisionHistory(models.Model):
    """Immutable record of management proposal/approval decisions for both sides."""

    class Action(models.TextChoices):
        PROPOSE = "PROPOSE", "Proposed"
        APPROVE = "APPROVE", "Approved"
        REJECT = "REJECT", "Proposal Rejected"
        REOPEN = "REOPEN", "Approval Reopened"

    future_budget_line = models.ForeignKey(
        "core.FutureBudgetLine",
        on_delete=models.PROTECT,
        related_name="decision_history",
    )
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="future_budget_decision_history",
    )
    previous_proposed = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    new_proposed = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    previous_proposed_inflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    new_proposed_inflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    previous_approved = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    new_approved = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    previous_approved_inflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    new_approved_inflow = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    system_suggested_snapshot = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    reason = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["future_budget_line", "created_at"]),
            models.Index(fields=["future_budget_line", "action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} — Future Budget Line {self.future_budget_line_id}"
