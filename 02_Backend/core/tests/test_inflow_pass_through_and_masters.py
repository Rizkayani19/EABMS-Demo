from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import User

from core.forms import InflowForm, OutflowForm
from core.models import Account, AccountHead, FinancialYear, InflowType, Installation, InternalSection, MajorHead, OutflowNature, Unit, Transaction
from reports.services import build_pass_through_summary


@pytest.mark.django_db
def test_inflow_form_contains_pass_through_and_active_masters():
    installation = Installation.objects.create(installation_code='TEST-01', installation_name='Test Installation')
    account = Account.objects.create(installation=installation, code='TEST', name='Test Account')
    head = AccountHead.objects.create(account=account, code='H1', name='Test Inflow', head_type=AccountHead.HeadType.INFLOW)
    inflow_type = InflowType.objects.create(code='TEST-IN', name='Test Inflow Type')
    unit = Unit.objects.create(code='U1', name='Master Unit')
    section = InternalSection.objects.create(code='S1', name='Master Section')
    fy = FinancialYear.objects.create(code='2099-00', name='Test FY', start_date=date(2099, 1, 1), end_date=date(2099, 12, 31))

    form = InflowForm(financial_year=fy)
    assert 'pass_through' in form.fields
    assert unit in form.fields['transaction_units'].queryset
    assert section in form.fields['transaction_sections'].queryset
    assert head in form.fields['account_head'].queryset
    assert inflow_type in form.fields['inflow_type'].queryset


@pytest.mark.django_db
def test_outflow_form_keeps_pass_through_and_master_attribution():
    installation = Installation.objects.create(installation_code='TEST-02', installation_name='Test Installation 2')
    account = Account.objects.create(installation=installation, code='TEST2', name='Test Account 2')
    AccountHead.objects.create(account=account, code='H2', name='Test Outflow', head_type=AccountHead.HeadType.OUTFLOW)
    OutflowNature.objects.create(code='TEST-OUT', name='Test Nature')
    Unit.objects.create(code='U2', name='Master Unit 2')
    InternalSection.objects.create(code='S2', name='Master Section 2')
    fy = FinancialYear.objects.create(code='2098-00', name='Test FY 2', start_date=date(2098, 1, 1), end_date=date(2098, 12, 31))

    form = OutflowForm(financial_year=fy)
    assert 'pass_through' in form.fields
    assert form.fields['transaction_units'].queryset.filter(name='Master Unit 2').exists()
    assert form.fields['transaction_sections'].queryset.filter(name='Master Section 2').exists()


@pytest.mark.django_db
def test_pass_through_is_valid_for_both_transaction_directions_without_compatibility_hook():
    installation = Installation.objects.create(installation_code='TEST-PT', installation_name='Pass Through Test Installation')
    account = Account.objects.create(installation=installation, code='PT', name='Pass Through Test Account')
    inflow_head = AccountHead.objects.create(account=account, code='PT-I', name='Pass Through Inflow', head_type=AccountHead.HeadType.INFLOW)
    outflow_head = AccountHead.objects.create(account=account, code='PT-O', name='Pass Through Outflow', head_type=AccountHead.HeadType.OUTFLOW)
    fy = FinancialYear.objects.create(code='2096-00', name='Pass Through Test FY', start_date=date(2096, 1, 1), end_date=date(2096, 12, 31))

    inflow = Transaction(
        transaction_number='PT-DIRECT-IN', account=account, financial_year=fy,
        account_head=inflow_head, transaction_date=date(2096, 3, 1),
        direction=Transaction.Direction.INFLOW, amount=Decimal('50.00'),
        pass_through=True, status=Transaction.Status.ACTIVE,
    )
    outflow = Transaction(
        transaction_number='PT-DIRECT-OUT', account=account, financial_year=fy,
        account_head=outflow_head, transaction_date=date(2096, 3, 2),
        direction=Transaction.Direction.OUTFLOW, amount=Decimal('75.00'),
        pass_through=True, status=Transaction.Status.ACTIVE,
    )

    # Model validation must accept the same transaction characteristic for either direction.
    inflow.full_clean()
    outflow.full_clean()


@pytest.mark.django_db
def test_pass_through_summary_reports_both_directions():
    installation = Installation.objects.create(installation_code='TEST-03', installation_name='Test Installation 3')
    account = Account.objects.create(installation=installation, code='TEST3', name='Test Account 3')
    inflow_head = AccountHead.objects.create(account=account, code='H3I', name='Inflow', head_type=AccountHead.HeadType.INFLOW)
    outflow_head = AccountHead.objects.create(account=account, code='H3O', name='Outflow', head_type=AccountHead.HeadType.OUTFLOW)
    fy = FinancialYear.objects.create(code='2097-00', name='Test FY 3', start_date=date(2097, 1, 1), end_date=date(2097, 12, 31))
    user = User.objects.create_user(username='pt-test')
    Transaction.objects.create(transaction_number='PT-IN', account=account, financial_year=fy, account_head=inflow_head, transaction_date=date(2097, 2, 1), direction=Transaction.Direction.INFLOW, amount=Decimal('125.00'), pass_through=True, status=Transaction.Status.ACTIVE, created_by=user)
    Transaction.objects.create(transaction_number='PT-OUT', account=account, financial_year=fy, account_head=outflow_head, transaction_date=date(2097, 2, 2), direction=Transaction.Direction.OUTFLOW, amount=Decimal('80.00'), pass_through=True, status=Transaction.Status.ACTIVE, created_by=user)

    row = build_pass_through_summary({'account': account, 'financial_year': fy})[0]
    assert row['pass_through_inflows'] == Decimal('125.00')
    assert row['pass_through_outflows'] == Decimal('80.00')
    assert row['other_inflows'] == Decimal('0.00')
    assert row['other_outflows'] == Decimal('0.00')


@pytest.mark.django_db
def test_transaction_forms_checkbox_multi_select_widgets():
    from django import forms
    installation = Installation.objects.create(installation_code='TEST-CB', installation_name='Test CB Inst')
    account = Account.objects.create(installation=installation, code='TCB', name='Test CB Account')
    major_head = MajorHead.objects.create(account=account, code='TCBM', name='Sub Fund Tier 1')
    inflow_head = AccountHead.objects.create(account=account, major_head=major_head, code='TCBI', name='Inflow Head', head_type=AccountHead.HeadType.INFLOW)
    outflow_head = AccountHead.objects.create(account=account, major_head=major_head, code='TCBO', name='Outflow Head', head_type=AccountHead.HeadType.OUTFLOW)
    u1 = Unit.objects.create(code='U1', name='Unit Alpha')
    u2 = Unit.objects.create(code='U2', name='Unit Bravo')
    s1 = InternalSection.objects.create(code='S1', name='Section One')
    s2 = InternalSection.objects.create(code='S2', name='Section Two')
    fy = FinancialYear.objects.create(code='2095-00', name='Test FY CB', start_date=date(2095, 1, 1), end_date=date(2095, 12, 31))

    # Test Inflow Form widgets
    inflow_form = InflowForm(account=account, financial_year=fy)
    assert isinstance(inflow_form.fields['transaction_units'].widget, forms.CheckboxSelectMultiple)
    assert isinstance(inflow_form.fields['transaction_sections'].widget, forms.CheckboxSelectMultiple)

    # Test Outflow Form widgets
    outflow_form = OutflowForm(account=account, financial_year=fy)
    assert isinstance(outflow_form.fields['transaction_units'].widget, forms.CheckboxSelectMultiple)
    assert isinstance(outflow_form.fields['transaction_sections'].widget, forms.CheckboxSelectMultiple)

    # Test Form submission and M2M saving with multiple checkbox selections
    user = User.objects.create_user(username='cb-test-user')
    data = {
        'transaction_date': fy.start_date.isoformat(),
        'major_head': str(major_head.id),
        'account_head': str(inflow_head.id),
        'amount': '500.00',
        'payee_or_source': 'Test Org',
        'description': 'Test Inflow Description',
        'transaction_units': [str(u1.id), str(u2.id)],
        'transaction_sections': [str(s1.id), str(s2.id)],
    }
    bound_form = InflowForm(data=data, account=account, financial_year=fy)
    assert bound_form.is_valid(), bound_form.errors
    tx = bound_form.save(commit=False)
    tx.account = account
    tx.financial_year = fy
    tx.direction = Transaction.Direction.INFLOW
    tx.transaction_number = 'TX-CB-001'
    tx.created_by = user
    tx.save()
    bound_form.save_m2m()

    assert tx.transaction_units.count() == 2
    assert set(tx.transaction_units.all()) == {u1, u2}
    assert tx.transaction_sections.count() == 2
    assert set(tx.transaction_sections.all()) == {s1, s2}

