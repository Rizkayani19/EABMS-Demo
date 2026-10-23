"""Seed an approved demo budget for each fund that has demo transactions.

Budgets are derived from the seeded demo transactions: actual activity for the
months covered is annualised, multiplied by a per-head headroom factor
(0.95x-1.45x, fixed per head so re-runs give the same figures) and rounded to
the nearest thousand, so heads show realistic, differing utilisation. Re-running the command replaces the demo budget lines; it never
touches a budget that is not marked as the demo budget.
"""
import zlib
from decimal import Decimal, ROUND_HALF_UP

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.db.models import Max, Min, Sum

from core.budget_inflow_models import BudgetInflowLine
from core.models import Account, Budget, BudgetLine, BudgetType, FinancialYear, Transaction

DEMO_REFERENCE = 'DEMO-BUDGET'


def _headroom(head_id):
    """Deterministic factor between 0.95 and 1.45 for each account head."""
    return Decimal('0.95') + Decimal(zlib.crc32(str(head_id).encode()) % 51) / Decimal(100)


def _annualise(amount, months, head_id):
    projected = amount * Decimal(12) / Decimal(months) * _headroom(head_id)
    return (projected / Decimal(1000)).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * Decimal(1000)


class Command(BaseCommand):
    help = "Seed an approved demo budget (outflow and inflow lines) from the demo transactions."

    def add_arguments(self, parser):
        parser.add_argument('--fy', default='2026-27', help='Financial year code (default 2026-27).')

    def handle(self, *args, **options):
        try:
            fy = FinancialYear.objects.get(code=options['fy'])
        except FinancialYear.DoesNotExist:
            self.stderr.write(f"Financial year {options['fy']} not found. Run seed_eabms_corporate first.")
            return
        budget_type = BudgetType.objects.filter(code='ROUTINE').first() or BudgetType.objects.first()
        if budget_type is None:
            self.stderr.write("No budget types found. Run seed_eabms_corporate first.")
            return

        seeded = 0
        for account in Account.objects.filter(is_active=True).order_by('display_order', 'code'):
            txns = Transaction.objects.filter(
                account=account, financial_year=fy, status=Transaction.Status.ACTIVE,
                pass_through=False, account_head__isnull=False,
            )
            if not txns.exists():
                continue
            span = txns.aggregate(first=Min('transaction_date'), last=Max('transaction_date'))
            months = max(1, (span['last'].year - span['first'].year) * 12 + span['last'].month - span['first'].month + 1)

            with db_transaction.atomic():
                budget = Budget.objects.filter(account=account, financial_year=fy).first()
                if budget and budget.reference != DEMO_REFERENCE:
                    self.stdout.write(f"  [SKIP] {account.code}: a non-demo budget already exists")
                    continue
                if budget is None:
                    budget = Budget.objects.create(
                        account=account, financial_year=fy, reference=DEMO_REFERENCE,
                        status=Budget.Status.APPROVED,
                        budget_allocation_basis=Budget._meta.get_field('budget_allocation_basis').default,
                        remarks='Demo budget derived from seeded demo transactions.',
                    )
                else:
                    budget.status = Budget.Status.APPROVED
                    budget.save(update_fields=['status', 'updated_at'])
                    budget.lines.all().delete()
                    budget.inflow_lines.all().delete()

                out_total = in_total = Decimal('0')
                for direction, model in (('OUTFLOW', BudgetLine), ('INFLOW', BudgetInflowLine)):
                    rows = (txns.filter(direction=direction)
                            .values('account_head').annotate(total=Sum('amount')).order_by('account_head'))
                    for row in rows:
                        amount = _annualise(row['total'], months, row['account_head'])
                        model.objects.create(budget=budget, account_head_id=row['account_head'],
                                             budget_type=budget_type, amount=amount)
                        if direction == 'OUTFLOW':
                            out_total += amount
                        else:
                            in_total += amount
            seeded += 1
            self.stdout.write(self.style.SUCCESS(
                f"  [OK] {account.code} {fy.code}: outflow budget Rs {out_total:,.0f}, "
                f"inflow budget Rs {in_total:,.0f} ({months} month(s) annualised)"))

        if not seeded:
            self.stdout.write("No demo transactions found. Run seed_eabms_demo_transactions first.")
