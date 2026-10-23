"""
ABMS Custom Template Filters
Centralises application-wide date, month-year and amount formatting.
Standards:
  Date       -> DD-MM-YYYY
  Month-Year -> MMM YY (e.g. Jun 25)
  Amount     -> 1,234.56 / Rs 1,234.56
  Arithmetic -> Decimal, never float for financial values.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, date
from django import template

register = template.Library()
CURRENCY_SYMBOL = '$'
TWO_PLACES = Decimal('0.01')


def _to_decimal(value):
    if value is None or value == '':
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


@register.filter(name='dmy')
def format_dmy(value):
    """DD-MM-YYYY."""
    if not value:
        return '—'
    d = _as_date(value)
    if d:
        return d.strftime('%d-%m-%Y')
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').strftime('%d-%m-%Y')
    except (ValueError, TypeError):
        return str(value)


@register.filter(name='mmy')
def format_mmy(value):
    """MMM YY, e.g. Jun 25."""
    if not value:
        return '—'
    d = _as_date(value)
    if d:
        return d.strftime('%b %y')
    text = str(value)
    for fmt in ('%Y-%m', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).strftime('%b %y')
        except ValueError:
            pass
    return text


@register.filter(name='mmyyyy')
def format_mmyyyy(value):
    """MMM YYYY for exceptional administrative contexts only."""
    if not value:
        return '—'
    d = _as_date(value)
    if d:
        return d.strftime('%b %Y')
    return str(value)


@register.filter(name='ym')
def format_ym(value):
    return format_mmy(value)


@register.filter(name='rs')
def format_rs(value):
    return f'{CURRENCY_SYMBOL} {_to_decimal(value):,.2f}'


@register.filter(name='rs_abs')
def format_rs_abs(value):
    return f'{CURRENCY_SYMBOL} {abs(_to_decimal(value)):,.2f}'


@register.filter(name='rs_signed')
def format_rs_signed(value):
    d = _to_decimal(value)
    return f'+{CURRENCY_SYMBOL} {d:,.2f}' if d >= 0 else f'-{CURRENCY_SYMBOL} {abs(d):,.2f}'


@register.filter(name='rs_mn')
def format_rs_mn(value):
    d = _to_decimal(value)
    mn = (d / Decimal('1000000')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f'{CURRENCY_SYMBOL} {mn:,.2f} Mn'


@register.filter(name='rs_mn_signed')
def format_rs_mn_signed(value):
    d = _to_decimal(value)
    mn = (d / Decimal('1000000')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f'+{CURRENCY_SYMBOL} {mn:,.2f} Mn' if mn >= 0 else f'-{CURRENCY_SYMBOL} {abs(mn):,.2f} Mn'


@register.filter(name='mn2')
def format_mn2(value):
    d = _to_decimal(value)
    mn = (d / Decimal('1000000')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f'{mn:,.2f}'


@register.filter(name='pct')
def format_pct(value):
    if value is None or value == '':
        return '—'
    try:
        return f'{_to_decimal(value):,.2f}%'
    except Exception:
        return '—'


@register.filter(name='dp2')
def format_dp2(value):
    return f'{_to_decimal(value):,.2f}'


@register.filter(name='sum_attr')
def sum_attr(values, attr=''):
    """Sum a numeric/Decimal attribute from an iterable, preserving Decimal."""
    total = Decimal('0.00')
    if not values:
        return total
    for item in values:
        try:
            value = getattr(item, attr, None) if attr else item
            total += _to_decimal(value)
        except (TypeError, ValueError, InvalidOperation):
            continue
    return total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# Keys commonly used by ABMS report datasets for financial values.
_AMOUNT_KEYWORDS = (
    'amount', 'balance', 'budget', 'inflow', 'outflow', 'received',
    'expected', 'pending', 'consumed', 'reimbursement', 'opening',
    'movement', 'expenditure', 'available', 'total', 'routine',
    'addl', 'pass_through', 'operational_outflows', 'prior_actual',
    'curr_budget', 'curr_actual', 'budget_balance', 'yoy_variance'
)


@register.filter(name='abms_value')
def format_abms_value(value, key=''):
    """Context-aware report cell formatter used by screen reports."""
    key = str(key or '').lower()
    if value is None or value == '':
        return '—'
    if 'utilisation' in key or 'utilization' in key or key.endswith('_pct') or key == 'pct':
        return format_pct(value)
    if key == 'month' or key.endswith('_month'):
        return format_mmy(value)
    if 'date' in key or key.endswith('_at'):
        return format_dmy(value)
    if any(token in key for token in _AMOUNT_KEYWORDS) and not isinstance(value, str):
        return format_rs(value)
    return str(value)


@register.filter(name='abms_value_mn')
def format_abms_value_mn(value, key=''):
    key = str(key or '').lower()
    if value is None or value == '':
        return '-'
    if 'utilisation' in key or 'utilization' in key or key.endswith('_pct') or key == 'pct':
        return format_pct(value)
    if key == 'month' or key.endswith('_month'):
        return format_mmy(value)
    if 'date' in key or key.endswith('_at'):
        return format_dmy(value)
    if any(token in key for token in _AMOUNT_KEYWORDS) and not isinstance(value, str):
        return format_rs_mn(value)
    return str(value)

TWO_PLACES = Decimal('0.01')


def _to_decimal(value):
    if value is None or value == '':
        return Decimal('0.00')
    if isinstance(value, Decimal):
        return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    try:
        return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal('0.00')


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


@register.filter(name='dmy')
def format_dmy(value):
    """DD-MM-YYYY."""
    if not value:
        return '—'
    d = _as_date(value)
    if d:
        return d.strftime('%d-%m-%Y')
    try:
        return datetime.strptime(str(value), '%Y-%m-%d').strftime('%d-%m-%Y')
    except (ValueError, TypeError):
        return str(value)


@register.filter(name='mmy')
def format_mmy(value):
    """MMM YY, e.g. Jun 25."""
    if not value:
        return '—'
    d = _as_date(value)
    if d:
        return d.strftime('%b %y')
    text = str(value)
    for fmt in ('%Y-%m', '%Y-%m-%d'):
        try:
            return datetime.strptime(text, fmt).strftime('%b %y')
        except ValueError:
            pass
    return text


@register.filter(name='mmyyyy')
def format_mmyyyy(value):
    """MMM YYYY for exceptional administrative contexts only."""
    if not value:
        return '—'
    d = _as_date(value)
    if d:
        return d.strftime('%b %Y')
    return str(value)


@register.filter(name='ym')
def format_ym(value):
    return format_mmy(value)


@register.filter(name='rs')
def format_rs(value):
    return f'{CURRENCY_SYMBOL} {_to_decimal(value):,.2f}'


@register.filter(name='rs_abs')
def format_rs_abs(value):
    return f'{CURRENCY_SYMBOL} {abs(_to_decimal(value)):,.2f}'


@register.filter(name='rs_signed')
def format_rs_signed(value):
    d = _to_decimal(value)
    return f'+{CURRENCY_SYMBOL} {d:,.2f}' if d >= 0 else f'-{CURRENCY_SYMBOL} {abs(d):,.2f}'


@register.filter(name='rs_mn')
def format_rs_mn(value):
    d = _to_decimal(value)
    mn = (d / Decimal('1000000')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f'{CURRENCY_SYMBOL} {mn:,.2f} Mn'


@register.filter(name='rs_mn_signed')
def format_rs_mn_signed(value):
    d = _to_decimal(value)
    mn = (d / Decimal('1000000')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f'+{CURRENCY_SYMBOL} {mn:,.2f} Mn' if mn >= 0 else f'-{CURRENCY_SYMBOL} {abs(mn):,.2f} Mn'


@register.filter(name='mn2')
def format_mn2(value):
    d = _to_decimal(value)
    mn = (d / Decimal('1000000')).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    return f'{mn:,.2f}'


@register.filter(name='pct')
def format_pct(value):
    if value is None or value == '':
        return '—'
    try:
        return f'{_to_decimal(value):,.2f}%'
    except Exception:
        return '—'


@register.filter(name='dp2')
def format_dp2(value):
    return f'{_to_decimal(value):,.2f}'


@register.filter(name='sum_attr')
def sum_attr(values, attr=''):
    """Sum a numeric/Decimal attribute from an iterable, preserving Decimal."""
    total = Decimal('0.00')
    if not values:
        return total
    for item in values:
        try:
            value = getattr(item, attr, None) if attr else item
            total += _to_decimal(value)
        except (TypeError, ValueError, InvalidOperation):
            continue
    return total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


# Keys commonly used by ABMS report datasets for financial values.
_AMOUNT_KEYWORDS = (
    'amount', 'balance', 'budget', 'inflow', 'outflow', 'received',
    'expected', 'pending', 'consumed', 'reimbursement', 'opening',
    'movement', 'expenditure', 'available', 'total', 'routine',
    'addl', 'pass_through', 'operational_outflows', 'prior_actual',
    'curr_budget', 'curr_actual', 'budget_balance', 'yoy_variance'
)


@register.filter(name='abms_value')
def format_abms_value(value, key=''):
    """Context-aware report cell formatter used by screen reports."""
    key = str(key or '').lower()
    if value is None or value == '':
        return '—'
    if 'utilisation' in key or 'utilization' in key or key.endswith('_pct') or key == 'pct':
        return format_pct(value)
    if key == 'month' or key.endswith('_month'):
        return format_mmy(value)
    if 'date' in key or key.endswith('_at'):
        return format_dmy(value)
    if any(token in key for token in _AMOUNT_KEYWORDS) and not isinstance(value, str):
        return format_rs(value)
    return str(value)


@register.filter(name='abms_value_mn')
def format_abms_value_mn(value, key=''):
    key = str(key or '').lower()
    if value is None or value == '':
        return '-'
    if 'utilisation' in key or 'utilization' in key or key.endswith('_pct') or key == 'pct':
        return format_pct(value)
    if key == 'month' or key.endswith('_month'):
        return format_mmy(value)
    if 'date' in key or key.endswith('_at'):
        return format_dmy(value)
    if any(token in key for token in _AMOUNT_KEYWORDS) and not isinstance(value, str):
        return format_rs_mn(value)
    return str(value)
