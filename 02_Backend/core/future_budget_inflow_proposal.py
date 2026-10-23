from decimal import Decimal, InvalidOperation


KEY = "user_proposed_inflow"


def get_user_proposed_inflow(line):
    """Return the Draft management inflow proposal stored in the line suggestion payload."""
    payload = line.suggestion_breakdown or {}
    raw = payload.get(KEY)
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return None


def set_user_proposed_inflow(line, amount):
    """Store the Draft management inflow proposal without conflating it with approval."""
    payload = dict(line.suggestion_breakdown or {})
    if amount is None:
        payload.pop(KEY, None)
    else:
        payload[KEY] = format(Decimal(str(amount)).quantize(Decimal("0.01")), "f")
    line.suggestion_breakdown = payload
