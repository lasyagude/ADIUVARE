from ..core.models import AdiuvareEvent, SignalResult
from ..core.gate import run_trackA
from ..core.scorer import compute_score
from ..core.verdict import compute_verdict
from ..signals.ai import AISignal
from ..signals.behavior import BehaviorSignal
from ..signals.identity import IdentitySignal
from ..signals.payload import PayloadSignal
from ..state.identity_store import IdentityStore


class Pipeline:
    def __init__(
        self,
        id_store: IdentityStore,
        soft_signals: list | None = None,
        ai_sig: AISignal | None = None,
    ) -> None:
        self._id_store = id_store
        self._soft_signals = soft_signals or [
            PayloadSignal(),
            BehaviorSignal(id_store),
            IdentitySignal(id_store),
        ]
        self._ai_sig = ai_sig or AISignal()

    async def process(self, ctx):
        gate = run_trackA(ctx, self._id_store)
        if not gate.passed:
            return gate, None

        event = await self.trackB(ctx)
        return gate, event

    async def trackB(self, ctx):
        sig_res = {}
        for sig in self._soft_signals:
            try:
                sig_res[sig.name] = await sig.extract(ctx)
            except Exception as exc:
                sig_res[sig.name] = SignalResult(
                    score=0.0,
                    reason="signal_error",
                    exception=exc,
                )

        score, breakdown = compute_score(sig_res, ctx.snapshot)
        identity_risk = sig_res.get("identity").score if "identity" in sig_res else 0.0
        payload_risk = sig_res.get("payload").score if "payload" in sig_res else 0.0
        ai_res = None
        if ctx.snapshot and ctx.snapshot.ai_mode != "off":
            ai_res = await self._ai_sig.review(ctx, score)
        verdict = compute_verdict(
            score,
            ctx.snapshot,
            identity_risk=identity_risk,
            payload_risk=payload_risk,
        )
        detail = {"signal_reasons": {name: res.reason for name, res in sig_res.items()}}
        if ai_res is not None:
            detail["ai"] = ai_res.detail
        self._id_store.apply_score(ctx.identity, score)
        event = AdiuvareEvent(
            identity=ctx.identity,
            endpoint=ctx.endpoint,
            score=score,
            verdict=verdict,
            breakdown=breakdown,
            detail=detail,
        )
        return event
