from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from core.budget_analysis_services import analyse_budget, variance_flags, build_future_baseline
from core.models import Account, AccountHead, BudgetLine, FinancialYear, FutureBudget


class Command(BaseCommand):
    help = (
        "Run existing-FY budget analysis and optionally prepare a future-FY "
        "planning budget without modifying an approved future budget."
    )

    def add_arguments(self, parser):
        parser.add_argument("--account", required=True, help="Account code, e.g. NGL")
        parser.add_argument("--source-fy", dest="source_fy", required=True, help="Source FY code, e.g. 2025-26")
        parser.add_argument("--target-fy", dest="target_fy", help="Target FY code for future planning")
        parser.add_argument("--routine-adjustment", dest="routine_adjustment", default="0", help="Routine adjustment percentage")

    def handle(self, *args, **options):
        try:
            account = Account.objects.get(code=options["account"])
            source_fy = FinancialYear.objects.get(code=options["source_fy"])
        except (Account.DoesNotExist, FinancialYear.DoesNotExist) as exc:
            raise CommandError(str(exc))

        result = analyse_budget(account, source_fy)
        self.stdout.write(self.style.SUCCESS(
            f"{account.code} | {source_fy.code} | Budget Rs {result['total_budget']:,.2f} | "
            f"Actual Rs {result['total_actual']:,.2f} | Variance Rs {result['total_variance']:,.2f} | "
            f"Utilisation {result['utilisation_pct']:,.2f}% | "
            f"Reconciliation Rs {result['reconciliation_difference']:,.2f}"
        ))
        self.stdout.write(f"Material flags: {len(variance_flags(result))}")

        if not options.get("target_fy"):
            return

        try:
            target_fy = FinancialYear.objects.get(code=options["target_fy"])
            pct = Decimal(str(options["routine_adjustment"]))
        except (FinancialYear.DoesNotExist, ValueError) as exc:
            raise CommandError(str(exc))

        existing = FutureBudget.objects.filter(
            account=account,
            source_fy=source_fy,
            target_fy=target_fy,
        ).first()

        if existing and existing.status == FutureBudget.Status.APPROVED:
            self.stdout.write(
                self.style.WARNING(
                    f"Future Budget #{existing.pk} is APPROVED; generating non-destructive planning preview."
                )
            )
            head_ids = {row["account_head_id"] for row in result["rows"]}
            heads = {h.id: h for h in AccountHead.objects.filter(id__in=head_ids)}
            suggestions = []
            from core.future_budget_services import analyze_account_head
            from core.future_budget_calculation import calculate_future_budget_components

            for head_id, row in ((r["account_head_id"], r) for r in result["rows"]):
                head = heads[head_id]
                analysis = analyze_account_head(account, source_fy, head)
                prior_budget = (
                    BudgetLine.objects.filter(
                        budget__account=account,
                        budget__financial_year=source_fy,
                        account_head=head,
                    ).aggregate(t=Sum("amount"))["t"]
                    or Decimal("0.00")
                )
                baseline = Decimal("0.00") if analysis["is_onetime"] else analysis["planning_actual"]
                effective_pct = Decimal("0.00") if "salar" in head.name.lower() else pct
                calc = calculate_future_budget_components(
                    previous_actual=baseline,
                    routine_adj_pct=effective_pct,
                    continuing_amount=Decimal("0.00"),
                    known_change_amount=Decimal("0.00"),
                    personnel_amount=Decimal("0.00"),
                    onetime_amount=Decimal("0.00"),
                    additional_management_amount=Decimal("0.00"),
                )
                suggestions.append((head.name, prior_budget, analysis["planning_actual"], calc.system_suggested))

            planning_total = sum((r[2] for r in suggestions), Decimal("0.00"))
            suggested_total = sum((r[3] for r in suggestions), Decimal("0.00"))
            self.stdout.write(self.style.SUCCESS(
                f"Future planning preview {target_fy.code}: {len(suggestions)} heads | "
                f"Planning baseline Rs {planning_total:,.2f} | "
                f"System suggested Rs {suggested_total:,.2f} | Approved record #{existing.pk}"
            ))
            return

        try:
            future = build_future_baseline(account, source_fy, target_fy, pct)
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc))

        suggested = sum(
            (line.system_suggested for line in future.lines.all()),
            Decimal("0.00"),
        )
        self.stdout.write(self.style.SUCCESS(
            f"Future planning draft {target_fy.code}: #{future.pk} | "
            f"{future.lines.count()} heads | System suggested Rs {suggested:,.2f}"
        ))
