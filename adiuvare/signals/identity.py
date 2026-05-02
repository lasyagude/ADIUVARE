from ..core.models import RequestContext, SignalResult
from ..state.identity_store import IdentityStore
from .base import SoftSignal


class IdentitySignal(SoftSignal):
    name = "identity"
    weight = 0.25

    def __init__(self, id_store: IdentityStore) -> None:
        self._id_store = id_store

    async def extract(self, ctx: RequestContext) -> SignalResult:
        win = self._id_store.get(ctx.identity)
        score = win.score_ewma

        if win.seen > 10:
            score = min(1.0, score + 0.10)

        detail = {}
        monitored = win.monitored_remaining > 0
        if monitored:
            score = min(1.0, score * win.monitored_multiplier)
            detail = {
                "monitored_remaining": win.monitored_remaining,
                "monitored_multiplier": win.monitored_multiplier,
            }

        if score == 0.0:
            return SignalResult(score=0.0, reason="identity_clean")

        return SignalResult(
            score=score,
            reason="identity_monitored" if monitored else "identity_flag",
            detail=detail,
        )
