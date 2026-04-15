from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ConfigSnapshot:
    payload_weight: float
    behavior_weight: float
    identity_weight: float
    flag_threshold: float
    throttle_threshold: float
    block_threshold: float
    observe_only: bool = False
    ai_mode: str = "off"


@dataclass
class RequestContext:
    identity: str
    payload: str | None
    url: str
    method: str
    headers: dict[str, str]
    ip: str
    endpoint: str
    sensitivity: Literal["public", "internal", "critical"] = "internal"
    snapshot: ConfigSnapshot | None = None


@dataclass
class SignalResult:
    score: float
    reason: str
    detail: dict[str, Any] = field(default_factory=dict)
    exception: Exception | None = None


@dataclass
class AdiuvareEvent:
    identity: str
    endpoint: str
    score: float
    verdict: str
    breakdown: dict[str, float]
    detail: dict[str, Any] = field(default_factory=dict)
