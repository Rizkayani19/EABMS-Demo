import json

from django.core.management.base import BaseCommand, CommandError

from core.models import Account, FinancialYear
from core.security_integrity import run_security_integrity_check


class Command(BaseCommand):
    help = "Run ABMS Gate 11 security, RBAC-related financial integrity and audit checks."

    def add_arguments(self, parser):
        parser.add_argument("--account", dest="account_code")
        parser.add_argument("--fy", dest="financial_year_code")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        account = None
        financial_year = None

        if options.get("account_code"):
            try:
                account = Account.objects.get(code=options["account_code"])
            except Account.DoesNotExist as exc:
                raise CommandError(f"Account not found: {options['account_code']}") from exc

        if options.get("financial_year_code"):
            try:
                financial_year = FinancialYear.objects.get(code=options["financial_year_code"])
            except FinancialYear.DoesNotExist as exc:
                raise CommandError(f"Financial Year not found: {options['financial_year_code']}") from exc

        result = run_security_integrity_check(account=account, financial_year=financial_year)

        if options["as_json"]:
            self.stdout.write(json.dumps(result, default=str, indent=2))
        else:
            self.stdout.write(f"Gate 11 security integrity status: {result['status']}")
            self.stdout.write(f"Transaction audit issues: {len(result['transaction_audit_issues'])}")
            self.stdout.write(f"Reimbursement link issues: {len(result['reimbursement_link_issues'])}")
            self.stdout.write(f"Opening Balance confirmation issues: {len(result['opening_balance_confirmation_issues'])}")
            self.stdout.write(f"Total exceptions: {result['total_exceptions']}")

        if result["status"] != "PASS":
            raise CommandError("Gate 11 security-integrity checks detected one or more exceptions.")
