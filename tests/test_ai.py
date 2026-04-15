import asyncio

from adiuvare.core.models import ConfigSnapshot, RequestContext
from adiuvare.core.pipeline import Pipeline
from adiuvare.signals.ai import AISignal
from adiuvare.state.identity_store import IdentityStore


async def _fake_call(ctx, prior_score):
    return {
        "verdict": "suspicious",
        "confidence": 0.8,
        "reason": f"looked odd near {ctx.endpoint} at {prior_score:.2f}",
    }


def test_ai_signal_stays_off_without_mode():
    sig = AISignal(caller=_fake_call)
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
    )

    res = asyncio.run(sig.extract(ctx))
    assert res.reason == "ai_off"


def test_ai_signal_parses_mock_result():
    sig = AISignal(caller=_fake_call)
    snap = ConfigSnapshot(
        payload_weight=0.4,
        behavior_weight=0.35,
        identity_weight=0.25,
        flag_threshold=0.25,
        throttle_threshold=0.55,
        block_threshold=0.8,
        ai_mode="assist",
    )
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={},
        ip="127.0.0.1",
        endpoint="/login",
        snapshot=snap,
    )

    res = asyncio.run(sig.review(ctx, 0.41))
    assert res.reason == "ai_suspicious"
    assert res.detail["verdict"] == "suspicious"


def test_pipeline_carries_ai_detail_in_event():
    snap = ConfigSnapshot(
        payload_weight=0.4,
        behavior_weight=0.35,
        identity_weight=0.25,
        flag_threshold=0.25,
        throttle_threshold=0.55,
        block_threshold=0.8,
        ai_mode="assist",
    )
    ctx = RequestContext(
        identity="u1",
        payload="select * from users",
        url="/login",
        method="POST",
        headers={"User-Agent": "Mozilla/5.0"},
        ip="127.0.0.1",
        endpoint="/login",
        snapshot=snap,
    )

    pipe = Pipeline(IdentityStore(), ai_sig=AISignal(caller=_fake_call))
    gate, event = asyncio.run(pipe.process(ctx))
    assert gate.passed is True
    assert event is not None
    assert event.detail["ai"]["verdict"] == "suspicious"
