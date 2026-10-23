from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from decimal import Decimal
from datetime import date
from core.models import (
    Installation, Account, FinancialYear, Unit, InternalSection,
    MajorHead, InflowType, OutflowNature, BudgetType, ReimbursementType,
    DocumentType, PersonnelClassification, AccountHead, OpeningBalance, UserProfile
)


class Command(BaseCommand):
    help = "Seeds corporate master data for EABMS — NexGen Holdings Ltd. (NGL), Employee Welfare Fund (EWF), Corporate Provident Fund (CPF)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting EABMS Corporate Master Seeding..."))

        with transaction.atomic():
            # ── 1. Installation ──────────────────────────────────────────────
            inst, _ = Installation.objects.get_or_create(
                installation_code='EABMS-01',
                defaults={
                    'installation_name': 'EABMS Corporate Installation',
                    'description': 'Enterprise Accounts & Business Management System — Primary Installation',
                    'is_active': True,
                }
            )
            self.stdout.write(self.style.SUCCESS(f"  [OK] Installation: {inst.installation_name}"))

            # ── 2. Three Corporate Accounts ──────────────────────────────────
            ngl, _ = Account.objects.get_or_create(
                code='NGL',
                defaults={
                    'installation': inst,
                    'name': 'NexGen Holdings Ltd.',
                    'short_name': 'NGL',
                    'description': 'NexGen Holdings Ltd. — Primary corporate operating account',
                    'budget_allocation_basis': 'ACCOUNT_HEAD',
                    'is_active': True,
                    'display_order': 1,
                }
            )
            ngl.installation = inst
            ngl.budget_allocation_basis = 'ACCOUNT_HEAD'
            ngl.save()

            ewf, _ = Account.objects.get_or_create(
                code='EWF',
                defaults={
                    'installation': inst,
                    'name': 'Employee Welfare Fund',
                    'short_name': 'EWF',
                    'description': 'Employee Welfare Fund — Benefits, housing, medical & recreation',
                    'budget_allocation_basis': 'SUB_FUND',
                    'is_active': True,
                    'display_order': 2,
                }
            )
            ewf.installation = inst
            ewf.budget_allocation_basis = 'SUB_FUND'
            ewf.save()

            cpf, _ = Account.objects.get_or_create(
                code='CPF',
                defaults={
                    'installation': inst,
                    'name': 'Corporate Provident Fund',
                    'short_name': 'CPF',
                    'description': 'Corporate Provident Fund — Retirement contributions & investment returns',
                    'budget_allocation_basis': 'SUB_FUND',
                    'is_active': True,
                    'display_order': 3,
                }
            )
            cpf.installation = inst
            cpf.budget_allocation_basis = 'SUB_FUND'
            cpf.save()

            self.stdout.write(self.style.SUCCESS("  [OK] 3 Corporate Accounts seeded: NGL, EWF, CPF"))

            # ── 3. Financial Year 2026-27 ────────────────────────────────────
            fy, _ = FinancialYear.objects.get_or_create(
                code='2026-27',
                defaults={
                    'name': 'FY 2026-27',
                    'start_date': date(2026, 7, 1),
                    'end_date': date(2027, 6, 30),
                    'status': FinancialYear.Status.OPEN,
                    'display_order': 1,
                }
            )
            self.stdout.write(self.style.SUCCESS(f"  [OK] Financial Year: {fy.name}"))

            # ── 4. Outflow Natures ───────────────────────────────────────────
            outflow_natures = [
                ('ROUTINE',      'Routine',               'Recurring operational expenditure',              False, 1),
                ('ADDL',         'Additional',            'Additional expenditure outside normal budget',    False, 2),
                ('CONTINUING',   'Continuing Requirement','Expenditure continuing into next FY',             False, 3),
                ('NEW',          'New Requirement',       'New expenditure not previously established',      False, 4),
                ('PASS_THROUGH', 'Pass-Through',          'Transfer-through clearing expenditure',           True,  5),
                ('OTHER',        'Other',                 'General / unclassified outflow',                 False, 6),
            ]
            for code, name, desc, pt, order in outflow_natures:
                OutflowNature.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'is_pass_through': pt, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Outflow Natures seeded"))

            # ── 5. Inflow Types ──────────────────────────────────────────────
            inflow_types = [
                ('DIRECT',        'Direct Credit',         'Direct bank receipt / credit advice',           1),
                ('PROFIT',        'Bank Profit',           'Monthly profit on running account',             2),
                ('TRANSFER_IN',   'Transfer In',           'Internal inter-account transfer received',      3),
                ('REIMBURSEMENT', 'Reimbursement Receipt', 'Vendor or inter-company reimbursement received',4),
                ('OTHER_INFLOW',  'Other Inflow',          'Miscellaneous inflow receipt',                  5),
            ]
            for code, name, desc, order in inflow_types:
                InflowType.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Inflow Types seeded"))

            # ── 6. Budget Types ──────────────────────────────────────────────
            BudgetType.objects.filter(code__in=['INITIAL', 'REVISED', 'SUPPLEMENTARY']).delete()
            budget_types = [
                ('ROUTINE',    'Routine',               'Routine expenditure budget',          1),
                ('ADDL',       'Additional',            'Additional expenditure budget',        2),
                ('CONTINUING', 'Continuing Requirement','Continuing requirement budget',        3),
                ('NEW',        'New Requirement',       'New requirement budget',               4),
                ('PERSONNEL',  'Personnel',             'Personnel & payroll budget',           5),
                ('OTHER',      'Other',                 'Other / miscellaneous budget',         6),
            ]
            for code, name, desc, order in budget_types:
                BudgetType.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Budget Types seeded"))

            # ── 7. Reimbursement Types ───────────────────────────────────────
            reimb_types = [
                ('VENDOR_RECOVERY',    'Vendor Recovery',       'Recovery received from vendor or supplier',   1),
                ('INTERCO_RECOVERY',   'Inter-company Recovery','Recovery from group / subsidiary company',     2),
                ('GENERAL_REIMB',      'General Reimbursement', 'Other general reimbursement tracking',         3),
            ]
            for code, name, desc, order in reimb_types:
                ReimbursementType.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Reimbursement Types seeded"))

            # ── 8. Document Types ────────────────────────────────────────────
            doc_types = [
                ('APPROVAL_MEMO',   'Approval Memo',     'Signed approval memo / authorization letter', 1),
                ('BANK_STATEMENT',  'Bank Statement',    'Bank record / credit advice',                 2),
                ('PAYMENT_VOUCHER', 'Payment Voucher',   'Signed payment voucher',                      3),
                ('INVOICE_BILL',    'Invoice / Bill',    'Vendor invoice or utility bill',              4),
                ('PURCHASE_ORDER',  'Purchase Order',    'Issued purchase order',                       5),
                ('CONTRACT',        'Contract',          'Vendor / service contract',                   6),
                ('OTHER_DOC',       'Other Document',    'General supporting document',                 7),
            ]
            for code, name, desc, order in doc_types:
                DocumentType.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Document Types seeded"))

            # ── 9. Personnel Classifications ─────────────────────────────────
            pers_classes = [
                ('PERMANENT_STAFF',  'Permanent Staff',         'Full-time permanent employees',        1),
                ('CONTRACT_STAFF',   'Contract Staff',          'Fixed-term contract employees',        2),
                ('MANAGEMENT',       'Management Grade',        'Senior management & executive grade',  3),
                ('SUPPORT_STAFF',    'Support Staff',           'Support, admin & daily wage staff',    4),
            ]
            for code, name, desc, order in pers_classes:
                PersonnelClassification.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] Personnel Classifications seeded"))

            # ── 10. Organisations (replacing Units) ──────────────────────────
            orgs_data = [
                ('HQ-CORP',   'Corporate Headquarters', 'Main head office — strategy, finance, HR & legal',  1),
                ('DIV-NORTH', 'Northern Division',      'Northern regional operations & sales',              2),
                ('DIV-SOUTH', 'Southern Division',      'Southern regional operations & sales',              3),
                ('DIV-EAST',  'Eastern Division',       'Eastern regional operations & logistics',            4),
                ('REG-KHI',   'Karachi Regional Office','Karachi branch office & port operations',            5),
            ]
            for code, name, desc, order in orgs_data:
                Unit.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] 5 Organisations seeded"))

            # ── 11. Departments (replacing InternalSections) ─────────────────
            depts_data = [
                ('DEPT-FIN',   'Finance & Accounts',   'Financial management, budgeting & audit',             1),
                ('DEPT-HR',    'Human Resources',      'Recruitment, payroll, welfare & training',            2),
                ('DEPT-OPS',   'Operations',           'Day-to-day business operations & logistics',          3),
                ('DEPT-IT',    'Information Technology','Software, hardware & digital infrastructure',          4),
                ('DEPT-LEGAL', 'Legal & Compliance',   'Legal affairs, contracts & regulatory compliance',    5),
            ]
            for code, name, desc, order in depts_data:
                InternalSection.objects.get_or_create(
                    code=code,
                    defaults={'name': name, 'description': desc, 'display_order': order}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] 5 Departments seeded"))

            # ── 12. NGL Account Heads (29 corporate heads) ───────────────────
            ngl_heads = [
                (1,  'NGL-01', 'Operating Reserve',                    AccountHead.HeadType.BOTH,   1),
                (2,  'NGL-02', 'Administration & Office Expenses',      AccountHead.HeadType.BOTH,   2),
                (3,  'NGL-03', 'IT & Digital Infrastructure',           AccountHead.HeadType.BOTH,   3),
                (4,  'NGL-04', 'Staff Welfare & Benefits',              AccountHead.HeadType.BOTH,   4),
                (5,  'NGL-05', 'Capacity Building & Training',          AccountHead.HeadType.BOTH,   5),
                (6,  'NGL-06', 'Divisional Support Allocation',         AccountHead.HeadType.BOTH,   6),
                (7,  'NGL-07', 'Cross-Division Grants',                 AccountHead.HeadType.BOTH,   7),
                (8,  'NGL-08', 'Overtime & After-Hours',                AccountHead.HeadType.BOTH,   8),
                (9,  'NGL-09', 'Executive Dining & Entertainment',      AccountHead.HeadType.BOTH,   9),
                (10, 'NGL-10', 'Payroll & Salaries',                    AccountHead.HeadType.BOTH,  10),
                (11, 'NGL-11', 'Standing Approvals',                    AccountHead.HeadType.BOTH,  11),
                (12, 'NGL-12', 'Utilities & Maintenance',               AccountHead.HeadType.BOTH,  12),
                (13, 'NGL-13', 'Staff Loans & Advances',                AccountHead.HeadType.BOTH,  13),
                (14, 'NGL-14', 'Lease & Rent',                          AccountHead.HeadType.BOTH,  14),
                (15, 'NGL-15', 'Miscellaneous Corporate Expenses',      AccountHead.HeadType.BOTH,  15),
                (16, 'NGL-16', 'Monthly Bank Profit',                   AccountHead.HeadType.INFLOW,16),
                (17, 'NGL-17', 'Vendor Recovery Received',              AccountHead.HeadType.INFLOW,17),
                (18, 'NGL-18', 'Inter-company Recovery',                AccountHead.HeadType.INFLOW,18),
                (19, 'NGL-19', 'Subsidiary Receipts — Welfare',         AccountHead.HeadType.INFLOW,19),
                (20, 'NGL-20', 'Subsidiary Receipts — Provident',       AccountHead.HeadType.INFLOW,20),
                (21, 'NGL-21', 'Executive Reference Publications',      AccountHead.HeadType.BOTH,  21),
                (22, 'NGL-22', 'Regional Office Receipts',              AccountHead.HeadType.INFLOW,22),
                (23, 'NGL-23', 'Training Centre Receipts',              AccountHead.HeadType.INFLOW,23),
                (24, 'NGL-24', 'Executive Security Deposits',           AccountHead.HeadType.BOTH,  24),
                (25, 'NGL-25', 'Legal Reserve Account',                 AccountHead.HeadType.BOTH,  25),
                (26, 'NGL-26', 'Cafeteria & Refreshments',              AccountHead.HeadType.BOTH,  26),
                (27, 'NGL-27', 'Corporate Park Lease Income',           AccountHead.HeadType.BOTH,  27),
                (28, 'NGL-28', 'Executive Club Account',                AccountHead.HeadType.BOTH,  28),
                (29, 'NGL-29', 'Pass-Through Clearing',                 AccountHead.HeadType.BOTH,  29),
            ]
            for _, code, name, htype, order in ngl_heads:
                AccountHead.objects.update_or_create(
                    account=ngl, code=code,
                    defaults={'name': name, 'head_type': htype, 'display_order': order, 'is_active': True}
                )
            self.stdout.write(self.style.SUCCESS(f"  [OK] 29 NGL Account Heads seeded"))

            # ── 13. Opening Balances ─────────────────────────────────────────
            OpeningBalance.objects.update_or_create(
                account=ngl, financial_year=fy,
                defaults={
                    'balance_amount': Decimal('71250000.00'),
                    'is_confirmed': True,
                    'remarks': 'Confirmed opening balance for FY 2026-27 — NexGen Holdings Ltd.',
                }
            )
            OpeningBalance.objects.update_or_create(
                account=ewf, financial_year=fy,
                defaults={
                    'balance_amount': Decimal('8500000.00'),
                    'is_confirmed': True,
                    'remarks': 'Confirmed opening balance for FY 2026-27 — Employee Welfare Fund',
                }
            )
            OpeningBalance.objects.update_or_create(
                account=cpf, financial_year=fy,
                defaults={
                    'balance_amount': Decimal('42000000.00'),
                    'is_confirmed': True,
                    'remarks': 'Confirmed opening balance for FY 2026-27 — Corporate Provident Fund',
                }
            )
            self.stdout.write(self.style.SUCCESS("  [OK] Opening Balances seeded (NGL: $71.25M, EWF: $8.5M, CPF: $42M)"))

            # ── 14. RBAC Users ───────────────────────────────────────────────
            users_data = [
                ('admin',      'admin123',      'System',    'Administrator', 'admin@eabms.corp',      UserProfile.Role.ADMINISTRATOR, True),
                ('clerk',      'clerk123',      'Accounts',  'Clerk',         'clerk@eabms.corp',      UserProfile.Role.CLERK,         False),
                ('management', 'management123', 'Senior',    'Management',    'management@eabms.corp', UserProfile.Role.MANAGEMENT,    False),
            ]
            for username, password, first, last, email, role, is_super in users_data:
                user, created = User.objects.get_or_create(
                    username=username,
                    defaults={'first_name': first, 'last_name': last, 'email': email,
                              'is_staff': is_super, 'is_superuser': is_super}
                )
                if created:
                    user.set_password(password)
                    user.save()
                UserProfile.objects.get_or_create(
                    user=user,
                    defaults={'role': role, 'default_account': ngl, 'is_active': True}
                )
            self.stdout.write(self.style.SUCCESS("  [OK] 3 RBAC Users seeded: admin / clerk / management"))

        self.stdout.write(self.style.SUCCESS("\nEABMS Corporate Master Seeding Completed Successfully!"))
