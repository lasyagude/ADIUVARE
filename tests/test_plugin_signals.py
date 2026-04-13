import asyncio

from adiuvare.core.models import RequestContext
from adiuvare.guard import Guard
from adiuvare.signals.context import ContextSignal
from adiuvare.signals.ip_rep import IPRepSignal


def test_context_signal_marks_hot_critical_route():
    ctx = RequestContext(
        identity="u1",
        payload="x" * 2200,
        url="/admin/login",
        method="PUT",
        headers={},
        ip="127.0.0.1",
        endpoint="/admin/login",
        sensitivity="critical",
    )

    res = asyncio.run(ContextSignal().extract(ctx))
    assert res.score > 0.3


def test_ip_rep_signal_marks_tor_hint_header():
    ctx = RequestContext(
        identity="u1",
        payload=None,
        url="/",
        method="GET",
        headers={"x-tor-exit": "1"},
        ip="45.155.1.8",
        endpoint="/",
    )

    res = asyncio.run(IPRepSignal().extract(ctx))
    assert res.score >= 0.2


def test_guard_default_pipeline_now_has_more_signal_families():
    guard = Guard()
    names = [sig.name for sig in guard.pipeline._soft_signals]
    assert "context" in names
    assert "ip_rep" in names
