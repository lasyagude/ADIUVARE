from rich.text import Text
from textual.widgets import DataTable

from ..workspace import decision_color, decision_icon


class RiskStream(DataTable):
    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.add_columns("", "risk", "identity", "endpoint")

    def show_events(self, events: list[dict]) -> None:
        self.clear(columns=False)
        for event in events:
            verdict = str(event.get("verdict", "allow"))
            breakdown = event.get("breakdown") or {}
            risk = max(breakdown.values(), default=0.0) if isinstance(breakdown, dict) else 0.0
            self.add_row(
                Text(decision_icon(verdict), style=decision_color(verdict)),
                Text(f"{risk:0.2f}", style=decision_color(verdict)),
                Text(str(event.get("identity", "?"))[:18]),
                Text(str(event.get("endpoint", "?"))[:26]),
            )

