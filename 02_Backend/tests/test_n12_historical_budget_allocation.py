from decimal import Decimal

from django.test import TestCase

from core.budget_analysis_services import build_existing_organisational_analysis
from core.historical_budget_allocation_models import HistoricalBudgetAllocation
from core.models import (
    Account,
    AccountHead,
    Budget,
    BudgetLine,
    BudgetType,
    FinancialYear,
    Installation,
    InternalSection,
    Transaction,
    Unit,
)


class N12HistoricalBudgetAllocationTests(TestCase):
    def setUp(self):
        installation = Installation.objects.create(installation_code='N12-TEST', installation_name='N12 Test')
        self.account = Account.objects.create(installation=installation, code='N12', name='N12 Test Account')
        self.fy = FinancialYear.objects.create(code='N12-2526', name='FY 2025-26', start_date='2025-07-01', end_date='2026-06-30')
        self.head = AccountHead.objects.create(account=self.account, code='H1', name='Test Head')
        self.budget_type = BudgetType.objects.create(code='N12-BT', name='N12 Budget')
        self.unit_a = Unit.objects.create(code='N12-A', name='N12 Unit A')
        self.unit_b = Unit.objects.create(code='N12-B', name='N12 Unit B')
        self.evt = InternalSection.objects.create(code='N12-EVT', name='N12 EVT')
        self.coord = InternalSection.objects.create(code='N12-COORD', name='N12 Coordination')
        self.budget = Budget.objects.create(account=self.account, financial_year=self.fy, status=Budget.Status.APPROVED)
        self.line = BudgetLine.objects.create(
            budget=self.budget,
            account_head=self.head,
            unit=self.unit_a,
            budget_type=self.budget_type,
            amount=Decimal('100000.00'),
        )

    def test_budget_line_can_be_explicitly_split_across_units_and_sections(self):
        HistoricalBudgetAllocation.objects.create(
            budget_line=self.line, unit=self.unit_a, internal_section=self.evt, allocated_amount=Decimal('60000.00')
        )
        HistoricalBudgetAllocation.objects.create(
            budget_line=self.line, unit=self.unit_b, internal_section=self.coord, allocated_amount=Decimal('40000.00')
        )
        result = build_existing_organisational_analysis(self.account, self.fy)
        self.assertEqual(result['section_budget_total'], Decimal('100000.00'))
        self.assertEqual(
            {(r['unit'], r['internal_section'], r['budget']) for r in result['matrix_rows']},
            {
                ('N12 Unit A', 'N12 EVT', Decimal('60000.00')),
                ('N12 Unit B', 'N12 Coordination', Decimal('40000.00')),
            },
        )

    def test_no_section_budget_is_invented_from_unit_management_relationship(self):
        self.unit_a.managed_by_sections.add(self.evt)
        result = build_existing_organisational_analysis(self.account, self.fy)
        self.assertFalse(result['historical_section_budget_available'])
        self.assertEqual(result['section_budget_total'], Decimal('0.00'))

    def test_actuals_remain_transaction_ssot_and_section_filter_works(self):
        Transaction.objects.create(
            transaction_number='N12-TX-1',
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            unit=self.unit_a,
            internal_section=self.evt,
            transaction_date='2025-08-01',
            direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('25000.00'),
            status=Transaction.Status.ACTIVE,
        )
        Transaction.objects.create(
            transaction_number='N12-TX-2',
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            unit=self.unit_b,
            internal_section=self.coord,
            transaction_date='2025-08-02',
            direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('10000.00'),
            status=Transaction.Status.ACTIVE,
        )
        result = build_existing_organisational_analysis(self.account, self.fy, internal_sections=['N12 EVT'])
        self.assertEqual(result['section_actual_total'], Decimal('25000.00'))
        self.assertEqual(result['unit_actual_total'], Decimal('25000.00'))
