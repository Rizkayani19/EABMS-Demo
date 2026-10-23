"""Regression tests for explicit management inputs in future-budget planning."""
from decimal import Decimal

from django.test import TestCase

from core.future_budget_services import build_future_budget_lines, get_future_budget_summary
from core.future_budget_management_models import FutureBudgetManagementInput
from core.models import Account, AccountHead, FinancialYear, FutureBudget, InternalSection, Unit


class FutureBudgetManagementInputTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        account = Account.objects.create(code='MBI', name='Management Input Test')
        source = FinancialYear.objects.create(
            code='MBI-25', name='FY MBI 2025-26', start_date='2025-07-01',
            end_date='2026-06-30', status=FinancialYear.Status.CLOSED,
        )
        target = FinancialYear.objects.create(
            code='MBI-26', name='FY MBI 2026-27', start_date='2026-07-01',
            end_date='2027-06-30', status=FinancialYear.Status.OPEN,
        )
        head = AccountHead.objects.create(account=account, code='MBI-R', name='Routine Requirement')
        new_head = AccountHead.objects.create(account=account, code='MBI-N', name='New Management Requirement')
        unit = Unit.objects.create(code='MBI-U', name='MBI Unit')
        section = InternalSection.objects.create(code='MBI-S', name='MBI Section')
        future = FutureBudget.objects.create(
            account=account, source_fy=source, target_fy=target,
            routine_adjustment_pct=Decimal('10.00'),
        )
        cls.future = future
        cls.head = head
        cls.new_head = new_head
        cls.unit = unit
        cls.section = section

    def test_active_continuing_and_additional_inputs_are_separate(self):
        FutureBudgetManagementInput.objects.create(
            future_budget=self.future, account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.CONTINUING,
            description='Continuing requirement', amount=Decimal('10000.00'),
            justification='Required for next FY continuation',
            status=FutureBudgetManagementInput.Status.ACTIVE,
        ).units.add(self.unit)
        additional = FutureBudgetManagementInput.objects.create(
            future_budget=self.future, account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL,
            description='Additional requirement', amount=Decimal('25000.00'),
            justification='Approved management requirement',
            status=FutureBudgetManagementInput.Status.ACTIVE,
        )
        additional.units.add(self.unit)
        additional.internal_sections.add(self.section)
        FutureBudgetManagementInput.objects.create(
            future_budget=self.future, account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL,
            description='Draft requirement', amount=Decimal('90000.00'),
            justification='Not yet approved',
            status=FutureBudgetManagementInput.Status.DRAFT,
        )

        build_future_budget_lines(self.future)
        line = self.future.lines.get(account_head=self.head)
        self.assertEqual(line.continuing_amount, Decimal('10000.00'))
        self.assertEqual(line.addl_amount, Decimal('0.00'))
        self.assertEqual(line.system_suggested, Decimal('35000.00'))

        summary = get_future_budget_summary(self.future)
        self.assertEqual(summary['management_continuing_total'], Decimal('10000.00'))
        self.assertEqual(summary['management_additional_total'], Decimal('25000.00'))

    def test_management_input_can_create_new_future_requirement_without_historical_actual(self):
        FutureBudgetManagementInput.objects.create(
            future_budget=self.future, account_head=self.new_head,
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL,
            description='New requirement with no historical actual', amount=Decimal('50000.00'),
            justification='Genuinely new requirement for target FY',
            status=FutureBudgetManagementInput.Status.ACTIVE,
        )

        build_future_budget_lines(self.future)
        line = self.future.lines.get(account_head=self.new_head)
        self.assertEqual(line.previous_actual, Decimal('0.00'))
        self.assertEqual(line.addl_amount, Decimal('0.00'))
        self.assertEqual(line.system_suggested, Decimal('50000.00'))

    def test_management_input_organisational_attribution_is_preserved(self):
        row = FutureBudgetManagementInput.objects.create(
            future_budget=self.future, account_head=self.head,
            input_type=FutureBudgetManagementInput.InputType.ADDITIONAL,
            description='Multi-organisation requirement', amount=Decimal('12000.00'),
            justification='Requirement applies to more than one organisation',
            status=FutureBudgetManagementInput.Status.ACTIVE,
        )
        row.units.add(self.unit)
        row.internal_sections.add(self.section)
        self.assertEqual(list(row.units.values_list('name', flat=True)), ['MBI Unit'])
        self.assertEqual(list(row.internal_sections.values_list('name', flat=True)), ['MBI Section'])
