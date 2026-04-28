from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Static

from ..widgets.signal_chart import SignalChart
from ..workspace import WorkspaceView


class SignalsScreen(WorkspaceView):
    shortcut_hints = "[1-6] tabs  [up/down] rows  [r] refresh"
    primary_id = "signals-table"

    def compose(self) -> ComposeResult:
        with Horizontal(id="signals-shell"):
            with Vertical(classes="monitor-main"):
                yield DataTable(id="signals-table")
            with Vertical(classes="monitor-side"):
                yield SignalChart(id="signals-chart")
                yield Static("", id="signals-copy")
                yield Static("", id="signals-runtime")

    def on_mount(self) -> None:
        table = self.query_one("#signals-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("signal", "weight", "hits")
        self.refresh_view()

    def refresh_view(self) -> None:
        cfg = self._app().config
        rows = self._app().recent_rows(80)
        hits = {}
        totals = {
            "payload": cfg.weights.payload,
            "behavior": cfg.weights.behavior,
            "identity": cfg.weights.identity,
        }
        for row in rows:
            for name, score in (row.get("breakdown") or {}).items():
                if score > 0.05:
                    hits[name] = hits.get(name, 0) + 1
                    totals.setdefault(name, 0.0)

        table = self.query_one("#signals-table", DataTable)
        table.clear(columns=False)
        for name, weight in totals.items():
            table.add_row(name, f"{weight:0.2f}", str(hits.get(name, 0)))
        self.query_one("#signals-chart", SignalChart).show_breakdown(
            {name: float(count) for name, count in hits.items()}
        )
        self.query_one("#signals-copy", Static).update(
            f"registered signals: {len(totals)}\nrecent rows scanned: {len(rows)}"
        )
        self.query_one("#signals-runtime", Static).update(self._runtime_copy())

    def _app(self):
        return cast("AdiuvareApp", self.app)

    def _runtime_copy(self) -> str:
        cfg = self._app().config
        snap = self._app().runtime_snapshot()
        lines = [
            "runtime mix",
            f"strictness: {cfg.meta.strictness}",
            f"ai mode: {cfg.ai.mode}",
            f"backend: {snap.get('backend', 'sqlite')}",
            "",
            "thresholds",
            f"flag: {cfg.thresholds.flag:.2f}",
            f"throttle: {cfg.thresholds.throttle:.2f}",
            f"block: {cfg.thresholds.block:.2f}",
        ]
        return "\n".join(lines)
