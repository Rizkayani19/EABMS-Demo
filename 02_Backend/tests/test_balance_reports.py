from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from core.balance_report_services import (
    build_account_head_report,
    build_sub_account_head_report,
    build_sub_fund_report,
)
from core.models import Account, AccountHead, FinancialYear, MajorHead, OpeningBalance, SubHead, Transaction


def make_fy():
    return FinancialYear.objects.create(
        code="2035-36",
        name="2035-36",
        start_date=date(2035, 7, 1),
        end_date=date(2036, 6, 30),
    )


@pytest.mark.django_db
def test_present_balance_reports_reconcile():
    user = get_user_model().objects.create_user(username="balance_report_user")
    account = Account.objects.create(code="BAL", name="Balance Report Account")
    fy = make_fy()
    sf1 = MajorHead.objects.create(account=account, code="SF1", name="Sub Fund 1")
    sf2 = MajorHead.objects.create(account=account, code="SF2", name="Sub Fund 2")
    ah1 = AccountHead.objects.create(account=account, major_head=sf1, code="AH1", name="Account Head 1")
    ah2 = AccountHead.objects.create(account=account, major_head=sf2, code="AH2", name="Account Head 2")
    sh1 = SubHead.objects.create(account=account, major_head=sf1, account_head=ah1, code="SH1", name="Sub Account Head 1")
    OpeningBalance.objects.create(account=account, financial_year=fy, balance_amount=Decimal("1000.00"))

    def tx(direction, amount, major, head, sub):
        return Transaction.objects.create(
            account=account,
            financial_year=fy,
            transaction_date=date(2035, 7, 5),
            direction=direction,
            amount=Decimal(amount),
            major_head=major,
            account_head=head,
            sub_head=sub,
            created_by=user,
            description="Test",
            status=Transaction.Status.ACTIVE,
        )

    tx(Transaction.Direction.INFLOW, "500.00", sf1, ah1, sh1)
    tx(Transaction.Direction.OUTFLOW, "200.00", sf1, ah1, sh1)
    tx(Transaction.Direction.INFLOW, "300.00", sf2, ah2, None)

    for report in (
        build_sub_fund_report(account, fy, date(2035, 7, 31)),
        build_account_head_report(account, fy, date(2035, 7, 31)),
        build_sub_account_head_report(account, fy, date(2035, 7, 31)),
    ):
        assert report["totals"]["opening_balance"] == Decimal("1000.00")
        assert report["totals"]["total_inflows"] == Decimal("800.00")
        assert report["totals"]["total_outflows"] == Decimal("200.00")
        assert report["totals"]["difference"] == Decimal("600.00")
        assert report["totals"]["present_balance"] == Decimal("1600.00")
        assert report["fund_present"] == Decimal("1600.00")
