from collections import Counter
from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from ...state.audit_log import AuditLog
from ..widgets.risk_stream import RiskStream
from ..workspace import PALETTE, WorkspaceView


class MonitorScreen(WorkspaceView):
    shortcut_hints = "[1-6] tabs  [up/down] rows  [r] refresh  [q] quit"
    primary_id = "monitor-stream"

    def compose(self) -> ComposeResult:
        with Horizontal(id="monitor-shell"):
            with Vertical(classes="monitor-main"):
                yield Static("MONITOR", id="monitor-title")
                yield RiskStream(id="monitor-stream")
            with Vertical(classes="monitor-side"):
                yield Static("", id="runtime-snapshot")
                yield Static("", id="runtime-counts")

    def on_mount(self) -> None:
        self.refresh_view()

    def refresh_view(self) -> None:
        audit = self._audit()
        rows = audit.recent(limit=14)
        counts = Counter(str(row.get("verdict", "allow")) for row in rows)
        self.query_one("#monitor-stream", RiskStream).show_events(rows)
        self.query_one("#runtime-snapshot", Static).update(self._snapshot_text())
        self.query_one("#runtime-counts", Static).update(self._counts_text(counts, len(rows)))

    def footer_status(self) -> str:
        return "monitor is live, the rest still needs filling in"

    def _snapshot_text(self) -> str:
        snap = self._app().runtime_snapshot()
        state_db = str(snap.get("state_db", "-"))
        ai_mode = str(snap.get("ai_mode", "off"))
        observe = bool(snap.get("observe_only", False))
        recent = int(snap.get("recent_events", 0))
        wl = int(snap.get("whitelist_size", 0))
        lines = [
            "runtime snapshot",
            f"ai mode: {ai_mode}",
            f"observe only: {observe}",
            f"recent stream: {recent}",
            f"whitelist: {wl}",
            f"state db: {state_db}",
        ]
        return "\n".join(lines)

    def _counts_text(self, counts: Counter[str], total: int) -> str:
        lines = [
            "recent decisions",
            f"allow: {counts.get('allow', 0)}",
            f"flag: {counts.get('flag', 0)}",
            f"throttle: {counts.get('throttle', 0)}",
            f"block: {counts.get('block', 0)}",
            f"rows: {total}",
        ]
        return "\n".join(lines)

    def _app(self):
        return cast("AdiuvareApp", self.app)

    def _audit(self) -> AuditLog:
        return self._app().audit

