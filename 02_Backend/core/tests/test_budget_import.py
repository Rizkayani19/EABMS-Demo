import csv
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.budget_import_services import parse_ngl_budget_analysis_csv, validate_ngl_budget_rows
from core.models import Account, AccountHead, FinancialYear


class NGLBudgetImportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from core.models import Installation

        cls.installation = Installation.objects.create(
            installation_code="TEST-BUDGET-IMPORT",
            installation_name="Budget Import Test",
        )
        cls.account = Account.objects.create(
            installation=cls.installation,
            code="NGL-T",
            name="NGL Test",
        )
        cls.fy = FinancialYear.objects.create(
            code="2025-26-T",
            name="FY 2025-26 Test",
            start_date="2025-07-01",
            end_date="2026-06-30",
        )
        AccountHead.objects.create(
            account=cls.account,
            name="Fin Asst Units",
            head_type=AccountHead.HeadType.OUTFLOW,
        )
        AccountHead.objects.create(
            account=cls.account,
            name="Fin Asst Indls",
            head_type=AccountHead.HeadType.OUTFLOW,
        )

    def test_parser_reads_outflow_budget_in_millions(self):
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", newline="", encoding="utf-8-sig", delete=False
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["Category / Head of Account", "Inflows", "", "Outflows"])
            writer.writerow(["OUTFLOW HEADS (RANKED HIGHEST TO LOWEST)", "", "", ""])
            writer.writerow(["Fin Asst Units", "8.00", "0.67", "12.85"])
            writer.writerow(["INFLOW HEADS (RANKED HIGHEST TO LOWEST)", "", "", ""])
            path = handle.name

        rows = parse_ngl_budget_analysis_csv(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["budget_amount"], Decimal("12850000.00"))

    def test_mapping_and_validation_use_account_heads(self):
        rows = [
            {
                "source_row": 5,
                "legacy_head": "Fin Asst Indis",
                "budget_millions": Decimal("16.50"),
                "budget_amount": Decimal("16500000.00"),
                "remarks": "",
            }
        ]
        validated, errors = validate_ngl_budget_rows(rows, self.account)
        self.assertFalse(errors)
        self.assertEqual(validated[0]["account_head"].name, "Fin Asst Indls")
