from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Account, MajorHead, SubHead, AccountHead


class Command(BaseCommand):
    help = "Seeds EWF (Employee Welfare Fund) sub-funds and account heads."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding EWF masters..."))

        try:
            ewf = Account.objects.get(code='EWF')
        except Account.DoesNotExist:
            self.stderr.write("EWF account not found. Run seed_eabms_corporate first.")
            return

        with transaction.atomic():
            # ── Sub-Funds (MajorHead) ────────────────────────────────────────
            sf_medical, _ = MajorHead.objects.update_or_create(
                account=ewf, code='MED-SF',
                defaults={'name': 'Medical Benefits Division', 'description': 'Employee medical, dental & vision coverage', 'display_order': 1, 'is_active': True}
            )
            sf_housing, _ = MajorHead.objects.update_or_create(
                account=ewf, code='HSG-SF',
                defaults={'name': 'Housing Assistance Division', 'description': 'Housing subsidies, utility allowances & home loans', 'display_order': 2, 'is_active': True}
            )
            sf_rec, _ = MajorHead.objects.update_or_create(
                account=ewf, code='REC-SF',
                defaults={'name': 'Recreation & Sports Division', 'description': 'Sports, cultural events & club memberships', 'display_order': 3, 'is_active': True}
            )
            sf_grants, _ = MajorHead.objects.update_or_create(
                account=ewf, code='GRT-SF',
                defaults={'name': 'Annual Grants Division', 'description': 'Performance bonuses, education & marriage grants', 'display_order': 4, 'is_active': True}
            )
            sf_train, _ = MajorHead.objects.update_or_create(
                account=ewf, code='TRN-SF',
                defaults={'name': 'Training & Development Division', 'description': 'External training, certifications & e-learning', 'display_order': 5, 'is_active': True}
            )
            self.stdout.write(self.style.SUCCESS("  [OK] 5 EWF Divisions seeded"))

            # ── Account Heads ────────────────────────────────────────────────
            heads = [
                # Medical
                (ewf, sf_medical, 'EWF-MD-01', 'Outpatient Claims',           AccountHead.HeadType.OUTFLOW, 1),
                (ewf, sf_medical, 'EWF-MD-02', 'Inpatient & Surgical Claims', AccountHead.HeadType.OUTFLOW, 2),
                (ewf, sf_medical, 'EWF-MD-03', 'Dental & Vision Care',        AccountHead.HeadType.OUTFLOW, 3),
                (ewf, sf_medical, 'EWF-MD-04', 'Specialist Referrals',        AccountHead.HeadType.OUTFLOW, 4),
                (ewf, sf_medical, 'EWF-MD-05', 'Medical Equipment & Supplies', AccountHead.HeadType.OUTFLOW, 5),
                (ewf, sf_medical, 'EWF-MD-06', 'Medical Insurance Premium',   AccountHead.HeadType.OUTFLOW, 6),
                # Housing
                (ewf, sf_housing, 'EWF-HS-01', 'House Rent Subsidy',          AccountHead.HeadType.OUTFLOW, 1),
                (ewf, sf_housing, 'EWF-HS-02', 'Utility Allowance',           AccountHead.HeadType.OUTFLOW, 2),
                (ewf, sf_housing, 'EWF-HS-03', 'Home Loan Assistance',        AccountHead.HeadType.OUTFLOW, 3),
                (ewf, sf_housing, 'EWF-HS-04', 'Relocation & Moving Grants',  AccountHead.HeadType.OUTFLOW, 4),
                # Recreation
                (ewf, sf_rec, 'EWF-RC-01', 'Annual Sports Day & Events',      AccountHead.HeadType.OUTFLOW, 1),
                (ewf, sf_rec, 'EWF-RC-02', 'Corporate Club Memberships',      AccountHead.HeadType.OUTFLOW, 2),
                (ewf, sf_rec, 'EWF-RC-03', 'Team Building Activities',        AccountHead.HeadType.OUTFLOW, 3),
                (ewf, sf_rec, 'EWF-RC-04', 'Cultural & Festival Events',      AccountHead.HeadType.OUTFLOW, 4),
                # Grants
                (ewf, sf_grants, 'EWF-GR-01', 'Performance Bonus Disbursements', AccountHead.HeadType.OUTFLOW, 1),
                (ewf, sf_grants, 'EWF-GR-02', 'Employee Education Grants',      AccountHead.HeadType.OUTFLOW, 2),
                (ewf, sf_grants, 'EWF-GR-03', 'Marriage Assistance Grants',     AccountHead.HeadType.OUTFLOW, 3),
                (ewf, sf_grants, 'EWF-GR-04', 'Bereavement & Emergency Aid',    AccountHead.HeadType.OUTFLOW, 4),
                (ewf, sf_grants, 'EWF-GR-05', 'Long Service Awards',            AccountHead.HeadType.OUTFLOW, 5),
                # Training
                (ewf, sf_train, 'EWF-TR-01', 'External Training Programs',     AccountHead.HeadType.OUTFLOW, 1),
                (ewf, sf_train, 'EWF-TR-02', 'Professional Certifications',    AccountHead.HeadType.OUTFLOW, 2),
                (ewf, sf_train, 'EWF-TR-03', 'E-Learning Subscriptions',       AccountHead.HeadType.OUTFLOW, 3),
                (ewf, sf_train, 'EWF-TR-04', 'Training Recovery from NGL',     AccountHead.HeadType.INFLOW,  4),
            ]
            for account, major_head, code, name, htype, order in heads:
                AccountHead.objects.update_or_create(
                    account=account, code=code,
                    defaults={'name': name, 'head_type': htype, 'display_order': order,
                              'is_active': True}
                )

            self.stdout.write(self.style.SUCCESS(f"  [OK] {len(heads)} EWF Account Heads seeded across 5 Divisions"))

        self.stdout.write(self.style.SUCCESS("EWF Master Seeding Complete!"))
