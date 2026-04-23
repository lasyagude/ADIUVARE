from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, ContentSwitcher, Static

from ..config.loader import load_config
from ..state.audit_log import AuditLog
from .screens.monitor import MonitorScreen
from .workspace import WorkspaceView


class PlaceholderView(WorkspaceView):
    def __init__(self, name: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._name = name

    def compose(self) -> ComposeResult:
        yield Static(f"{self._name} is still pretty thin right now.", id="placeholder-copy")

    def footer_status(self) -> str:
        return f"{self._name.lower()} is a placeholder for now"


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
        self._view = "monitor"

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
                yield PlaceholderView("Events", id="events-view")
                yield PlaceholderView("Config", id="config-view")
                yield PlaceholderView("Signals", id="signals-view")
                yield PlaceholderView("AI", id="analyst-view")
                yield PlaceholderView("Audit", id="audit-view")
            with Horizontal(id="app-footer"):
                yield Static("", id="footer-shortcuts")
                yield Static("", id="footer-status")

    def on_mount(self) -> None:
        self._sync_view()

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

    def runtime_snapshot(self) -> dict:
        return {
            "ai_mode": self.config.ai.mode,
            "observe_only": self.config.runtime.observe_only,
            "recent_events": 0,
            "whitelist_size": 0,
            "state_db": self.config.runtime.state_db_path,
        }

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
        self.query_one("#footer-shortcuts", Static).update(page.shortcut_summary())
        self.query_one("#footer-status", Static).update(page.footer_status())

    def _active_page(self) -> WorkspaceView:
        return self.query_one(f"#{self._view}-view", WorkspaceView)

