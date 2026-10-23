"""Regression tests for transaction validation and user-facing error handling."""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse

from core.models import Account, AccountHead, FinancialYear, UserProfile, Transaction


User = get_user_model()


class TransactionValidationUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_eabms_corporate', verbosity=0)
        cls.account = Account.objects.get(code='NGL')
        cls.fy_2025, _ = FinancialYear.objects.get_or_create(
            code='2025-26',
            defaults={
                'name': 'FY 2025-26',
                'start_date': '2025-07-01',
                'end_date': '2026-06-30',
                'status': 'OPEN',
            }
        )
        cls.admin, _ = User.objects.get_or_create(username='validation-ui-admin')
        cls.admin.set_password('testpass123')
        cls.admin.is_staff = True
        cls.admin.save(update_fields=['password', 'is_staff'])
        UserProfile.objects.update_or_create(
            user=cls.admin,
            defaults={
                'role': UserProfile.Role.ADMINISTRATOR,
                'default_account': cls.account,
            },
        )
        cls.account_head = AccountHead.objects.filter(
            account=cls.account,
            is_active=True,
            head_type__in=[AccountHead.HeadType.INFLOW, AccountHead.HeadType.BOTH],
        ).first()

    def client_for_fy(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session['active_account_id'] = str(self.account.id)
        session['active_fy_id'] = str(self.fy_2025.id)
        session.save()
        return client

    def test_invalid_inflow_date_is_returned_as_form_error_not_500(self):
        self.assertIsNotNone(self.account_head, 'Seed data must contain an active inflow Account Head.')
        client = self.client_for_fy()
        before = Transaction.objects.count()

        response = client.post(
            reverse('core:inflow_create'),
            {
                'transaction_date': '2026-08-30',
                'account_head': self.account_head.id,
                'amount': '250000',
                'description': 'FY validation regression test',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), before)
        form = response.context['form']
        expected = (
            'Transaction date 30-Aug-2026 is outside the selected Financial Year '
            '(2025-26). Enter a date between 01-Jul-2025 and 30-Jun-2026.'
        )
        self.assertIn(expected, form.errors['transaction_date'])
        self.assertContains(response, 'Please correct the errors before saving:')
        self.assertContains(response, expected)
