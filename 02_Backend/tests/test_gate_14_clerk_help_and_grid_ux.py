from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from core.bulk_transactions import _parse_date


class Gate14ClerkHelpAndGridUxTests(SimpleTestCase):
    def test_bulk_grid_accepts_browser_and_display_date_formats(self):
        self.assertEqual(str(_parse_date("21-08-2026")), "2026-08-21")
        self.assertEqual(str(_parse_date("2026-08-21")), "2026-08-21")

    def test_help_manual_is_clerk_facing_and_explains_bulk_grid(self):
        path = Path(settings.BASE_DIR) / "templates" / "help" / "index.html"
        content = path.read_text(encoding="utf-8")
        required_phrases = [
            "How to record one Inflow",
            "How to record one Outflow",
            "How to find a transaction in All Transactions",
            "Mass / Bulk Grid",
            "How to add a new row",
            "What happens when I press Save All Changes?",
            "all-or-nothing",
            "Why?",
        ]
        for phrase in required_phrases:
            self.assertIn(phrase, content)

    def test_base_template_contains_global_native_date_picker_initialiser(self):
        path = Path(settings.BASE_DIR) / "templates" / "base.html"
        content = path.read_text(encoding="utf-8")
        self.assertIn("initTransactionDatePickers", content)
        self.assertIn("input[name=\"date_from\"]", content)
        self.assertIn("input[name=\"date_to\"]", content)
        self.assertIn("#bulk-editor [data-field=\"transaction_date\"]", content)
