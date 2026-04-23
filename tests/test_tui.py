import importlib.util

import pytest

from adiuvare.core.models import AdiuvareEvent


HAS_TEXTUAL = importlib.util.find_spec("textual") is not None

if HAS_TEXTUAL:
    from textual.widgets import Button, ContentSwitcher
    from adiuvare.tui.app import AdiuvareApp


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
