from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from core.future_budget_allocation_models import FutureBudgetAllocation
from core.future_budget_allocation_services import (
    allocation_reconciliation,
    get_parent_target,
    save_allocation,
    validate_allocations,
)
from core.models import (
    Account,
    AccountHead,
    FinancialYear,
    FutureBudget,
    FutureBudgetLine,
    InternalSection,
    Installation,
    Unit,
)


class FutureBudgetAllocationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('budget_test', password='test')
        self.installation = Installation.objects.create(installation_code='TEST-01', installation_name='Test')
        self.account = Account.objects.create(installation=self.installation, code='TST', name='Test Account')
        self.source_fy = FinancialYear.objects.create(
            code='FY25-26', name='FY 2025-26', start_date='2025-07-01', end_date='2026-06-30', status='CLOSED'
        )
        self.target_fy = FinancialYear.objects.create(
            code='FY26-27', name='FY 2026-27', start_date='2026-07-01', end_date='2027-06-30', status='OPEN'
        )
        self.head = AccountHead.objects.create(account=self.account, name='Test Head', head_type='OUTFLOW')
        self.section = InternalSection.objects.create(code='PS-TEST', name='PS-Test')
        self.unit = Unit.objects.create(code='UNIT-TEST', name='Unit Test')
        self.future_budget = FutureBudget.objects.create(
            account=self.account, source_fy=self.source_fy, target_fy=self.target_fy, created_by=self.user
        )
        self.line = FutureBudgetLine.objects.create(
            future_budget=self.future_budget,
            account_head=self.head,
            system_suggested=Decimal('100000.00'),
        )

    def test_parent_target_prefers_approved_then_proposed_then_system(self):
        self.assertEqual(get_parent_target(self.line), Decimal('100000.00'))
        self.line.user_proposed = Decimal('110000.00')
        self.line.save(update_fields=['user_proposed'])
        self.assertEqual(get_parent_target(self.line), Decimal('110000.00'))
        self.line.approved_amount = Decimal('105000.00')
        self.line.save(update_fields=['approved_amount'])
        self.assertEqual(get_parent_target(self.line), Decimal('105000.00'))

    def test_multiple_unit_section_allocations_reconcile_exactly(self):
        save_allocation(line=self.line, amount='40000', unit=self.unit, user=self.user)
        save_allocation(line=self.line, amount='60000', internal_section=self.section, user=self.user)
        result = allocation_reconciliation(self.line)
        self.assertEqual(result['allocated'], Decimal('100000.00'))
        self.assertTrue(result['is_reconciled'])
        self.assertEqual(validate_allocations(self.line)['difference'], Decimal('0.00'))

    def test_unreconciled_allocations_are_rejected_by_service(self):
        save_allocation(line=self.line, amount='40000', unit=self.unit, user=self.user)
        result = allocation_reconciliation(self.line)
        self.assertEqual(result['difference'], Decimal('-60000.00'))
        with self.assertRaises(ValidationError):
            validate_allocations(self.line)

    def test_allocation_is_real_amount_not_transaction_attribution(self):
        allocation = FutureBudgetAllocation.objects.create(
            future_budget_line=self.line,
            unit=self.unit,
            internal_section=self.section,
            allocated_amount=Decimal('100000.00'),
        )
        self.assertEqual(allocation.allocated_amount, Decimal('100000.00'))
        self.assertEqual(allocation.future_budget_line_id, self.line.id)
