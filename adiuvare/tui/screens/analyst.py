from collections import Counter
from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ..workspace import WorkspaceView


class AnalystScreen(WorkspaceView):
    shortcut_hints = "[1-6] tabs  [a] ask  [Enter] send"
    primary_id = "ask-input"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("ai analyst")
            yield Static("", id="analyst-status")
            yield Static("", id="analyst-report")
            with Horizontal():
                yield Input(id="ask-input", placeholder="ask about the recent audit rows")
                yield Button("Send", id="ask-send")
            yield Static("ask a question to summarize the last few rows", id="ask-output")

    def on_mount(self) -> None:
        self.refresh_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ask-send":
            self.action_submit_question()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "ask-input":
            self.action_submit_question()

    def refresh_view(self) -> None:
        rows = self._app().recent_rows(40)
        counts = Counter(str(row.get("verdict", "allow")) for row in rows)
        ai_rows = 0
        for row in rows:
            detail = row.get("detail") or {}
            if isinstance(detail, dict) and detail.get("ai"):
                ai_rows += 1
        snap = self._app().runtime_snapshot()
        self.query_one("#analyst-status", Static).update(
            "\n".join(
                [
                    f"ai mode: {snap.get('ai_mode', 'off')}",
                    f"ai enabled: {bool(snap.get('ai_enabled', False))}",
                    f"model: {snap.get('ai_model', 'n/a')}",
                    f"live link: {bool(snap.get('connected', False))}",
                ]
            )
        )
        self.query_one("#analyst-report", Static).update(
            "\n".join(
                [
                    f"rows: {len(rows)}",
                    f"allow: {counts.get('allow', 0)}",
                    f"flag: {counts.get('flag', 0)}",
                    f"throttle: {counts.get('throttle', 0)}",
                    f"block: {counts.get('block', 0)}",
                    f"rows with ai detail: {ai_rows}",
                ]
            )
        )

    def action_submit_question(self) -> None:
        prompt = self.query_one("#ask-input", Input).value.strip()
        rows = self._app().recent_rows(20)
        top = Counter(str(row.get("identity", "?")) for row in rows).most_common(1)
        lead = top[0][0] if top else "none"
        snap = self._app().runtime_snapshot()
        self.query_one("#ask-output", Static).update(
            f"Q: {prompt or '...'}\n"
            f"lead identity: {lead}\n"
            f"rows scanned: {len(rows)}\n"
            f"ai mode: {snap.get('ai_mode', 'off')}\n"
            f"model: {snap.get('ai_model', 'n/a')}"
        )

    def _app(self):
        return cast("AdiuvareApp", self.app)
