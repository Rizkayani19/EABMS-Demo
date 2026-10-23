import uuid
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from decimal import Decimal


class Installation(models.Model):
    installation_code = models.CharField(max_length=50, unique=True, default='INST-01', db_index=True, help_text="e.g. INST-01")
    installation_name = models.CharField(max_length=150, default='ABMS Main Installation')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['installation_code']
        verbose_name = "Installation"
        verbose_name_plural = "Installations"
    def __str__(self):
        return f"{self.installation_name} ({self.installation_code})"

class Account(models.Model):
    class BudgetAllocationBasis(models.TextChoices):
        ACCOUNT_HEAD = 'ACCOUNT_HEAD', 'Account Head'
        SUB_FUND = 'SUB_FUND', 'Sub-Fund'

    installation = models.ForeignKey(Installation, on_delete=models.PROTECT, related_name='accounts', null=True, blank=True)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=150, unique=True)
    short_name = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    budget_allocation_basis = models.CharField(
        max_length=20,
        choices=BudgetAllocationBasis.choices,
        default=BudgetAllocationBasis.ACCOUNT_HEAD,
        help_text="Primary budget allocation level: Sub-Fund (MajorHead) or Account Head."
    )
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Account"
        verbose_name_plural = "Accounts"
    def __str__(self):
        return f"{self.name} ({self.code})"

class FinancialYear(models.Model):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        CLOSED = 'CLOSED', 'Closed'
        ARCHIVED = 'ARCHIVED', 'Archived'
    code = models.CharField(max_length=20, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-start_date', 'display_order']
        verbose_name = "Financial Year"
        verbose_name_plural = "Financial Years"
    def __str__(self):
        return f"{self.name} [{self.get_status_display()}]"
    @property
    def is_active(self): return self.status == self.Status.OPEN
    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date.")

class InternalSection(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Department"
        verbose_name_plural = "Departments"
    def __str__(self): return self.name

class Unit(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    managed_by_sections = models.ManyToManyField(InternalSection, blank=True, related_name='managed_units', help_text='Responsible Departments for this Organisation.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Organisation"
        verbose_name_plural = "Organisations"
    def __str__(self): return self.name

class MajorHead(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='major_heads', null=True, blank=True)
    code = models.CharField(max_length=50, blank=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Division"
        verbose_name_plural = "Divisions"
    def __str__(self):
        acc_str = f" [{self.account.code}]" if self.account else ""
        return f"{self.name}{acc_str}"

class SubHead(models.Model):
    account_head = models.ForeignKey('AccountHead', on_delete=models.SET_NULL, related_name='sub_heads', null=True, blank=True, help_text="Parent Account Head (Tier 2)")
    major_head = models.ForeignKey(MajorHead, on_delete=models.PROTECT, related_name='sub_heads', null=True, blank=True, help_text="Parent Sub Fund (Tier 1)")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='sub_heads', null=True, blank=True)
    code = models.CharField(max_length=50, blank=True, db_index=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Sub Head"
        verbose_name_plural = "Sub Heads"
    def __str__(self):
        parent_str = f" ({self.account_head.name})" if self.account_head else (f" ({self.major_head.name})" if self.major_head else "")
        return f"{self.name}{parent_str}"

class InflowType(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='inflow_types', null=True, blank=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Inflow Type"
        verbose_name_plural = "Inflow Types"
    def __str__(self):
        acc_str = f" [{self.account.code}]" if self.account else ""
        return f"{self.name}{acc_str}"

class OutflowNature(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='outflow_natures', null=True, blank=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_pass_through = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Outflow Nature"
        verbose_name_plural = "Outflow Natures"
    def __str__(self):
        acc_str = f" [{self.account.code}]" if self.account else ""
        return f"{self.name}{acc_str}"


class BudgetType(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Budget Type"
        verbose_name_plural = "Budget Types"
    def __str__(self): return self.name

class ReimbursementType(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Reimbursement Type"
        verbose_name_plural = "Reimbursement Types"
    def __str__(self): return self.name

class DocumentType(models.Model):
    code = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Document Type"
        verbose_name_plural = "Document Types"
    def __str__(self): return self.name

class PersonnelClassification(models.Model):
    code = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['display_order', 'name']
        verbose_name = "Personnel Classification"
        verbose_name_plural = "Personnel Classifications"
    def __str__(self): return self.name

class AccountHead(models.Model):
    class HeadType(models.TextChoices):
        OUTFLOW = 'OUTFLOW', 'Outflow'
        INFLOW = 'INFLOW', 'Inflow'
        BOTH = 'BOTH', 'Both'
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='account_heads')
    major_head = models.ForeignKey(MajorHead, on_delete=models.SET_NULL, related_name='account_heads', null=True, blank=True)
    sub_head = models.ForeignKey(SubHead, on_delete=models.SET_NULL, related_name='account_heads', null=True, blank=True)
    code = models.CharField(max_length=50, blank=True)
    name = models.CharField(max_length=150)
    head_type = models.CharField(max_length=20, choices=HeadType.choices, default=HeadType.OUTFLOW)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    display_order = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = [('account', 'major_head', 'name')]
        ordering = ['account', 'display_order', 'name']
        verbose_name = "Account Head"
        verbose_name_plural = "Account Heads"
    def __str__(self): return f"{self.name} [{self.account.code}]"

class OpeningBalance(models.Model):
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='opening_balances')
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.PROTECT, related_name='opening_balances')
    balance_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    reference = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)
    document_reference = models.CharField(max_length=255, blank=True)
    is_confirmed = models.BooleanField(default=False)
    confirmed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='confirmed_opening_balances')
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_opening_balances')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = [('account', 'financial_year')]
        ordering = ['account', '-financial_year__start_date']
        verbose_name = "Opening Balance"
        verbose_name_plural = "Opening Balances"
    def __str__(self):
        status = "Confirmed" if self.is_confirmed else "Unconfirmed"
        return f"{self.account.code} - {self.financial_year.code}: Rs {self.balance_amount:,.2f} ({status})"

class AuditLog(models.Model):
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_logs')
    account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL, related_name='audit_logs')
    action = models.CharField(max_length=50, db_index=True)
    model_name = models.CharField(max_length=100, db_index=True)
    record_id = models.CharField(max_length=100)
    record_repr = models.CharField(max_length=255, blank=True)
    old_values = models.JSONField(null=True, blank=True)
    new_values = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"{self.timestamp:%Y-%m-%d %H:%M} | {actor_name} | {self.action} on {self.model_name} #{self.record_id}"

class UserProfile(models.Model):
    class Role(models.TextChoices):
        ADMINISTRATOR = 'ADMINISTRATOR', 'Administrator'
        CLERK = 'CLERK', 'Clerk'
        MANAGEMENT = 'MANAGEMENT', 'Management'
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CLERK)
    default_account = models.ForeignKey(Account, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = "User Profile"
        verbose_name_plural = "User Profiles"
    def __str__(self): return f"{self.user.username} ({self.get_role_display()})"

class Budget(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        APPROVED = 'APPROVED', 'Approved'
        CANCELLED = 'CANCELLED', 'Cancelled'
        CLOSED = 'CLOSED', 'Closed'
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='budgets')
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.PROTECT, related_name='budgets')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    budget_allocation_basis = models.CharField(
        max_length=20,
        choices=Account.BudgetAllocationBasis.choices,
        default=Account.BudgetAllocationBasis.ACCOUNT_HEAD,
        help_text="Primary budget allocation level: Sub-Fund (MajorHead) or Account Head."
    )
    reference = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_budgets')
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_budgets')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['account', '-financial_year__start_date']
        verbose_name = "Budget"
        verbose_name_plural = "Budgets"
        unique_together = [('account', 'financial_year')]
    @property
    def total_amount(self):
        from django.db.models import Sum
        return self.lines.aggregate(t=Sum('amount'))['t'] or Decimal('0.00')
    def __str__(self): return f"Budget {self.account.code} - {self.financial_year.code} [{self.get_status_display()}]"

class BudgetLine(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE, related_name='lines')
    account_head = models.ForeignKey(AccountHead, on_delete=models.PROTECT, null=True, blank=True, related_name='budget_lines')
    major_head = models.ForeignKey(MajorHead, on_delete=models.PROTECT, null=True, blank=True, related_name='budget_lines')
    sub_head = models.ForeignKey(SubHead, on_delete=models.PROTECT, null=True, blank=True, related_name='budget_lines')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, related_name='budget_lines')
    budget_type = models.ForeignKey(BudgetType, on_delete=models.PROTECT, related_name='budget_lines')
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['budget', 'account_head', 'major_head']
        verbose_name = "Budget Line"
        verbose_name_plural = "Budget Lines"
        constraints = [
            models.UniqueConstraint(fields=['budget', 'account_head', 'budget_type', 'unit'], condition=models.Q(account_head__isnull=False), name='unique_budget_line_with_unit'),
            models.UniqueConstraint(fields=['budget', 'account_head', 'budget_type'], condition=models.Q(account_head__isnull=False, unit__isnull=True), name='unique_budget_line_without_unit'),
            models.UniqueConstraint(fields=['budget', 'major_head', 'budget_type', 'unit'], condition=models.Q(account_head__isnull=True, major_head__isnull=False), name='unique_budget_line_sf_with_unit'),
            models.UniqueConstraint(fields=['budget', 'major_head', 'budget_type'], condition=models.Q(account_head__isnull=True, major_head__isnull=False, unit__isnull=True), name='unique_budget_line_sf_without_unit'),
        ]
    def __str__(self):
        head_name = self.account_head.name if self.account_head else (self.major_head.name if self.major_head else 'Unnamed')
        btype = self.budget_type.name if self.budget_type else 'Routine'
        return f"{head_name} - {btype}: Rs {self.amount:,.2f}"
    def clean(self):
        if not self.account_head and not self.major_head:
            raise ValidationError("Either Account Head or Sub-Fund must be specified for a Budget Line.")
        if self.budget and self.account_head and self.account_head.account != self.budget.account:
            raise ValidationError({"account_head": "Account Head must belong to the Budget's Account."})
        if self.budget and self.major_head and self.major_head.account != self.budget.account:
            raise ValidationError({"major_head": "Sub-Fund must belong to the Budget's Account."})
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "Budget amount cannot be negative."})

class BudgetRevision(models.Model):
    budget_line = models.ForeignKey(BudgetLine, on_delete=models.CASCADE, related_name='revisions', null=True, blank=True)
    previous_amount = models.DecimalField(max_digits=18, decimal_places=2)
    revised_amount = models.DecimalField(max_digits=18, decimal_places=2)
    difference = models.DecimalField(max_digits=18, decimal_places=2)
    reason = models.TextField()
    reference = models.CharField(max_length=255, blank=True)
    revised_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='budget_revisions')
    revised_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ['-revised_at']
        verbose_name = "Budget Revision"
        verbose_name_plural = "Budget Revisions"
    def __str__(self): return f"Revision for {self.budget_line} at {self.revised_at:%Y-%m-%d %H:%M}"

class FutureBudget(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PROPOSED = 'PROPOSED', 'Proposed'
        APPROVED = 'APPROVED', 'Approved'
        CLOSED = 'CLOSED', 'Closed'
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='future_budgets')
    target_fy = models.ForeignKey(FinancialYear, related_name='future_budgets_target', on_delete=models.PROTECT)
    source_fy = models.ForeignKey(FinancialYear, related_name='future_budgets_source', on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    budget_allocation_basis = models.CharField(
        max_length=20,
        choices=Account.BudgetAllocationBasis.choices,
        default=Account.BudgetAllocationBasis.ACCOUNT_HEAD,
        help_text="Primary budget allocation level: Sub-Fund (MajorHead) or Account Head."
    )
    personnel_revision_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    routine_adjustment_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    reference = models.CharField(max_length=100, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, related_name='future_budgets_created', on_delete=models.SET_NULL, null=True)
    updated_by = models.ForeignKey(User, related_name='future_budgets_updated', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = [['account', 'target_fy', 'source_fy']]
        ordering = ['-created_at']
    def __str__(self): return f'Future Budget {self.account} → {self.target_fy} (from {self.source_fy})'

class FutureBudgetLine(models.Model):
    future_budget = models.ForeignKey(FutureBudget, related_name='lines', on_delete=models.CASCADE)
    account_head = models.ForeignKey('AccountHead', null=True, blank=True, on_delete=models.PROTECT)
    major_head = models.ForeignKey('MajorHead', null=True, blank=True, on_delete=models.PROTECT)
    sub_head = models.ForeignKey('SubHead', null=True, blank=True, on_delete=models.SET_NULL)
    budget_type = models.ForeignKey('BudgetType', null=True, blank=True, on_delete=models.SET_NULL)
    previous_budget = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    previous_actual = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    routine_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    continuing_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    addl_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    onetime_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    known_change_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    personnel_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    system_suggested = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    suggestion_breakdown = models.JSONField(default=dict, blank=True)
    routine_evidence = models.TextField(blank=True)
    is_routine = models.BooleanField(default=False)
    is_addl = models.BooleanField(default=False)
    is_onetime = models.BooleanField(default=False)
    continuing_flag = models.CharField(max_length=50, blank=True)
    user_proposed = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    approved_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    approved_inflow_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    justification = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['future_budget', 'account_head'], condition=models.Q(account_head__isnull=False), name='unique_future_budget_head'),
            models.UniqueConstraint(fields=['future_budget', 'major_head'], condition=models.Q(account_head__isnull=True, major_head__isnull=False), name='unique_future_budget_sf'),
        ]
        ordering = ['account_head__name', 'major_head__name']
    def __str__(self):
        head_name = self.account_head.name if self.account_head else (self.major_head.name if self.major_head else 'Unnamed')
        return f'{head_name} — Suggested: {self.system_suggested}'

class FutureBudgetKnownChange(models.Model):
    class ChangeType(models.TextChoices):
        NEW = 'NEW', 'New Requirement'
        DISCONTINUED = 'DISCONTINUED', 'Discontinued Requirement'
        PRICE_INCREASE = 'PRICE_INCREASE', 'Price Increase'
        POLICY = 'POLICY', 'Policy Change'
        PROJECT = 'PROJECT', 'Planned Project'
        PERSONNEL = 'PERSONNEL', 'Personnel Change'
        OTHER = 'OTHER', 'Other'
    future_budget = models.ForeignKey(FutureBudget, related_name='known_changes', on_delete=models.CASCADE)
    account_head = models.ForeignKey('AccountHead', null=True, blank=True, on_delete=models.SET_NULL)
    description = models.CharField(max_length=300)
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    justification = models.TextField(blank=True)
    reference = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(User, related_name='+', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'{self.get_change_type_display()}: {self.description}'

class FutureBudgetPersonnel(models.Model):
    future_budget = models.ForeignKey(FutureBudget, related_name='personnel_lines', on_delete=models.CASCADE)
    category_label = models.CharField(max_length=100)
    current_annual_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    revision_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0.00'))
    revision_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    new_personnel_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    transferred_personnel_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    projected_cost = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def save(self, *args, **kwargs):
        self.revision_amount = (self.current_annual_cost * self.revision_pct / Decimal('100')).quantize(Decimal('0.01'))
        self.projected_cost = (self.current_annual_cost + self.revision_amount + self.new_personnel_cost + self.transferred_personnel_cost).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)
    def __str__(self): return f'{self.category_label}: Projected {self.projected_cost}'

class Transaction(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        ACTIVE = 'ACTIVE', 'Active'
        CANCELLED = 'CANCELLED', 'Cancelled'
        SOFT_DELETED = 'SOFT_DELETED', 'Soft Deleted'
    class Direction(models.TextChoices):
        INFLOW = 'INFLOW', 'Inflow'
        OUTFLOW = 'OUTFLOW', 'Outflow'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_number = models.CharField(max_length=50, unique=True, db_index=True)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='transactions')
    financial_year = models.ForeignKey(FinancialYear, on_delete=models.PROTECT, related_name='transactions')
    account_head = models.ForeignKey(AccountHead, on_delete=models.PROTECT, related_name='transactions')
    major_head = models.ForeignKey(MajorHead, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    sub_head = models.ForeignKey(SubHead, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    internal_section = models.ForeignKey(InternalSection, on_delete=models.PROTECT, null=True, blank=True, related_name='primary_transactions')
    transaction_units = models.ManyToManyField(Unit, blank=True, related_name='attributed_transactions')
    transaction_sections = models.ManyToManyField(InternalSection, blank=True, related_name='attributed_transactions')
    transaction_date = models.DateField(db_index=True)
    direction = models.CharField(max_length=10, choices=Direction.choices, db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    inflow_type = models.ForeignKey(InflowType, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    outflow_nature = models.ForeignKey(OutflowNature, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions')
    cohort = models.ForeignKey('masters.Cohort', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    package = models.ForeignKey('masters.CohortPackage', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    pilgrim = models.ForeignKey('masters.Pilgrim', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    tour_operator = models.ForeignKey('masters.TourOperator', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    ceremony_event = models.ForeignKey('masters.CeremonyEvent', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    ceremony_venue = models.ForeignKey('masters.CeremonyVenue', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')

    pass_through = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    purpose = models.TextField(blank=True)
    payee_or_source = models.TextField(blank=True)
    reference = models.TextField(blank=True)
    document_reference = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    remarks = models.TextField(blank=True)
    is_historical = models.BooleanField(default=False)
    deleted_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='soft_deleted_transactions')
    deleted_at = models.DateTimeField(null=True, blank=True)
    deletion_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_transactions')
    updated_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_transactions')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['-transaction_date', '-created_at']
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
    def __str__(self): return f"{self.transaction_number} - {self.get_direction_display()} - Rs {self.amount:,.2f}"
    def clean(self):
        from datetime import date as date_type
        if self.financial_year_id and self.transaction_date:
            try:
                fy = self.financial_year
                tx_date = self.transaction_date
                if isinstance(tx_date, str):
                    parts = tx_date.split('-')
                    tx_date = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
                fy_start = fy.start_date
                if isinstance(fy_start, str):
                    parts = fy_start.split('-')
                    fy_start = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
                fy_end = fy.end_date
                if isinstance(fy_end, str):
                    parts = fy_end.split('-')
                    fy_end = date_type(int(parts[0]), int(parts[1]), int(parts[2]))
                if not (fy_start <= tx_date <= fy_end):
                    raise ValidationError({"transaction_date": "Transaction date must be within the selected Financial Year."})
            except self.__class__.financial_year.RelatedObjectDoesNotExist:
                pass
        if self.account_id and self.account_head_id:
            try:
                if self.account_head.account_id != self.account_id:
                    raise ValidationError({"account_head": "Account Head does not belong to the selected Account."})
            except (self.__class__.account.RelatedObjectDoesNotExist, self.__class__.account_head.RelatedObjectDoesNotExist):
                pass
        # Pass-through is a transaction characteristic valid for both directions
        if self.financial_year_id and not self.is_historical:
            try:
                fy = self.financial_year
                if fy.status != fy.Status.OPEN:
                    raise ValidationError({"financial_year": "Financial Year is closed or archived. New financial mutations are not permitted."})
            except self.__class__.financial_year.RelatedObjectDoesNotExist:
                pass
        from decimal import Decimal as _Decimal, InvalidOperation
        if self.amount is not None:
            try:
                self.amount = _Decimal(str(self.amount))
            except InvalidOperation:
                pass
            if self.amount <= 0:
                raise ValidationError({"amount": "Transaction amount must be strictly positive."})
    def save(self, *args, **kwargs):
        if self.direction == self.Direction.OUTFLOW and not self.pass_through:
            try:
                ah_name = (self.account_head.name if self.account_head else '').lower()
                nat_name = (self.outflow_nature.name if self.outflow_nature else '').lower()
                if 'pass' in ah_name or 'pass' in nat_name:
                    self.pass_through = True
            except Exception:
                pass
        if not self.transaction_number:
            import uuid as _uuid
            prefix_parts = []
            if self.account_id:
                try:
                    prefix_parts.append(self.account.installation.installation_code)
                    prefix_parts.append(self.account.code)
                except Exception:
                    pass
            prefix_parts.append('TXN')
            prefix = '-'.join(prefix_parts)
            self.transaction_number = f"{prefix}-{str(_uuid.uuid4()).replace('-', '')[:12].upper()}"
        self.clean()
        super().save(*args, **kwargs)

from .operational_models import (
    Reimbursement,
    Document,
    DocumentLink,
    ImportBatch,
    ImportedRecord,
)
