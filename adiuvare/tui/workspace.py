from textual.containers import Container


PALETTE = {
    "bg": "#10131a",
    "panel": "#151a24",
    "border": "#2a3242",
    "text": "#e7ecf2",
    "dim": "#8a95a8",
    "green": "#3fb950",
    "orange": "#d29922",
    "red": "#f85149",
    "blue": "#58a6ff",
}


class WorkspaceView(Container):
    DEFAULT_CSS = """
    WorkspaceView {
        width: 1fr;
        height: 1fr;
    }
    """

    shortcut_hints = "[1-6] tabs  [q] quit"
    primary_id: str | None = None

    def refresh_view(self) -> None:
        return

    def footer_status(self) -> str:
        return "runtime shell"

    def shortcut_summary(self) -> str:
        return self.shortcut_hints

    def focus_primary(self) -> None:
        if not self.primary_id:
            return
        try:
            self.app.set_focus(self.query_one(f"#{self.primary_id}"))
        except Exception:
            return


def decision_color(verdict: str) -> str:
    return {
        "allow": PALETTE["green"],
        "flag": PALETTE["orange"],
        "throttle": PALETTE["orange"],
        "block": PALETTE["red"],
    }.get(verdict, PALETTE["dim"])


def decision_icon(verdict: str) -> str:
    return {
        "allow": "o",
        "flag": "^",
        "throttle": "!",
        "block": "x",
    }.get(verdict, "?")

