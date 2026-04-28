import importlib.util
from pathlib import Path

import pytest

from adiuvare.core.models import AdiuvareEvent


HAS_TEXTUAL = importlib.util.find_spec("textual") is not None

if HAS_TEXTUAL:
    from textual.widgets import Button, ContentSwitcher, Select
    from adiuvare.tui.app import AdiuvareApp
    from adiuvare.tui.wizard import SetupWizardApp


@pytest.fixture
def app(tmp_path):
    if not HAS_TEXTUAL:
        pytest.skip("textual not installed")
    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        "\n".join(
                [
                    "runtime:",
                    f"  audit_db_path: '{(tmp_path / 'audit.db').as_posix()}'",
                    f"  state_db_path: '{(tmp_path / 'state.db').as_posix()}'",
                    "ai:",
                    "  mode: 'off'",
                ]
            ),
            encoding="utf-8",
        )
    return AdiuvareApp(config_path=str(cfg))


@pytest.fixture
def connected_app(tmp_path, monkeypatch):
    if not HAS_TEXTUAL:
        pytest.skip("textual not installed")

    cfg = tmp_path / "adiuvare.yaml"
    cfg.write_text(
        "\n".join(
            [
                "runtime:",
                f"  audit_db_path: '{(tmp_path / 'audit.db').as_posix()}'",
                f"  state_db_path: '{(tmp_path / 'state.db').as_posix()}'",
                "ai:",
                "  mode: 'off'",
            ]
        ),
        encoding="utf-8",
    )

    async def fake_subscribe(self):
        if False:
            yield {}

    calls = []

    async def fake_command(self, name, args=None):
        calls.append((name, args or {}))
        if name == "get_runtime_snapshot":
            return {
                "backend": "redis",
                "whitelist_size": 2,
                "recent_events": 1,
            }
        return {"ok": True}

    monkeypatch.setattr("adiuvare.tui.app.EventStreamClient.subscribe", fake_subscribe)
    monkeypatch.setattr("adiuvare.tui.app.EventStreamClient.command", fake_command)

    app = AdiuvareApp(socket_path="demo.sock", config_path=str(cfg))
    app._stream_rows = [
        {
            "identity": "live:user",
            "endpoint": "/review",
            "score": 0.91,
            "verdict": "block",
            "breakdown": {"payload": 0.91},
        }
    ]
    app._test_calls = calls
    return app


@pytest.mark.asyncio
async def test_tui_starts_on_monitor(app):
    async with app.run_test() as _pilot:
        switcher = app.query_one("#body-switcher", ContentSwitcher)
        assert switcher.current == "monitor-view"
        assert app.query_one("#tab-monitor", Button).has_class("-active")


@pytest.mark.asyncio
async def test_tui_switches_tabs(app):
    async with app.run_test() as pilot:
        await pilot.press("2")
        switcher = app.query_one("#body-switcher", ContentSwitcher)
        assert switcher.current == "events-view"
        assert app.query_one("#tab-events", Button).has_class("-active")


@pytest.mark.asyncio
async def test_monitor_reads_recent_audit_rows(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:1",
            endpoint="GET /login",
            score=0.74,
            verdict="flag",
            breakdown={"payload": 0.74},
        )
    )
    async with app.run_test() as _pilot:
        table = app.query_one("#monitor-stream")
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_connected_monitor_reads_live_stream_rows(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        table = connected_app.query_one("#monitor-stream")
        profile = str(connected_app.query_one("#runtime-profile").content)
        snapshot = str(connected_app.query_one("#runtime-snapshot").content)
        assert table.row_count == 1
        assert "backend: redis" in profile
        assert "live link: True" in snapshot


@pytest.mark.asyncio
async def test_monitor_shows_profile_and_thresholds(app):
    async with app.run_test() as _pilot:
        profile = str(app.query_one("#runtime-profile").content)
        counts = str(app.query_one("#runtime-counts").content)
        assert "framework: fastapi" in profile
        assert "block: 0.80" in counts


@pytest.mark.asyncio
async def test_events_filter_reduces_rows(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:a",
            endpoint="GET /a",
            score=0.70,
            verdict="flag",
            breakdown={"payload": 0.70},
        )
    )
    app.audit.write(
        AdiuvareEvent(
            identity="user:b",
            endpoint="GET /b",
            score=0.82,
            verdict="block",
            breakdown={"payload": 0.82},
        )
    )
    async with app.run_test() as pilot:
        await pilot.press("2")
        field = app.query_one("#events-identity-filter")
        field.value = "user:a"
        await pilot.pause()
        table = app.query_one("#events-table")
        assert table.row_count == 1


@pytest.mark.asyncio
async def test_connected_events_actions_use_runtime_commands(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        connected_app.query_one("#events-confirm", Button).press()
        connected_app.query_one("#events-whitelist", Button).press()
        note = connected_app.query_one("#events-note-input")
        note.value = "keep"
        connected_app.query_one("#events-note", Button).press()
        await pilot.pause()

    assert ("confirm_block", {"identity": "live:user"}) in connected_app._test_calls
    assert ("unblock_whitelist", {"identity": "live:user"}) in connected_app._test_calls
    assert ("unblock_note", {"identity": "live:user", "note": "keep"}) in connected_app._test_calls


@pytest.mark.asyncio
async def test_slash_focuses_events_filter(app):
    async with app.run_test() as pilot:
        await pilot.press("2")
        await pilot.press("/")
        assert app.focused is app.query_one("#events-identity-filter")


@pytest.mark.asyncio
async def test_config_save_updates_yaml(app):
    async with app.run_test() as pilot:
        await pilot.press("3")
        block = app.query_one("#cfg-block")
        block.value = "0.73"
        ai = app.query_one("#cfg-ai")
        ai.value = "assist"
        await pilot.click("#cfg-save")
        saved = Path(app.config_path).read_text(encoding="utf-8")
        assert "0.73" in saved
        assert "assist" in saved


@pytest.mark.asyncio
async def test_connected_config_save_sends_runtime_patch(connected_app):
    async with connected_app.run_test() as pilot:
        await pilot.press("3")
        connected_app.query_one("#cfg-block").value = "0.73"
        connected_app.query_one("#cfg-ai").value = "assist"
        await pilot.click("#cfg-save")
        await pilot.pause()

    assert ("patch_config", {"block_threshold": 0.73, "observe_only": False, "ai_mode": "assist"}) in connected_app._test_calls


@pytest.mark.asyncio
async def test_analyst_ask_updates_output(app):
    app.audit.write(
        AdiuvareEvent(
            identity="user:lead",
            endpoint="POST /login",
            score=0.76,
            verdict="flag",
            breakdown={"behavior": 0.76},
        )
    )
    async with app.run_test() as pilot:
        await pilot.press("5")
        ask = app.query_one("#ask-input")
        ask.focus()
        await pilot.press("w", "h", "o", "enter")
        output = str(app.query_one("#ask-output").content)
        assert "lead identity: user:lead" in output


@pytest.mark.asyncio
async def test_slash_focuses_audit_filter(app):
    async with app.run_test() as pilot:
        await pilot.press("6")
        await pilot.press("/")
        assert app.focused is app.query_one("#audit-identity-filter")


@pytest.mark.asyncio
async def test_setup_wizard_uses_selects_and_writes_full_config(tmp_path):
    if not HAS_TEXTUAL:
        pytest.skip("textual not installed")
    dest = tmp_path / "adiuvare.yaml"
    app = SetupWizardApp(dest)

    async with app.run_test() as pilot:
        assert isinstance(app.query_one("#wiz-framework"), Select)
        assert isinstance(app.query_one("#wiz-strict"), Select)
        app.query_one("#wiz-ai", Select).value = "assist"
        app.query_one("#wiz-save", Button).press()
        await pilot.pause()

    saved = Path(dest).read_text(encoding="utf-8")
    assert "weights:" in saved
    assert "thresholds:" in saved
    assert "framework: fastapi" in saved
    assert "mode: assist" in saved
