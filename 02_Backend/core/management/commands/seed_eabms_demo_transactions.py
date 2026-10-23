"""
EABMS Demo Transaction Seeder — NexGen Holdings Ltd. (NGL)
Generates realistic FY 2026-27 demo data for 3 months:
  July 2026      → ~$1.92M total transaction value
  August 2026    → ~$2.13M total transaction value
  September 2026 → ~$1.32M total transaction value
Opening Balance: $71,250,000
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction

from core.models import (
    Account, AccountHead, FinancialYear, InternalSection,
    OutflowNature, InflowType, Transaction, Unit
)


class Command(BaseCommand):
    help = "Seeds realistic 3-month demo transactions for NexGen Holdings Ltd. (NGL) — FY 2026-27."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding EABMS demo transactions..."))

        try:
            ngl = Account.objects.get(code='NGL')
            fy  = FinancialYear.objects.get(code='2026-27')
        except (Account.DoesNotExist, FinancialYear.DoesNotExist) as e:
            self.stderr.write(f"Prerequisites missing: {e}. Run seed_eabms_corporate first.")
            return

        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            self.stderr.write("No superuser found.")
            return

        # Pre-load lookup objects
        heads        = {h.code: h for h in AccountHead.objects.filter(account=ngl, is_active=True)}
        depts        = list(InternalSection.objects.filter(is_active=True))
        orgs         = list(Unit.objects.filter(is_active=True))
        natures      = {n.code: n for n in OutflowNature.objects.all()}
        inflow_types = {i.code: i for i in InflowType.objects.all()}

        # Realistic corporate payees / sources
        vendors = [
            "Microsoft Corporation", "Oracle Pakistan", "IBM Global Services",
            "Deloitte & Touche LLP", "KPMG Advisory", "Ernst & Young Pakistan",
            "HBL — Head Office", "Allied Bank Ltd.", "Meezan Bank Ltd.",
            "Arif Habib Limited", "JS Bank Treasury", "National Bank of Pakistan",
            "Atlas Honda Ltd.", "Indus Motor Company", "Engro Corporation",
            "Pakistan Petroleum Ltd.", "TCS Couriers", "DHL Express Pakistan",
            "Telenor Pakistan", "Jazz Communications", "PTCL Corporate",
            "Karachi Electric Supply Corp.", "SSGC — Southern Gas",
            "Crown Plaza Hotel Karachi", "Serena Hotels Ltd.", "Avari Towers",
            "McKinsey & Company", "Accenture Pakistan", "PwC Pakistan",
        ]

        # Monthly plans: (month_start, outflow_target, inflow_target)
        months = [
            (date(2026, 7, 1),  Decimal('1330000'), Decimal('590000')),   # Jul: $1.92M
            (date(2026, 8, 1),  Decimal('1480000'), Decimal('650000')),   # Aug: $2.13M
            (date(2026, 9, 1),  Decimal('900000'),  Decimal('420000')),   # Sep: $1.32M
        ]

        all_txns = []   # list of (Transaction, org|None, dept|None)

        for month_start, outflow_target, inflow_target in months:
            month_end  = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            month_name = month_start.strftime("%B %Y")
            self.stdout.write(f"  Generating {month_name}...")

            # ── OUTFLOWS ─────────────────────────────────────────────────────
            # (head_code, desc_template, payee|None, fraction, nature_code, count)
            outflow_plan = [
                ('NGL-10', 'Monthly payroll disbursement — {m}',             None,                     Decimal('0.42'), 'ROUTINE',      1),
                ('NGL-02', 'Office supplies & stationery — {m}',             None,                     Decimal('0.04'), 'ROUTINE',      2),
                ('NGL-02', 'Board meeting venue booking — {m}',              'Crown Plaza Hotel Karachi', Decimal('0.02'), 'ROUTINE',   1),
                ('NGL-03', 'Microsoft 365 annual license renewal',           'Microsoft Corporation',  Decimal('0.05'), 'ROUTINE',      1),
                ('NGL-03', 'IT infrastructure maintenance — {m}',            'IBM Global Services',    Decimal('0.03'), 'ROUTINE',      1),
                ('NGL-12', 'Electricity — Corporate Park — {m}',             'Karachi Electric Supply Corp.', Decimal('0.04'), 'ROUTINE', 1),
                ('NGL-12', 'Natural gas utility — {m}',                      'SSGC — Southern Gas',   Decimal('0.01'), 'ROUTINE',      1),
                ('NGL-12', 'Building maintenance & janitorial — {m}',        None,                     Decimal('0.02'), 'ROUTINE',      1),
                ('NGL-14', 'Corporate headquarters lease — {m}',             None,                     Decimal('0.06'), 'ROUTINE',      1),
                ('NGL-14', 'Karachi regional office lease — {m}',            None,                     Decimal('0.02'), 'ROUTINE',      1),
                ('NGL-05', 'Professional development workshop — {m}',        'Deloitte & Touche LLP',  Decimal('0.02'), 'ADDL',         1),
                ('NGL-09', 'Executive dinner — quarterly review — {m}',      'Avari Towers',           Decimal('0.01'), 'ROUTINE',      1),
                ('NGL-08', 'Overtime allowances — {m}',                      None,                     Decimal('0.02'), 'ROUTINE',      1),
                ('NGL-04', 'Employee welfare disbursement — {m}',            None,                     Decimal('0.02'), 'ROUTINE',      1),
                ('NGL-15', 'Miscellaneous corporate expenses — {m}',         None,                     Decimal('0.02'), 'ROUTINE',      2),
                ('NGL-25', 'Legal retainer — regulatory compliance — {m}',   'KPMG Advisory',          Decimal('0.02'), 'ROUTINE',      1),
                ('NGL-26', 'Cafeteria & refreshments — {m}',                 None,                     Decimal('0.01'), 'ROUTINE',      1),
                ('NGL-06', 'Northern Division support allocation — {m}',     None,                     Decimal('0.03'), 'ADDL',         1),
                ('NGL-07', 'Cross-division innovation grant — {m}',          None,                     Decimal('0.02'), 'ADDL',         1),
                ('NGL-29', 'Pass-through clearing — vendor advance — {m}',   None,                     Decimal('0.02'), 'PASS_THROUGH', 1),
            ]

            txn_date = month_start + timedelta(days=3)
            for head_code, desc_tmpl, payee, fraction, nature_code, count in outflow_plan:
                if head_code not in heads:
                    continue
                head = heads[head_code]
                nature_obj = natures.get(nature_code)
                base_amount = (outflow_target * fraction) / count
                for _ in range(count):
                    amount = self._jitter(base_amount)
                    desc   = desc_tmpl.format(m=month_name)
                    used_payee = payee or random.choice(vendors)
                    dept = random.choice(depts) if depts else None
                    org  = random.choice(orgs)  if orgs  else None
                    status = 'DRAFT' if random.random() < 0.08 else 'ACTIVE'
                    t = Transaction(
                        account=ngl,
                        financial_year=fy,
                        transaction_date=txn_date,
                        direction='OUTFLOW',
                        account_head=head,
                        amount=amount,
                        payee_or_source=used_payee,
                        description=desc,
                        purpose=f"{head.name} — {month_name}",
                        outflow_nature=nature_obj,
                        status=status,
                        created_by=admin_user,
                        updated_by=admin_user,
                    )
                    all_txns.append((t, org, dept))
                    txn_date += timedelta(days=1)
                    if txn_date > month_end:
                        txn_date = month_start + timedelta(days=2)

            # ── INFLOWS ──────────────────────────────────────────────────────
            # (head_code, desc_template, source|None, fraction, inflow_type_code)
            inflow_plan = [
                ('NGL-16', 'Monthly bank profit — running account — {m}', 'HBL — Head Office',    Decimal('0.42'), 'PROFIT'),
                ('NGL-17', 'Vendor recovery — IT equipment deposit — {m}','IBM Global Services',  Decimal('0.12'), 'REIMBURSEMENT'),
                ('NGL-18', 'Inter-company recovery — EWF allocation',      None,                  Decimal('0.15'), 'TRANSFER_IN'),
                ('NGL-18', 'Inter-company recovery — CPF contribution',    None,                  Decimal('0.10'), 'TRANSFER_IN'),
                ('NGL-22', 'Northern Division quarterly remittance — {m}', None,                  Decimal('0.10'), 'DIRECT'),
                ('NGL-23', 'Training centre course fees — {m}',            None,                  Decimal('0.06'), 'DIRECT'),
                ('NGL-27', 'Corporate park lease income — {m}',            None,                  Decimal('0.05'), 'DIRECT'),
            ]

            inflow_date = month_start + timedelta(days=1)
            for head_code, desc_tmpl, source, fraction, itype_code in inflow_plan:
                if head_code not in heads:
                    continue
                head       = heads[head_code]
                itype_obj  = inflow_types.get(itype_code)
                amount     = self._jitter(inflow_target * fraction)
                desc       = desc_tmpl.format(m=month_name)
                used_source = source or random.choice(vendors)
                t = Transaction(
                    account=ngl,
                    financial_year=fy,
                    transaction_date=inflow_date,
                    direction='INFLOW',
                    account_head=head,
                    amount=amount,
                    payee_or_source=used_source,
                    description=desc,
                    purpose=f"{head.name} receipt — {month_name}",
                    inflow_type=itype_obj,
                    status='ACTIVE',
                    created_by=admin_user,
                    updated_by=admin_user,
                )
                all_txns.append((t, None, None))
                inflow_date += timedelta(days=2)

        # ── Save individually so Transaction.save() generates transaction_number ──
        with db_transaction.atomic():
            saved = []
            for t, org, dept in all_txns:
                t.save()
                saved.append((t, org, dept))

            self.stdout.write(self.style.SUCCESS(f"  [OK] {len(saved)} transactions saved to database"))

            # Attach organisation & department M2M tags
            tagged = 0
            for txn_obj, org, dept in saved:
                try:
                    if org:
                        txn_obj.transaction_units.add(org)
                    if dept:
                        txn_obj.transaction_sections.add(dept)
                    tagged += 1
                except Exception:
                    pass
            self.stdout.write(self.style.SUCCESS(f"  [OK] {tagged} transactions tagged with Organisations/Departments"))

        # Final summary
        total_in  = sum(t.amount for t, _, _ in all_txns if t.direction == 'INFLOW')
        total_out = sum(t.amount for t, _, _ in all_txns if t.direction == 'OUTFLOW')
        self.stdout.write(self.style.SUCCESS(
            f"\n{'='*55}\n"
            f"  Demo Data Summary — NexGen Holdings Ltd. (NGL)\n"
            f"{'='*55}\n"
            f"  Opening Balance : $71,250,000.00\n"
            f"  Total Inflows   : ${total_in:>14,.2f}\n"
            f"  Total Outflows  : ${total_out:>14,.2f}\n"
            f"  Net Movement    : ${total_in - total_out:>14,.2f}\n"
            f"  Transactions    : {len(all_txns)}\n"
            f"{'='*55}"
        ))

    def _jitter(self, amount: Decimal) -> Decimal:
        """Add ±8% random variance to make amounts look realistic."""
        factor = Decimal(str(random.uniform(0.92, 1.08)))
        result = (amount * factor).quantize(Decimal('0.01'))
        return max(result, Decimal('100.00'))
