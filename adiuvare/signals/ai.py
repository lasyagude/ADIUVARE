import json

import httpx

from ..core.models import RequestContext, SignalResult
from .base import SoftSignal


class AISignal(SoftSignal):
    name = "ai"
    weight = 0.05

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "llama3.2:3b",
        timeout: float = 0.8,
        caller=None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/api/generate"
        self._model = model
        self._timeout = timeout
        self._caller = caller

    async def extract(self, ctx: RequestContext) -> SignalResult:
        return await self.review(ctx, 0.0)

    async def review(self, ctx: RequestContext, prior_score: float) -> SignalResult:
        if ctx.snapshot is None or ctx.snapshot.ai_mode == "off":
            return SignalResult(score=0.0, reason="ai_off")

        try:
            data = await self._ask(ctx, prior_score)
        except httpx.TimeoutException:
            return SignalResult(score=0.0, reason="ai_timeout")
        except Exception as exc:
            return SignalResult(score=0.0, reason="ai_error", exception=exc)

        verdict = str(data.get("verdict", "clean")).lower()
        conf = float(data.get("confidence", 0.0))
        reason = str(data.get("reason", "")).strip()

        score = 0.0
        if verdict == "suspicious":
            score = min(0.18, conf * 0.18)
        elif verdict == "malicious":
            score = min(0.30, conf * 0.30)

        return SignalResult(
            score=score,
            reason=f"ai_{verdict}",
            detail={
                "verdict": verdict,
                "confidence": conf,
                "note": reason,
                "model": self._model,
            },
        )

    async def _ask(self, ctx: RequestContext, prior_score: float) -> dict:
        if self._caller is not None:
            return await self._caller(ctx, prior_score)

        prompt = (
            "You are checking API input for abuse.\n"
            f"endpoint: {ctx.endpoint}\n"
            f"prior_score: {prior_score:.2f}\n"
            f"payload: {(ctx.payload or '')[:400]}\n"
            'reply with JSON only: {"verdict":"clean|suspicious|malicious","confidence":0.0,"reason":"..."}'
        )

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            res = await client.post(
                self._url,
                json={"model": self._model, "prompt": prompt, "stream": False},
            )
            res.raise_for_status()
            raw = res.json().get("response", "{}")
        return json.loads(raw)
