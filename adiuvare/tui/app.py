import asyncio
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Static

from ..config.loader import load_config
from ..state.audit_log import AuditLog
from ..state.event_stream import EventStreamClient
from ..config.editor import merge_sections
from ..config.watcher import ConfigWatcher
from .screens.analyst import AnalystScreen
from .screens.audit import AuditScreen
from .screens.config import ConfigScreen
from .screens.events import EventsScreen
from .screens.monitor import MonitorScreen
from .screens.signals import SignalsScreen
from .workspace import WorkspaceView


class AdiuvareApp(App[None]):
    CSS_PATH = Path(__file__).with_name("replit.tcss")
    BINDINGS = [
        Binding("1", "switch_view('monitor')", show=False),
        Binding("2", "switch_view('events')", show=False),
        Binding("3", "switch_view('config')", show=False),
        Binding("4", "switch_view('signals')", show=False),
        Binding("5", "switch_view('analyst')", show=False),
        Binding("6", "switch_view('audit')", show=False),
        Binding("q", "quit", show=False),
        Binding("r", "refresh_view", show=False),
    ]

    def __init__(self, socket_path: str | None = None, config_path: str | None = None) -> None:
        super().__init__()
        self.socket_path = socket_path
        self.connected = socket_path is not None
        self.config_path = config_path
        self.config = load_config(config_path)
        self.audit = AuditLog(self.config.runtime.audit_db_path)
        self.client = EventStreamClient(socket_path)
        self._view = "monitor"
        self._footer_note = "runtime shell"
        self._watcher = ConfigWatcher(config_path) if config_path else None
        self._runtime_cache: dict | None = None
        self._stream_rows: list[dict] = []
        self._tasks: list[asyncio.Task] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="app-shell"):
            with Horizontal(id="top-bar"):
                yield Static("Adiuvare", id="brand")
                with Horizontal(id="tab-strip"):
                    yield Button("1 Monitor", id="tab-monitor", classes="tab-btn")
                    yield Button("2 Events", id="tab-events", classes="tab-btn")
                    yield Button("3 Config", id="tab-config", classes="tab-btn")
                    yield Button("4 Signals", id="tab-signals", classes="tab-btn")
                    yield Button("5 AI", id="tab-analyst", classes="tab-btn")
                    yield Button("6 Audit", id="tab-audit", classes="tab-btn")
            with ContentSwitcher(initial="monitor-view", id="body-switcher"):
                yield MonitorScreen(id="monitor-view")
                yield EventsScreen(id="events-view")
                yield ConfigScreen(id="config-view")
                yield SignalsScreen(id="signals-view")
                yield AnalystScreen(id="analyst-view")
                yield AuditScreen(id="audit-view")
            with Horizontal(id="app-footer"):
                yield Static("", id="footer-shortcuts")
                yield Static("", id="footer-status")

    def on_mount(self) -> None:
        self._sync_view()
        if self.connected:
            self._tasks.append(asyncio.create_task(self._stream_loop()))
            self._tasks.append(asyncio.create_task(self._refresh_runtime()))
        self.set_interval(1.0, self._tick)

    async def on_unmount(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("tab-"):
            self.action_switch_view(button_id.removeprefix("tab-"))

    def action_switch_view(self, view: str) -> None:
        self._view = view
        self._sync_view()

    def action_refresh_view(self) -> None:
        page = self._active_page()
        page.refresh_view()
        self._sync_footer(page)

    def set_footer_status(self, text: str) -> None:
        self._footer_note = text
        self._sync_footer(self._active_page())

    def runtime_snapshot(self) -> dict:
        snap = {
            "framework": self.config.meta.framework,
            "instances": self.config.meta.instances,
            "strictness": self.config.meta.strictness,
            "ai_mode": self.config.ai.mode,
            "ai_enabled": self.config.ai.enabled,
            "ai_model": self.config.ai.model,
            "observe_only": self.config.runtime.observe_only,
            "recent_events": len(self._stream_rows) if self._stream_rows else len(self.audit.recent(limit=20)),
            "whitelist_size": 0,
            "audit_db": self.config.runtime.audit_db_path,
            "state_db": self.config.runtime.state_db_path,
            "backend": self.config.runtime.backend,
            "connected": self.connected,
            "stream_path": self.socket_path,
            "flag_threshold": self.config.thresholds.flag,
            "throttle_threshold": self.config.thresholds.throttle,
            "block_threshold": self.config.thresholds.block,
            "payload_weight": self.config.weights.payload,
            "behavior_weight": self.config.weights.behavior,
            "identity_weight": self.config.weights.identity,
        }
        if self._runtime_cache:
            snap.update(self._runtime_cache)
        return snap

    def recent_rows(self, limit: int = 40) -> list[dict]:
        if self._stream_rows:
            return self._stream_rows[:limit]
        return self.audit.recent(limit=limit)

    def recent_by_identity(self, identity: str, limit: int = 40) -> list[dict]:
        return self.audit.by_identity(identity, limit=limit)

    def save_config(self, changes: dict) -> None:
        path = Path(self.config_path) if self.config_path else Path("adiuvare.yaml")
        merge_sections(path, changes)
        self.config = load_config(path)
        self._watcher = ConfigWatcher(path)
        self.audit.write_patch("patch_config", changes)
        runtime_patch = self._runtime_patch(changes)
        if self.connected and runtime_patch:
            self.run_worker(self._send_command("patch_config", runtime_patch), exclusive=False)

    def mark_note(self, identity: str, note: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("unblock_note", {"identity": identity, "note": note}), exclusive=False)
            return
        self.audit.write_patch("unblock_note", {"identity": identity, "note": note})

    def whitelist_identity(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("unblock_whitelist", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("unblock_whitelist", {"identity": identity})

    def confirm_identity(self, identity: str) -> None:
        if self.connected:
            self.run_worker(self._send_command("confirm_block", {"identity": identity}), exclusive=False)
            return
        self.audit.write_patch("confirm_block", {"identity": identity})

    def _sync_view(self) -> None:
        self.query_one("#body-switcher", ContentSwitcher).current = f"{self._view}-view"
        for name in ("monitor", "events", "config", "signals", "analyst", "audit"):
            button = self.query_one(f"#tab-{name}", Button)
            button.remove_class("-active")
            if name == self._view:
                button.add_class("-active")
        page = self._active_page()
        page.focus_primary()
        self._sync_footer(page)

    def _sync_footer(self, page: WorkspaceView) -> None:
        self.query_one("#footer-shortcuts", Static).update(Text(page.shortcut_summary()))
        status = page.footer_status()
        if self._footer_note and self._footer_note != "runtime shell":
            status = f"{status} | {self._footer_note}"
        self.query_one("#footer-status", Static).update(Text(status))

    def _active_page(self) -> WorkspaceView:
        return self.query_one(f"#{self._view}-view", WorkspaceView)

    def _tick(self) -> None:
        if self._watcher and self._watcher.check():
            self.config = load_config(self._watcher.path)
            self._active_page().refresh_view()
            self.set_footer_status("config changed on disk")

    async def _send_command(self, name: str, args: dict) -> None:
        try:
            res = await self.client.command(name, args)
        except Exception:
            self.set_footer_status("runtime command failed")
            return

        if name == "get_runtime_snapshot":
            self._runtime_cache = res
        else:
            self.set_footer_status("runtime command sent")
            await self._refresh_runtime()
        self._active_page().refresh_view()

    async def _refresh_runtime(self) -> None:
        if not self.connected:
            return
        try:
            self._runtime_cache = await self.client.command("get_runtime_snapshot", {})
        except Exception:
            return
        self._active_page().refresh_view()

    async def _stream_loop(self) -> None:
        if not self.connected:
            return
        try:
            async for row in self.client.subscribe():
                if not isinstance(row, dict):
                    continue
                self._stream_rows.insert(0, row)
                del self._stream_rows[80:]
                self._active_page().refresh_view()
        except Exception:
            self.set_footer_status("stream link dropped")

    def _runtime_patch(self, changes: dict) -> dict:
        patch = {}
        thresholds = changes.get("thresholds") or {}
        runtime = changes.get("runtime") or {}
        ai = changes.get("ai") or {}
        if "block" in thresholds:
            patch["block_threshold"] = thresholds["block"]
        if "observe_only" in runtime:
            patch["observe_only"] = runtime["observe_only"]
        if "mode" in ai:
            patch["ai_mode"] = ai["mode"]
        return patch
