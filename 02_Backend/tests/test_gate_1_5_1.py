from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Account, FinancialYear, AccountHead, BudgetType, Budget, BudgetLine, BudgetRevision, Installation
from decimal import Decimal
from datetime import date

class BudgetMasterCorrectionTests(TestCase):
    def setUp(self):
        self.inst = Installation.objects.create(installation_code='INST-01', installation_name='Main')
        self.ngl = Account.objects.create(installation=self.inst, code='NGL', name='NGL Fund')
        self.fy = FinancialYear.objects.create(
            code='2026-27', name='FY 2026-27', start_date=date(2026, 7, 1), end_date=date(2027, 6, 30)
        )
        self.head = AccountHead.objects.create(account=self.ngl, name='Utility', code='NGL-01')
        self.user = User.objects.create_user(username='clerk', password='123')

        # Create budget types as defined in Gate 1.5.1
        self.type_routine = BudgetType.objects.create(code='ROUTINE', name='Routine')
        self.type_addl = BudgetType.objects.create(code='ADDL', name='Addl')
    def test_budget_creation_and_status(self):
        """Test Budget model supports Gate 1.5.1 controlled states."""
        budget = Budget.objects.create(
            account=self.ngl,
            financial_year=self.fy,
            status=Budget.Status.APPROVED
        )
        bl = BudgetLine.objects.create(
            budget=budget,
            account_head=self.head,
            budget_type=self.type_routine,
            amount=Decimal('500000.00')
        )
        self.assertEqual(budget.status, 'APPROVED')
        self.assertEqual(bl.amount, Decimal('500000.00'))

    def test_budget_revision_history(self):
        """Test BudgetRevision captures historical tracking."""
        budget = Budget.objects.create(
            account=self.ngl,
            financial_year=self.fy,
            status=Budget.Status.APPROVED
        )
        bl = BudgetLine.objects.create(
            budget=budget,
            account_head=self.head,
            budget_type=self.type_routine,
            amount=Decimal('500000.00')
        )

        revision = BudgetRevision.objects.create(
            budget_line=bl,
            previous_amount=bl.amount,
            revised_amount=Decimal('600000.00'),
            difference=Decimal('100000.00'),
            reason="Additional requirement approved",
            reference="Auth-001"
        )
        
        bl.amount = revision.revised_amount
        bl.save()

        self.assertEqual(bl.revisions.count(), 1)
        self.assertEqual(bl.amount, Decimal('600000.00'))
        self.assertEqual(bl.revisions.first().difference, Decimal('100000.00'))
