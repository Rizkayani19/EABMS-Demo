import json
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase

from core.bulk_views import TransactionBulkDeleteView
from core.models import (
    Account,
    AccountHead,
    AuditLog,
    FinancialYear,
    Installation,
    Transaction,
    UserProfile,
)


class BulkTransactionDiscardTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.installation = Installation.objects.create(
            installation_code='DISCARD-TEST',
            installation_name='Discard Test Installation',
        )
        self.account = Account.objects.create(
            installation=self.installation,
            code='DISC-ACC',
            name='Discard Account',
        )
        self.fy = FinancialYear.objects.create(
            code='2025-26',
            name='FY 2025-26',
            start_date=date(2025, 7, 1),
            end_date=date(2026, 6, 30),
        )
        self.head = AccountHead.objects.create(
            account=self.account,
            name='Operations Discard',
            head_type=AccountHead.HeadType.OUTFLOW,
        )

        # Users
        self.clerk_user = User.objects.create_user(username='clerk_discard', password='x')
        UserProfile.objects.create(user=self.clerk_user, role=UserProfile.Role.CLERK)

        self.mgmt_user = User.objects.create_user(username='mgmt_discard', password='x')
        UserProfile.objects.create(user=self.mgmt_user, role=UserProfile.Role.MANAGEMENT)

        # Transactions
        self.tx1 = Transaction.objects.create(
            transaction_number='TXN-DISC-001',
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            transaction_date=date(2025, 9, 1),
            direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('5000.00'),
            is_historical=False,
            status=Transaction.Status.ACTIVE,
        )
        self.tx2 = Transaction.objects.create(
            transaction_number='TXN-DISC-002',
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            transaction_date=date(2025, 9, 2),
            direction=Transaction.Direction.INFLOW,
            amount=Decimal('10000.00'),
            is_historical=False,
            status=Transaction.Status.ACTIVE,
        )
        self.hist_tx = Transaction.objects.create(
            transaction_number='TXN-DISC-HIST',
            account=self.account,
            financial_year=self.fy,
            account_head=self.head,
            transaction_date=date(2025, 8, 15),
            direction=Transaction.Direction.OUTFLOW,
            amount=Decimal('25000.00'),
            is_historical=True,
            status=Transaction.Status.ACTIVE,
        )

    def test_json_bulk_delete_non_historical_success(self):
        view = TransactionBulkDeleteView.as_view()
        req = self.factory.post(
            '/transactions/bulk-delete/',
            data=json.dumps({'ids': [str(self.tx1.id), str(self.tx2.id)]}),
            content_type='application/json',
        )
        req.user = self.clerk_user
        req.account = self.account
        req.fy = self.fy

        resp = view(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode('utf-8'))
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('deleted_count'), 2)
        self.assertEqual(data.get('protected_count'), 0)
        self.assertIn(str(self.tx1.id), data.get('deleted_ids'))
        self.assertIn(str(self.tx2.id), data.get('deleted_ids'))

        # Check records were deleted from DB
        self.assertFalse(Transaction.objects.filter(id=self.tx1.id).exists())
        self.assertFalse(Transaction.objects.filter(id=self.tx2.id).exists())

        # Check audit log entries created
        audit_logs = AuditLog.objects.filter(action='DELETE_TRANSACTION')
        self.assertEqual(audit_logs.count(), 2)

    def test_json_bulk_delete_protects_historical_transactions(self):
        view = TransactionBulkDeleteView.as_view()
        req = self.factory.post(
            '/transactions/bulk-delete/',
            data=json.dumps({'ids': [str(self.tx1.id), str(self.hist_tx.id)]}),
            content_type='application/json',
        )
        req.user = self.clerk_user
        req.account = self.account
        req.fy = self.fy

        resp = view(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode('utf-8'))
        self.assertTrue(data.get('ok'))
        self.assertEqual(data.get('deleted_count'), 1)
        self.assertEqual(data.get('protected_count'), 1)
        self.assertIn(str(self.tx1.id), data.get('deleted_ids'))
        self.assertNotIn(str(self.hist_tx.id), data.get('deleted_ids'))

        # tx1 deleted, hist_tx remains intact
        self.assertFalse(Transaction.objects.filter(id=self.tx1.id).exists())
        self.assertTrue(Transaction.objects.filter(id=self.hist_tx.id).exists())

    def test_management_user_cannot_delete(self):
        view = TransactionBulkDeleteView.as_view()
        req = self.factory.post(
            '/transactions/bulk-delete/',
            data=json.dumps({'ids': [str(self.tx1.id)]}),
            content_type='application/json',
        )
        req.user = self.mgmt_user
        req.account = self.account
        req.fy = self.fy

        resp = view(req)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Transaction.objects.filter(id=self.tx1.id).exists())

    def test_form_post_backward_compatibility(self):
        view = TransactionBulkDeleteView.as_view()
        req = self.factory.post(
            '/transactions/bulk-delete/',
            data={'selected_ids': [str(self.tx1.id)]},
        )
        req.user = self.clerk_user
        req.account = self.account
        req.fy = self.fy
        from django.contrib.messages.storage.fallback import FallbackStorage
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        resp = view(req)
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Transaction.objects.filter(id=self.tx1.id).exists())
