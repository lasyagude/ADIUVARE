from ..core.models import RequestContext, SignalResult
from .base import SoftSignal


class ContextSignal(SoftSignal):
    name = "context"
    weight = 0.10

    async def extract(self, ctx: RequestContext) -> SignalResult:
        score = 0.0
        detail = {}

        if ctx.sensitivity == "critical":
            score += 0.14
            detail["sensitivity"] = "critical"

        if ctx.method not in {"GET", "POST"}:
            score += 0.10
            detail["method"] = ctx.method

        if len(ctx.payload or "") > 2000:
            score += 0.16
            detail["big_payload"] = True

        if ctx.endpoint.startswith("/admin") or "/auth" in ctx.endpoint:
            score += 0.08
            detail["hot_route"] = True

        if score == 0.0:
            return SignalResult(score=0.0, reason="ctx_clean")

        return SignalResult(score=min(1.0, score), reason="ctx_risk", detail=detail)
