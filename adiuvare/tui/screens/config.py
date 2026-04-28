import json
import sqlite3
from pathlib import Path
from typing import cast

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

from ..workspace import WorkspaceView


class ConfigScreen(WorkspaceView):
    shortcut_hints = "[1-6] tabs  [s] save  [r] reset  [t] observe"
    primary_id = "cfg-block"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._observe = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("config patching", id="cfg-title")
            with Horizontal(classes="filter-row"):
                yield Static("block threshold", id="cfg-block-label")
                yield Input(id="cfg-block")
                yield Static("ai mode", id="cfg-ai-label")
                yield Input(id="cfg-ai")
            with Horizontal(classes="filter-row"):
                yield Button("Toggle observe", id="cfg-toggle")
                yield Button("Save", id="cfg-save")
                yield Button("Reset", id="cfg-reset")
            with Horizontal(id="cfg-shell"):
                with Vertical(classes="monitor-main"):
                    yield Static("", id="cfg-summary")
                    yield Static("", id="cfg-runtime")
                with Vertical(classes="monitor-side"):
                    yield Static("", id="cfg-weights")
                    yield Static("", id="cfg-history")

    def on_mount(self) -> None:
        self.refresh_view()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cfg-toggle":
            self._observe = not self._observe
            self._render_summary("observe flag changed")
        elif event.button.id == "cfg-save":
            self.action_save_config()
        elif event.button.id == "cfg-reset":
            self.action_reset_config()

    def action_save_config(self) -> None:
        block = float(self.query_one("#cfg-block", Input).value)
        ai_mode = self.query_one("#cfg-ai", Input).value.strip() or "off"
        changes = {
            "thresholds": {"block": block},
            "runtime": {"observe_only": self._observe},
            "ai": {"mode": ai_mode, "enabled": ai_mode != "off"},
        }
        self._app().save_config(changes)
        self.refresh_view()
        self._app().set_footer_status("config saved")

    def action_reset_config(self) -> None:
        self.refresh_view()
        self._app().set_footer_status("config reset")

    def refresh_view(self) -> None:
        cfg = self._app().config
        self._observe = cfg.runtime.observe_only
        self.query_one("#cfg-block", Input).value = str(cfg.thresholds.block)
        self.query_one("#cfg-ai", Input).value = cfg.ai.mode
        self._render_summary("editing local config")
        self._render_runtime()
        self._render_weights()
        self._render_history()

    def footer_status(self) -> str:
        path = self._app().config_path or str(Path("adiuvare.yaml"))
        strict = self._app().config.meta.strictness
        return f"config path: {path} | strictness: {strict}"

    def _render_summary(self, note: str) -> None:
        cfg = self._app().config
        where = "runtime + file" if self._app().connected else "file only"
        self.query_one("#cfg-summary", Static).update(
            "\n".join(
                [
                    "session",
                    f"framework: {cfg.meta.framework}",
                    f"strictness: {cfg.meta.strictness}",
                    f"instances: {cfg.meta.instances}",
                    f"observe only: {self._observe}",
                    f"ai mode: {cfg.ai.mode}",
                    f"flag/throttle/block: {cfg.thresholds.flag:.2f} / {cfg.thresholds.throttle:.2f} / {cfg.thresholds.block:.2f}",
                    f"save path: {where}",
                    note,
                ]
            )
        )

    def _render_runtime(self) -> None:
        snap = self._app().runtime_snapshot()
        self.query_one("#cfg-runtime", Static).update(
            "\n".join(
                [
                    "runtime",
                    f"connected: {bool(snap.get('connected', False))}",
                    f"backend: {snap.get('backend', 'sqlite')}",
                    f"recent events: {int(snap.get('recent_events', 0))}",
                    f"whitelist: {int(snap.get('whitelist_size', 0))}",
                    f"audit db: {snap.get('audit_db', '-')}",
                    f"state db: {snap.get('state_db', '-')}",
                ]
            )
        )

    def _render_weights(self) -> None:
        cfg = self._app().config
        self.query_one("#cfg-weights", Static).update(
            "\n".join(
                [
                    "weights",
                    f"payload: {cfg.weights.payload:.2f}",
                    f"behavior: {cfg.weights.behavior:.2f}",
                    f"identity: {cfg.weights.identity:.2f}",
                    "",
                    "thresholds",
                    f"flag: {cfg.thresholds.flag:.2f}",
                    f"throttle: {cfg.thresholds.throttle:.2f}",
                    f"block: {cfg.thresholds.block:.2f}",
                ]
            )
        )

    def _render_history(self) -> None:
        cfg = self._app().config
        path = Path(cfg.runtime.audit_db_path)
        if not path.exists():
            self.query_one("#cfg-history", Static).update("history\nno saved changes yet")
            return

        with sqlite3.connect(path) as conn:
            rows = conn.execute(
                """
                select kind, patch_json, created_at
                from config_history
                order by id desc
                limit 4
                """
            ).fetchall()

        if not rows:
            self.query_one("#cfg-history", Static).update("history\nno saved changes yet")
            return

        lines = ["recent changes"]
        for kind, patch_json, created_at in rows:
            try:
                patch = json.loads(patch_json)
            except json.JSONDecodeError:
                patch = patch_json
            lines.append(f"{created_at}  {kind}")
            lines.append(str(patch)[:100])
        self.query_one("#cfg-history", Static).update("\n".join(lines))

    def _app(self):
        return cast("AdiuvareApp", self.app)
