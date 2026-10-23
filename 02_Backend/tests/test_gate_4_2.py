import tempfile
from io import StringIO
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.contrib.auth.models import User
from datetime import date
from decimal import Decimal

from core.models import (
    Installation, Account, FinancialYear, AccountHead,
    ImportBatch, ImportedRecord, Transaction,
    OutflowNature, BudgetType, UserProfile
)
from core.import_services import parse_import_file, validate_import_batch, execute_import_batch

class Gate42Tests(TestCase):
    def setUp(self):
        self.user_admin = User.objects.create_user(username='admin_user2', password='123')
        UserProfile.objects.create(user=self.user_admin, role=UserProfile.Role.ADMINISTRATOR)
        
        self.inst = Installation.objects.create(installation_code='INST-02', installation_name='Main')
        self.ngl = Account.objects.create(installation=self.inst, code='NGL', name='NGL Fund')
        
        self.fy26 = FinancialYear.objects.create(
            code='2026-27', name='FY 2026-27', start_date=date(2026, 7, 1), end_date=date(2027, 6, 30), status='OPEN'
        )
        
        # Masters from migration
        self.head_salaries = AccountHead.objects.create(account=self.ngl, name='Salaries', code='NGL-SAL')
        self.head_fin = AccountHead.objects.create(account=self.ngl, name='Fin Asst Indls', code='NGL-FAI')
        self.head_hqo = AccountHead.objects.create(account=self.ngl, name='Received from HQO', code='NGL-HQO')
        self.head_cap = AccountHead.objects.create(account=self.ngl, name='Capacity Enhancement Project', code='NGL-CEM')
        self.head_pass = AccountHead.objects.create(account=self.ngl, name='All pass through transactions', code='NGL-PTT')
        self.head_tea = AccountHead.objects.create(account=self.ngl, name='cafeteria', code='NGL-TEA')
        self.head_evt = AccountHead.objects.create(account=self.ngl, name='Received from Ceremony Fund Acct', code='NGL-EVT')
        self.head_trv = AccountHead.objects.create(account=self.ngl, name='Received from Umra & Haj Acct', code='NGL-TRV')
        
        self.out_addl = OutflowNature.objects.create(code='ADDL', name='Addl')
        self.out_routine = OutflowNature.objects.create(code='ROUTINE', name='Routine')

    def test_mappings(self):
        content = "Date,Amount,HeadCode,UnitType,Direction\n"
        # 1. Salaries maps to Salaries
        content += "2026-08-01,100.00,Salaries,,\n"
        # 2. Fin Asst Indis maps to Fin Asst Indls
        content += "2026-08-02,200.00,Fin Asst Indis,,\n"
        # 3. Amount Tfr from HQO maps to Received from HQO
        content += "2026-08-03,300.00,Amount Tfr from HQO,,\n"
        # 4. Capacity Enhancement Project maps to Capacity Enhancement Project
        content += "2026-08-04,400.00,Capacity Enhancement Project,,\n"
        # 5/9. Pass Through Transactions maps to All pass through transactions and pass_through=True
        content += "2026-08-05,500.00,Pass Through Transactions,Pass Through,\n"
        # 6. cafeteria maps to cafeteria
        content += "2026-08-06,600.00,cafeteria,,\n"
        # 7. Amount Tfr from EVT maps to Received from Ceremony Fund Acct
        content += "2026-08-07,700.00,Amount Tfr from EVT,,\n"
        # 8. Amount Tfr from TRV maps to Received from Umra & Haj Acct
        content += "2026-08-08,800.00,Amount Tfr from TRV,,\n"
        # 11. Addl maps to Outflow Nature Addl
        content += "2026-08-09,900.00,Salaries,Addl,\n"
        # 12. Routine maps to Outflow Nature Routine
        content += "2026-08-10,1000.00,Salaries,Routine,\n"
        # 13. Unknown values are not silently imported
        content += "2026-08-11,1100.00,Unknown Head,,\n"
        
        csv_file = SimpleUploadedFile("import.csv", content.encode('utf-8'))
        batch = ImportBatch.objects.create(
            account=self.ngl, source_file=csv_file, source_type='CSV', imported_by=self.user_admin
        )
        parse_import_file(batch)
        mapping = {'date': 'Date', 'amount': 'Amount', 'head_code': 'HeadCode', 'unit_type': 'UnitType'}
        validate_import_batch(batch, mapping)
        
        records = batch.records.order_by('original_row_number')
        
        # Test 1-8, 11, 12 should be valid
        for i in range(10):
            self.assertEqual(records[i].validation_status, 'VALID', f"Row {i} failed: {records[i].error_message}")
            
        # Test 13
        self.assertEqual(records[10].validation_status, 'INVALID')
        self.assertIn("Unknown Account Head", records[10].error_message)
        
        # Now execute and check db attributes
        execute_import_batch(batch, mapping)
        
        # 9. Pass Through check
        txn_pass = Transaction.objects.get(account_head=self.head_pass)
        self.assertTrue(txn_pass.pass_through)
        
        # 11/12 Outflow check
        txn_addl = Transaction.objects.get(transaction_date=date(2026, 8, 9))
        self.assertEqual(txn_addl.outflow_nature, self.out_addl)
        
        txn_routine = Transaction.objects.get(transaction_date=date(2026, 8, 10))
        self.assertEqual(txn_routine.outflow_nature, self.out_routine)
        
    def test_reimbursement_is_not_budget_type(self):
        # 10. Reimbursement is not a BudgetType
        self.assertFalse(BudgetType.objects.filter(name__iexact='Reimbursement').exists())
