"""G23.2 contract tests for the canonical Future Budget calculation primitive."""
from decimal import Decimal

from django.test import SimpleTestCase

from core.future_budget_services import compute_system_suggested


class G23FutureBudgetCalculationContractTests(SimpleTestCase):
    def test_components_are_added_once(self):
        suggested, breakdown = compute_system_suggested(
            Decimal("100000.00"),
            Decimal("10.00"),
            Decimal("5000.00"),
            Decimal("3000.00"),
            Decimal("7000.00"),
            Decimal("0.00"),
            Decimal("4000.00"),
        )
        self.assertEqual(suggested, Decimal("129000.00"))
        self.assertEqual(breakdown["routine_adjustment"], "10000.00")
        self.assertEqual(breakdown["continuing_requirement"], "5000.00")
        self.assertEqual(breakdown["management_additional_requirement"], "4000.00")
        self.assertEqual(breakdown["known_changes"], "3000.00")
        self.assertEqual(breakdown["personnel_effect"], "7000.00")

    def test_personnel_effect_is_not_subject_to_second_routine_uplift(self):
        suggested, _ = compute_system_suggested(
            Decimal("900000.00"),
            Decimal("10.00"),
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("75000.00"),
            Decimal("0.00"),
            Decimal("0.00"),
        )
        # The personnel effect is already the calculated personnel delta;
        # the generic routine adjustment applies only to the supplied baseline.
        self.assertEqual(suggested, Decimal("1065000.00"))

    def test_one_time_deduction_is_explicit_when_supplied(self):
        suggested, breakdown = compute_system_suggested(
            Decimal("100000.00"),
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("0.00"),
            Decimal("20000.00"),
            Decimal("0.00"),
        )
        self.assertEqual(suggested, Decimal("80000.00"))
        self.assertEqual(breakdown["onetime_deduction"], "20000.00")

    def test_suggestion_never_becomes_negative(self):
        suggested, _ = compute_system_suggested(
            Decimal("10000.00"), Decimal("0.00"), Decimal("0.00"),
            Decimal("0.00"), Decimal("0.00"), Decimal("25000.00"), Decimal("0.00"),
        )
        self.assertEqual(suggested, Decimal("0.00"))
