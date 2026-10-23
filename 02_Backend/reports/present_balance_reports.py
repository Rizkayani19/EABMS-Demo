from decimal import Decimal
from core.balance_report_services import (
    build_sub_fund_report,
    build_account_head_report,
    build_sub_account_head_report,
)
from .registry import registry, ReportDefinition


def build_present_sub_fund_report(filters):
    acc = filters.get('account')
    fy = filters.get('financial_year')
    as_of = filters.get('end_date') or filters.get('as_of')
    if not acc or not fy:
        return []
    res = build_sub_fund_report(acc, fy, as_of=as_of)
    return res.get('rows', [])


def build_present_account_head_report(filters):
    acc = filters.get('account')
    fy = filters.get('financial_year')
    as_of = filters.get('end_date') or filters.get('as_of')
    if not acc or not fy:
        return []
    res = build_account_head_report(acc, fy, as_of=as_of)
    return res.get('rows', [])


def build_present_sub_account_head_report(filters):
    acc = filters.get('account')
    fy = filters.get('financial_year')
    as_of = filters.get('end_date') or filters.get('as_of')
    if not acc or not fy:
        return []
    res = build_sub_account_head_report(acc, fy, as_of=as_of)
    return res.get('rows', [])


registry.register(
    ReportDefinition(
        slug='present-sub-fund-balance',
        title='Present Sub-Fund Status vs Start of Year',
        description='Compares live sub-fund cash positions against start-of-year opening allocations, detailing cumulative operational inflows, expenditures, and net available balance.',
        builder_func=build_present_sub_fund_report,
        columns=[
            {'key': 'name', 'label': 'Sub Fund'},
            {'key': 'code', 'label': 'Code'},
            {'key': 'opening_balance', 'label': 'Start of Yr Opening'},
            {'key': 'total_inflows', 'label': 'Total Inflows'},
            {'key': 'total_outflows', 'label': 'Total Outflows'},
            {'key': 'difference', 'label': 'Net Movement'},
            {'key': 'present_balance', 'label': 'Present Balance'},
        ],
        supported_filters=['account', 'financial_year', 'end_date'],
        totals=['opening_balance', 'total_inflows', 'total_outflows', 'difference', 'present_balance'],
        display_in_millions=True,
    )
)

registry.register(
    ReportDefinition(
        slug='present-account-head-balance',
        title='Present Account Head Balance vs Start of Year',
        description='Head-wise live balance reconciliation against start-of-year position, capturing unallocated opening cash and head-level movements.',
        builder_func=build_present_account_head_report,
        columns=[
            {'key': 'name', 'label': 'Account Head'},
            {'key': 'code', 'label': 'Code'},
            {'key': 'opening_balance', 'label': 'Start of Yr Opening'},
            {'key': 'total_inflows', 'label': 'Total Inflows'},
            {'key': 'total_outflows', 'label': 'Total Outflows'},
            {'key': 'difference', 'label': 'Net Movement'},
            {'key': 'present_balance', 'label': 'Present Balance'},
        ],
        supported_filters=['account', 'financial_year', 'end_date'],
        totals=['opening_balance', 'total_inflows', 'total_outflows', 'difference', 'present_balance'],
        display_in_millions=True,
    )
)

registry.register(
    ReportDefinition(
        slug='present-sub-account-head-balance',
        title='Present Sub-Head Balance vs Start of Year',
        description='Granular sub-account head live balance status compared against opening position with cumulative receipts and payments.',
        builder_func=build_present_sub_account_head_report,
        columns=[
            {'key': 'name', 'label': 'Sub Account Head'},
            {'key': 'code', 'label': 'Code'},
            {'key': 'opening_balance', 'label': 'Start of Yr Opening'},
            {'key': 'total_inflows', 'label': 'Total Inflows'},
            {'key': 'total_outflows', 'label': 'Total Outflows'},
            {'key': 'difference', 'label': 'Net Movement'},
            {'key': 'present_balance', 'label': 'Present Balance'},
        ],
        supported_filters=['account', 'financial_year', 'end_date'],
        totals=['opening_balance', 'total_inflows', 'total_outflows', 'difference', 'present_balance'],
        display_in_millions=True,
    )
)
