from types import SimpleNamespace

from core.future_budget_proposal_views import _is_outflow_side
from core.models import AccountHead


def test_bulk_outflow_scope_excludes_inflow_only_heads():
    inflow_only = SimpleNamespace(account_head=SimpleNamespace(head_type=AccountHead.HeadType.INFLOW))
    outflow_only = SimpleNamespace(account_head=SimpleNamespace(head_type=AccountHead.HeadType.OUTFLOW))
    both = SimpleNamespace(account_head=SimpleNamespace(head_type=AccountHead.HeadType.BOTH))

    assert _is_outflow_side(inflow_only) is False
    assert _is_outflow_side(outflow_only) is True
    assert _is_outflow_side(both) is True
