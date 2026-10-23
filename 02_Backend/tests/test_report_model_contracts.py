from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from reports.services import build_pending_reimbursements


class ReportModelContractTests(SimpleTestCase):
    def test_pending_reimbursement_uses_canonical_reference_field(self):
        reimbursement = SimpleNamespace(
            reference="RB-001",
            original_outflow=SimpleNamespace(transaction_number="TX-001"),
            expected_amount=Decimal("100.00"),
            received_amount=Decimal("25.00"),
        )
        with patch("reports.services.Reimbursement.objects.filter", return_value=[reimbursement]):
            result = build_pending_reimbursements({})

        self.assertEqual(result, [{
            "reference": "RB-001",
            "outflow_tx": "TX-001",
            "expected": Decimal("100.00"),
            "received": Decimal("25.00"),
            "pending": Decimal("75.00"),
        }])
