import json
from decimal import Decimal
from datetime import date

from django.test import TestCase, Client
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import (
    Account,
    AccountHead,
    FinancialYear,
    InflowType,
    MajorHead,
    OutflowNature,
    SubHead,
    Transaction,
    Unit,
    UserProfile,
)

User = get_user_model()


class BulkTransactionEditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_eabms_corporate', verbosity=0)

        cls.account = Account.objects.get(code='NGL')
        cls.fy = FinancialYear.objects.get(code='2026-27')

        cls.major_head = MajorHead.objects.filter(account=cls.account).first()
        cls.account_head = AccountHead.objects.filter(account=cls.account).first()
        cls.sub_head = SubHead.objects.filter(account=cls.account).first()
        cls.unit = Unit.objects.first()
        cls.nature = OutflowNature.objects.first()
        cls.inflow_type = InflowType.objects.first()

        # Users
        cls.admin_user = User.objects.get(username='admin')
        cls.clerk_user = User.objects.get(username='clerk')
        cls.mgmt_user = User.objects.get(username='management')

        # Create a non-historical test transaction
        cls.tx = Transaction.objects.create(
            account=cls.account,
            financial_year=cls.fy,
            transaction_number='TX-TEST-001',
            transaction_date=date(2026, 8, 15),
            direction=Transaction.Direction.OUTFLOW,
            account_head=cls.account_head,
            sub_head=cls.sub_head,
            major_head=cls.major_head,
            unit=cls.unit,
            outflow_nature=cls.nature,
            amount=Decimal('15000.00'),
            payee_or_source='Alpha Suppliers',
            description='Office Stationeries batch 1',
            status=Transaction.Status.ACTIVE,
            is_historical=False,
            created_by=cls.admin_user,
        )

        # Create a historical transaction (should be protected)
        cls.hist_tx = Transaction.objects.create(
            account=cls.account,
            financial_year=cls.fy,
            transaction_number='TX-HIST-001',
            transaction_date=date(2026, 8, 10),
            direction=Transaction.Direction.OUTFLOW,
            account_head=cls.account_head,
            amount=Decimal('50000.00'),
            is_historical=True,
            created_by=cls.admin_user,
        )

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.admin_user)
        session = self.client.session
        session['active_account_id'] = self.account.id
        session['active_fy_id'] = self.fy.id
        session.save()

    def test_bulk_edit_view_renders_cleanly(self):
        res = self.client.get(reverse('core:transaction_bulk_edit'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Bulk Transaction Grid')
        self.assertContains(res, 'TX-TEST-001')
        self.assertNotContains(res, 'TX-HIST-001')  # Historical excluded

    def test_bulk_save_updates_existing_transaction(self):
        payload = {
            'rows': [
                {
                    'id': str(self.tx.id),
                    'transaction_date': '20-08-2026',
                    'direction': 'OUTFLOW',
                    'amount': '25000.00',
                    'payee_or_source': 'Alpha Suppliers Updated',
                    'account_head_id': self.account_head.id,
                    'sub_head_id': self.sub_head.id if self.sub_head else None,
                    'major_head_id': self.major_head.id if self.major_head else None,
                    'unit_id': self.unit.id if self.unit else None,
                    'nature_id': self.nature.id if self.nature else None,
                    'reference': 'CHQ-9988',
                    'description': 'Updated description batch',
                    'status': 'ACTIVE',
                }
            ]
        }

        res = self.client.post(
            reverse('core:transaction_bulk_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('updated_count'), 1)

        self.tx.refresh_from_db()
        self.assertEqual(self.tx.amount, Decimal('25000.00'))
        self.assertEqual(self.tx.payee_or_source, 'Alpha Suppliers Updated')
        self.assertEqual(self.tx.transaction_date, date(2026, 8, 20))
        self.assertEqual(self.tx.reference, 'CHQ-9988')

    def test_bulk_save_creates_new_transaction_row(self):
        payload = {
            'rows': [
                {
                    'id': '',  # Blank ID indicates new row
                    'transaction_date': '22-08-2026',
                    'direction': 'INFLOW',
                    'amount': '75000.00',
                    'payee_or_source': 'Govt Grants Receipt',
                    'account_head_id': self.account_head.id,
                    'sub_head_id': None,
                    'major_head_id': None,
                    'unit_id': None,
                    'inflow_type_id': self.inflow_type.id if self.inflow_type else None,
                    'reference': 'GRT-2026-01',
                    'description': 'Special grant funding',
                    'status': 'ACTIVE',
                }
            ]
        }

        res = self.client.post(
            reverse('core:transaction_bulk_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        if res.status_code != 200:
            print("ERROR IN TEST:", res.json())
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('created_count'), 1)

        new_tx = Transaction.objects.filter(payee_or_source='Govt Grants Receipt').first()
        self.assertIsNotNone(new_tx)
        self.assertEqual(new_tx.amount, Decimal('75000.00'))
        self.assertEqual(new_tx.direction, Transaction.Direction.INFLOW)

    def test_historical_transaction_cannot_be_modified(self):
        payload = {
            'rows': [
                {
                    'id': str(self.hist_tx.id),
                    'transaction_date': '20-08-2026',
                    'direction': 'OUTFLOW',
                    'amount': '999999.00',
                    'account_head_id': self.account_head.id,
                    'status': 'ACTIVE',
                }
            ]
        }

        res = self.client.post(
            reverse('core:transaction_bulk_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)
        self.hist_tx.refresh_from_db()
        self.assertEqual(self.hist_tx.amount, Decimal('50000.00'))  # Unchanged

    def test_rbac_management_user_view_only_and_save_forbidden(self):
        self.client.force_login(self.mgmt_user)
        session = self.client.session
        session['active_account_id'] = self.account.id
        session['active_fy_id'] = self.fy.id
        session.save()

        # GET should load in view-only mode (can_edit = False)
        res_get = self.client.get(reverse('core:transaction_bulk_edit'))
        self.assertEqual(res_get.status_code, 200)
        self.assertContains(res_get, 'Management access is view-only')

        # POST to save should be forbidden
        payload = {'rows': [{'id': str(self.tx.id), 'transaction_date': '20-08-2026', 'amount': '20000.00'}]}
        res_post = self.client.post(
            reverse('core:transaction_bulk_save'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res_post.status_code, 403)
