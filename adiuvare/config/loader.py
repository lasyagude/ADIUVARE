import os
from pathlib import Path

import yaml

from ..core.models import ConfigSnapshot
from .schema import AdiuvareConfig, PRESETS


def find_config_file(
    start_dir: str | Path | None = None,
    *,
    include_home: bool = True,
    use_env: bool = True,
) -> Path | None:
    if use_env:
        env_path = os.getenv("ADIUVARE_CONFIG")
        if env_path:
            candidate = _resolve_candidate(Path(env_path))
            if not candidate.exists():
                raise FileNotFoundError(
                    f"ADIUVARE_CONFIG points to {candidate} but that file does not exist"
                )
            return candidate

    start = Path(start_dir) if start_dir is not None else Path.cwd()
    if start.is_file():
        start = start.parent

    for base in [start, *start.parents]:
        candidate = base / "adiuvare.yaml"
        if candidate.exists():
            return candidate

    if include_home:
        home_candidate = Path.home() / "adiuvare.yaml"
        if home_candidate.exists():
            return home_candidate

    return None


def load_config(path: str | Path | None = None, preset: str = "balanced") -> AdiuvareConfig:
    base = PRESETS[preset].model_copy(deep=True).model_dump()
    data = {}

    resolved = _resolve_candidate(Path(path)) if path else find_config_file()
    if path and not resolved.exists():
        raise FileNotFoundError(f"config file not found: {resolved}")
    if resolved and resolved.exists():
        file_data = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        data = file_data

    merged = _merge_dicts(base, data)
    merged = _env_overrides(merged)
    return AdiuvareConfig.model_validate(merged)


def build_snapshot(cfg: AdiuvareConfig) -> ConfigSnapshot:
    return ConfigSnapshot(
        payload_weight=cfg.weights.payload,
        behavior_weight=cfg.weights.behavior,
        identity_weight=cfg.weights.identity,
        flag_threshold=cfg.thresholds.flag,
        throttle_threshold=cfg.thresholds.throttle,
        block_threshold=cfg.thresholds.block,
        observe_only=cfg.runtime.observe_only,
        ai_mode=cfg.ai.mode,
    )


def _merge_dicts(base: dict, patch: dict) -> dict:
    out = dict(base)
    for key, val in patch.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dicts(out[key], val)
        else:
            out[key] = val
    return out


def _resolve_candidate(path: Path) -> Path:
    return path / "adiuvare.yaml" if path.is_dir() else path


def _env_overrides(data: dict) -> dict:
    if ai_mode := os.getenv("ADIUVARE_AI_MODE"):
        data.setdefault("ai", {})
        data["ai"]["mode"] = ai_mode
        data["ai"]["enabled"] = ai_mode != "off"

    if ollama_url := os.getenv("ADIUVARE_OLLAMA_URL"):
        data.setdefault("ai", {})
        data["ai"]["base_url"] = ollama_url

    if redis_url := os.getenv("ADIUVARE_REDIS_URL"):
        data.setdefault("runtime", {})
        data["runtime"]["redis_url"] = redis_url

    if observe := os.getenv("ADIUVARE_OBSERVE_ONLY"):
        data.setdefault("runtime", {})
        data["runtime"]["observe_only"] = observe.lower() in {"1", "true", "yes", "on"}

    if block := os.getenv("ADIUVARE_BLOCK_THRESHOLD"):
        data.setdefault("thresholds", {})
        data["thresholds"]["block"] = float(block)

    return data
