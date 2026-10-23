from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Account, MajorHead, AccountHead


class Command(BaseCommand):
    help = "Seeds CPF (Corporate Provident Fund) sub-funds and account heads."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding CPF masters..."))

        try:
            cpf = Account.objects.get(code='CPF')
        except Account.DoesNotExist:
            self.stderr.write("CPF account not found. Run seed_eabms_corporate first.")
            return

        with transaction.atomic():
            # ── Sub-Funds (MajorHead / Division) ────────────────────────────
            sf_staff, _ = MajorHead.objects.update_or_create(
                account=cpf, code='SVC-SF',
                defaults={'name': 'Staff Voluntary Contributions', 'description': 'Employee voluntary provident contributions', 'display_order': 1, 'is_active': True}
            )
            sf_employer, _ = MajorHead.objects.update_or_create(
                account=cpf, code='EMP-SF',
                defaults={'name': 'Employer Contributions', 'description': 'Company matching and discretionary contributions', 'display_order': 2, 'is_active': True}
            )
            sf_invest, _ = MajorHead.objects.update_or_create(
                account=cpf, code='INV-SF',
                defaults={'name': 'Investment Returns', 'description': 'Fixed deposits, T-bills, dividends & capital gains', 'display_order': 3, 'is_active': True}
            )
            self.stdout.write(self.style.SUCCESS("  [OK] 3 CPF Divisions seeded"))

            # ── Account Heads ────────────────────────────────────────────────
            heads = [
                # Staff Voluntary Contributions
                (cpf, sf_staff,    'CPF-SV-01', 'Regular Monthly Contributions',       AccountHead.HeadType.INFLOW,  1),
                (cpf, sf_staff,    'CPF-SV-02', 'Additional Voluntary Contributions',  AccountHead.HeadType.INFLOW,  2),
                (cpf, sf_staff,    'CPF-SV-03', 'Withdrawal — Retirement Maturity',    AccountHead.HeadType.OUTFLOW, 3),
                (cpf, sf_staff,    'CPF-SV-04', 'Withdrawal — Advance on Account',     AccountHead.HeadType.OUTFLOW, 4),
                (cpf, sf_staff,    'CPF-SV-05', 'Refund — Resigned Employees',         AccountHead.HeadType.OUTFLOW, 5),
                # Employer Contributions
                (cpf, sf_employer, 'CPF-EM-01', 'Company Matching Contributions',      AccountHead.HeadType.INFLOW,  1),
                (cpf, sf_employer, 'CPF-EM-02', 'Annual Bonus Contribution',           AccountHead.HeadType.INFLOW,  2),
                (cpf, sf_employer, 'CPF-EM-03', 'Management Discretionary Allocation', AccountHead.HeadType.INFLOW,  3),
                (cpf, sf_employer, 'CPF-EM-04', 'Administrative Expenses',             AccountHead.HeadType.OUTFLOW, 4),
                # Investment Returns
                (cpf, sf_invest,   'CPF-IV-01', 'Fixed Deposit Interest',              AccountHead.HeadType.INFLOW,  1),
                (cpf, sf_invest,   'CPF-IV-02', 'Government T-Bill Profits',           AccountHead.HeadType.INFLOW,  2),
                (cpf, sf_invest,   'CPF-IV-03', 'Dividend Income',                     AccountHead.HeadType.INFLOW,  3),
                (cpf, sf_invest,   'CPF-IV-04', 'Capital Gains on Securities',         AccountHead.HeadType.INFLOW,  4),
                (cpf, sf_invest,   'CPF-IV-05', 'Fund Management Fees',                AccountHead.HeadType.OUTFLOW, 5),
            ]
            for account, major_head, code, name, htype, order in heads:
                AccountHead.objects.update_or_create(
                    account=account, code=code,
                    defaults={'name': name, 'head_type': htype, 'display_order': order, 'is_active': True}
                )

            self.stdout.write(self.style.SUCCESS(f"  [OK] {len(heads)} CPF Account Heads seeded across 3 Divisions"))

        self.stdout.write(self.style.SUCCESS("CPF Master Seeding Complete!"))
