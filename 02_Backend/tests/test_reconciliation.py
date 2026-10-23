from django.test import TestCase, Client
from core.models import FinancialYear, OpeningBalance, Account
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()

class ReconciliationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user('test', 'test@test.com', 'test')
        self.client.force_login(self.user)
        self.account = Account.objects.create(code='NGL', name='NGL')
        self.fy1 = FinancialYear.objects.create(code='2025-26', name='FY1', start_date='2025-07-01', end_date='2026-06-30')
        self.fy2 = FinancialYear.objects.create(code='2026-27', name='FY2', start_date='2026-07-01', end_date='2027-06-30')
        OpeningBalance.objects.create(account=self.account, financial_year=self.fy1, balance_amount=Decimal('100.00'))

    def test_view_loads(self):
        session = self.client.session
        session['active_account_id'] = self.account.id
        session['active_fy_id'] = self.fy2.id
        session.save()
        
        response = self.client.get('/reconcile-balance/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Opening Balances')
        self.assertContains(response, '100.00')

