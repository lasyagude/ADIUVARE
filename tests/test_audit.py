import asyncio
import json
import sqlite3

from adiuvare import Guard
from adiuvare.core.models import AdiuvareEvent
from adiuvare.state.audit_log import AuditLog
from adiuvare.state.identity_store import IdentityStore
from adiuvare.state.persistence import (
    checkpoint_state,
    init_state_db,
    load_whitelist_state,
    save_identity_state,
    save_whitelist_state,
)
from adiuvare.state.whitelist import WhitelistStore


def test_audit_log_writes_event(tmp_path):
    db_path = tmp_path / "audit.db"
    log = AuditLog(db_path)
    event = AdiuvareEvent(
        identity="u1",
        endpoint="/login",
        score=0.42,
        verdict="flag",
        breakdown={"payload": 0.28, "identity": 0.14},
    )

    log.write(event)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "select identity, verdict, breakdown_json from audit_events"
        ).fetchone()

    assert row is not None
    assert row[0] == "u1"
    assert row[1] == "flag"
    assert json.loads(row[2])["payload"] == 0.28


def test_state_checkpoint_writes_identity_window(tmp_path):
    db_path = tmp_path / "audit.db"
    store = IdentityStore()
    win = store.get("u1")
    win.seen = 3
    win.score_ewma = 0.42
    win.monitored_remaining = 7
    win.monitored_multiplier = 1.4
    store.update("u1", win)

    init_state_db(db_path)
    save_identity_state(db_path, store)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            select
                identity,
                seen,
                score_ewma,
                monitored_remaining,
                monitored_multiplier
            from identity_state
            """
        ).fetchone()

    assert row == ("u1", 3, 0.42, 7, 1.4)


def test_audit_log_query_helpers_work(tmp_path):
    db_path = tmp_path / "audit.db"
    log = AuditLog(db_path)
    first = AdiuvareEvent(
        identity="u1",
        endpoint="/login",
        score=0.42,
        verdict="flag",
        breakdown={"payload": 0.28},
        detail={"ai": {"verdict": "suspicious"}},
    )
    second = AdiuvareEvent(
        identity="u2",
        endpoint="/pay",
        score=0.88,
        verdict="block",
        breakdown={"payload": 0.4},
    )
    log.write(first)
    log.write(second)

    recent = log.recent()
    mine = log.by_identity("u1")
    assert recent[0]["identity"] == "u2"
    assert mine[0]["detail"]["ai"]["verdict"] == "suspicious"


def test_checkpoint_state_helper_runs(tmp_path):
    db_path = tmp_path / "audit.db"
    store = IdentityStore()
    store.bump("u1")
    checkpoint_state(db_path, store)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("select identity, seen from identity_state").fetchone()

    assert row == ("u1", 1)


def test_whitelist_state_round_trip(tmp_path):
    db_path = tmp_path / "state.db"
    wl = WhitelistStore()
    wl.add("u1")
    wl.add("u2")
    wl.ban_ip("203.0.113.4")

    init_state_db(db_path)
    save_whitelist_state(db_path, wl)

    loaded = WhitelistStore()
    load_whitelist_state(db_path, loaded)

    assert loaded.allows("u1") is True
    assert loaded.allows("u2") is True
    assert loaded.ip_blocked("203.0.113.4") is True


def test_guard_stream_command_path_updates_runtime_state(tmp_path):
    guard = Guard()
    guard._audit = AuditLog(tmp_path / "audit.db")
    guard._state_DBpath = tmp_path / "state.db"

    snap = asyncio.run(guard.event_stream.command("get_runtime_snapshot", {}))
    assert "ai_mode" in snap

    block = asyncio.run(
        guard.event_stream.command(
            "confirm_block",
            {"identity": "u1", "ttl_secs": 60},
        )
    )
    assert block["ok"] is True
    assert guard._id_store.is_blocked("u1") is True

    allow = asyncio.run(
        guard.event_stream.command(
            "unblock_whitelist",
            {"identity": "u1"},
        )
    )
    assert allow["ok"] is True
    assert guard.whitelist.allows("u1") is True

    monitored = asyncio.run(
        guard.event_stream.command(
            "monitor_identity",
            {"identity": "u2", "requests": 6, "multiplier": 1.3},
        )
    )
    assert monitored["ok"] is True
    assert monitored["monitored"] is True
    assert guard._id_store.get("u2").monitored_remaining == 6

    unblocked = asyncio.run(
        guard.event_stream.command(
            "unblock_monitor",
            {"identity": "u3", "requests": 4, "multiplier": 1.4},
        )
    )
    assert unblocked["ok"] is True
    assert guard._id_store.get("u3").monitored_remaining == 4

    cleared = asyncio.run(
        guard.event_stream.command(
            "unmonitor_identity",
            {"identity": "u3"},
        )
    )
    assert cleared["ok"] is True
    assert guard._id_store.get("u3").monitored_remaining == 0

    banned = asyncio.run(
        guard.event_stream.command(
            "ban_ip",
            {"ip": "203.0.113.4"},
        )
    )
    assert banned["ok"] is True
    assert banned["banned"] is True
    assert guard.whitelist.ip_blocked("203.0.113.4") is True

    unbanned = asyncio.run(
        guard.event_stream.command(
            "unban_ip",
            {"ip": "203.0.113.4"},
        )
    )
    assert unbanned["ok"] is True
    assert unbanned["banned"] is False
    assert guard.whitelist.ip_blocked("203.0.113.4") is False

    patched = asyncio.run(
        guard.event_stream.command(
            "patch_config",
            {"changes": {"ai_mode": "assist", "observe_only": True}},
        )
    )
    assert patched["ai_mode"] == "assist"
    assert patched["observe_only"] is True
    assert patched["ai_enabled"] is True


def test_guard_startup_loads_persisted_operator_state(tmp_path):
    first = Guard()
    first._audit = AuditLog(tmp_path / "audit.db")
    first._state_DBpath = tmp_path / "state.db"
    asyncio.run(
        first.event_stream.command(
            "unblock_whitelist",
            {"identity": "u1"},
        )
    )
    asyncio.run(
        first.event_stream.command(
            "ban_ip",
            {"ip": "203.0.113.4"},
        )
    )
    asyncio.run(
        first.event_stream.command(
            "monitor_identity",
            {"identity": "u2", "requests": 9, "multiplier": 1.4},
        )
    )

    async def run():
        second = Guard()
        second._audit = AuditLog(tmp_path / "audit.db")
        second._state_DBpath = tmp_path / "state.db"
        await second.startbgtasks()
        try:
            assert second.whitelist.allows("u1") is True
            assert second.whitelist.ip_blocked("203.0.113.4") is True
            assert second._id_store.get("u2").monitored_remaining == 9
            assert second._id_store.get("u2").monitored_multiplier == 1.4
        finally:
            await second.shutdown()

    asyncio.run(run())


def test_guard_analysis_commands_return_report_and_answer(tmp_path):
    guard = Guard()
    guard._audit = AuditLog(tmp_path / "audit.db")
    guard._state_DBpath = tmp_path / "state.db"
    guard._audit.write(
        AdiuvareEvent(
            identity="u1",
            endpoint="/login",
            score=0.82,
            verdict="block",
            breakdown={"payload": 0.5, "behavior": 0.2},
        )
    )
    guard._audit.write(
        AdiuvareEvent(
            identity="u2",
            endpoint="/search",
            score=0.31,
            verdict="flag",
            breakdown={"payload": 0.1, "context": 0.2},
        )
    )

    report = asyncio.run(
        guard.event_stream.command("get_analysis_report", {"window": "7d"})
    )
    assert report["source"] == "local"
    assert report["stats"]["events"] == 2
    assert report["stats"]["block"] == 1
    assert report["signal_pressure"][0]["signal"] == "payload"

    answer = asyncio.run(
        guard.event_stream.command(
            "ask_ai_analyst",
            {"question": "what is the top threat right now?", "window": "7d"},
        )
    )
    assert answer["source"] == "local"
    assert "strongest recent event" in answer["answer"].lower()


def test_guard_analysis_report_can_use_ai_summary(tmp_path):
    guard = Guard()
    guard._audit = AuditLog(tmp_path / "audit.db")
    guard._state_DBpath = tmp_path / "state.db"
    guard._cfg.ai.enabled = True
    guard._audit.write(
        AdiuvareEvent(
            identity="u1",
            endpoint="/login",
            score=0.82,
            verdict="block",
            breakdown={"payload": 0.5},
        )
    )

    async def fake_complete_json(_prompt: str):
        return {
            "summary": "AI summary",
            "findings": ["AI finding"],
            "recommendations": ["AI recommendation"],
        }

    async def fake_complete_text(_prompt: str):
        return "AI analyst answer"

    guard.pipeline._ai_sig.complete_json = fake_complete_json
    guard.pipeline._ai_sig.complete_text = fake_complete_text

    report = asyncio.run(
        guard.event_stream.command("get_analysis_report", {"window": "7d"})
    )
    assert report["source"] == "ai"
    assert report["summary"] == "AI summary"
    assert report["findings"] == ["AI finding"]

    answer = asyncio.run(
        guard.event_stream.command(
            "ask_ai_analyst",
            {"question": "what should we fix first?", "window": "7d"},
        )
    )
    assert answer["source"] == "ai"
    assert answer["answer"] == "AI analyst answer"


def test_guard_analysis_report_can_fallback_to_ai_text_summary(tmp_path):
    guard = Guard()
    guard._audit = AuditLog(tmp_path / "audit.db")
    guard._state_DBpath = tmp_path / "state.db"
    guard._cfg.ai.enabled = True
    guard._audit.write(
        AdiuvareEvent(
            identity="u1",
            endpoint="/login",
            score=0.82,
            verdict="block",
            breakdown={"payload": 0.5},
        )
    )

    async def fake_complete_json(_prompt: str):
        return {}

    async def fake_complete_text(_prompt: str):
        return "AI text summary"

    guard.pipeline._ai_sig.complete_json = fake_complete_json
    guard.pipeline._ai_sig.complete_text = fake_complete_text

    report = asyncio.run(
        guard.event_stream.command("get_analysis_report", {"window": "7d"})
    )
    assert report["source"] == "ai"
    assert report["summary"] == "AI text summary"


def test_checkpoint_loop_picks_up_new_identity(tmp_path):
    db_path = tmp_path / "state.db"
    store = IdentityStore()
    store.bump("u9")

    async def run():
        from adiuvare.state.persistence import start_checkpoint_loop

        task = asyncio.create_task(start_checkpoint_loop(db_path, store, interval_secs=0.01))
        try:
            await asyncio.sleep(0.03)
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    import contextlib

    asyncio.run(run())

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("select identity, seen from identity_state").fetchone()

    assert row == ("u9", 1)
