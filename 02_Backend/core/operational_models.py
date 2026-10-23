"""Operational finance models retained for the day-to-day ABMS application.

These models were part of the original transaction/import/document/reimbursement
workflow. They are kept in a compatibility module so the newer canonical budget
models can evolve independently while the operational application remains intact.

ReimbursementType and DocumentType remain canonical models in core.models. The
operational models below reference those existing models rather than redefining them.
"""
from decimal import Decimal
import uuid

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class Reimbursement(models.Model):
    class Status(models.TextChoices):
        EXPECTED = 'EXPECTED', 'Expected'
        PARTIALLY_RECEIVED = 'PARTIALLY_RECEIVED', 'Partially Received'
        FULLY_RECEIVED = 'FULLY_RECEIVED', 'Fully Received'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reimbursement_type = models.ForeignKey(
        'core.ReimbursementType',
        on_delete=models.PROTECT,
        related_name='reimbursements',
    )
    original_outflow = models.ForeignKey(
        'core.Transaction',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='expected_reimbursements',
    )
    received_inflow = models.OneToOneField(
        'core.Transaction',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='received_reimbursement',
    )
    expected_amount = models.DecimalField(max_digits=18, decimal_places=2)
    received_amount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal('0.00'))
    expected_date = models.DateField()
    received_date = models.DateField(null=True, blank=True)
    source = models.CharField(max_length=255)
    reference = models.CharField(max_length=255, blank=True)
    document_reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.EXPECTED, db_index=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='created_reimbursements')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-expected_date', '-created_at']
        verbose_name = 'Reimbursement'
        verbose_name_plural = 'Reimbursements'

    def __str__(self):
        return f'Reimbursement {self.id} - Expected: Rs {self.expected_amount:,.2f}'

    @property
    def pending_amount(self):
        return self.expected_amount - self.received_amount

    def clean(self):
        if self.received_amount > self.expected_amount:
            raise ValidationError({'received_amount': 'Received amount cannot exceed expected amount.'})
        if self.original_outflow and self.original_outflow.direction != 'OUTFLOW':
            raise ValidationError({'original_outflow': 'Original transaction must be an Outflow.'})
        if self.received_inflow and self.received_inflow.direction != 'INFLOW':
            raise ValidationError({'received_inflow': 'Received transaction must be an Inflow.'})


class Document(models.Model):
    document_type = models.ForeignKey('core.DocumentType', on_delete=models.RESTRICT)
    file = models.FileField(upload_to='documents/%Y/%m/')
    file_name = models.CharField(max_length=255)
    reference_no = models.CharField(max_length=100, null=True, blank=True)
    document_date = models.DateField(null=True, blank=True)
    financial_year = models.ForeignKey('core.FinancialYear', null=True, blank=True, on_delete=models.RESTRICT)
    description = models.TextField(null=True, blank=True)
    uploaded_by = models.ForeignKey(User, on_delete=models.RESTRICT)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True)


class DocumentLink(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='links')
    entity_type = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=50)
    created_by = models.ForeignKey(User, on_delete=models.RESTRICT)
    created_at = models.DateTimeField(auto_now_add=True)


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft/Pending'
        PREVIEWED = 'PREVIEWED', 'Previewed'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    account = models.ForeignKey('core.Account', on_delete=models.RESTRICT)
    source_file = models.FileField(upload_to='imports/%Y/%m/')
    source_type = models.CharField(max_length=20)
    imported_by = models.ForeignKey(User, on_delete=models.RESTRICT)
    import_date = models.DateTimeField(auto_now_add=True)
    total_rows = models.IntegerField(default=0)
    imported_rows = models.IntegerField(default=0)
    failed_rows = models.IntegerField(default=0)
    duplicate_rows = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    remarks = models.TextField(null=True, blank=True)
    # Added in migration 0017: SHA-256 fingerprint of the source file for duplicate-import prevention
    source_hash = models.CharField(max_length=64, blank=True, db_index=True)


class ImportedRecord(models.Model):
    class Status(models.TextChoices):
        VALID = 'VALID', 'Valid'
        INVALID = 'INVALID', 'Invalid'
        DUPLICATE = 'DUPLICATE', 'Duplicate'
        IMPORTED = 'IMPORTED', 'Imported'

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name='records')
    original_row_number = models.IntegerField()
    row_data = models.JSONField()
    validation_status = models.CharField(max_length=20, choices=Status.choices)
    error_message = models.TextField(null=True, blank=True)
    duplicate_status = models.BooleanField(default=False)
    target_transaction = models.ForeignKey('core.Transaction', null=True, blank=True, on_delete=models.SET_NULL)
    # Added in migration 0017: SHA-256 fingerprint of a single row for per-row duplicate detection
    row_hash = models.CharField(max_length=64, blank=True, db_index=True)

