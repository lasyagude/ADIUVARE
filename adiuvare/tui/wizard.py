from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Select, Static

from ..config.editor import merge_sections, starter_config


class SetupWizardApp(App[None]):
    CSS = """
    Screen {
        background: #10131a;
        color: #e7ecf2;
    }
    #wiz-shell {
        align: center middle;
        height: 100%;
    }
    #wiz-card {
        width: 72;
        border: solid #2a3242;
        background: #151a24;
        padding: 1 2;
    }
    #wiz-title {
        color: #58a6ff;
        text-style: bold;
        margin-bottom: 1;
    }
    .wiz-copy {
        color: #8a95a8;
        margin-bottom: 1;
    }
    .wiz-row {
        height: auto;
        margin-bottom: 1;
    }
    .wiz-label {
        width: 14;
        color: #8a95a8;
        content-align: left middle;
    }
    .wiz-pick {
        width: 1fr;
    }
    #wiz-save {
        margin-top: 1;
        width: 1fr;
    }
    #wiz-status {
        margin-top: 1;
        color: #8a95a8;
    }
    """

    def __init__(self, dest: str | Path) -> None:
        super().__init__()
        self._dest = Path(dest)

    def compose(self) -> ComposeResult:
        with Vertical(id="wiz-shell"):
            with Vertical(id="wiz-card"):
                yield Static("Adiuvare setup", id="wiz-title")
                yield Static("Pick the runtime shape and write a starter config.", classes="wiz-copy")
                with Horizontal(classes="wiz-row"):
                    yield Static("Framework", classes="wiz-label")
                    yield Select(
                        [("FastAPI", "fastapi"), ("Flask", "flask"), ("Django", "django")],
                        allow_blank=False,
                        value="fastapi",
                        id="wiz-framework",
                        classes="wiz-pick",
                    )
                with Horizontal(classes="wiz-row"):
                    yield Static("Instances", classes="wiz-label")
                    yield Select(
                        [("Single", "single"), ("Multi", "multi")],
                        allow_blank=False,
                        value="single",
                        id="wiz-instances",
                        classes="wiz-pick",
                    )
                with Horizontal(classes="wiz-row"):
                    yield Static("Strictness", classes="wiz-label")
                    yield Select(
                        [("Public", "public"), ("Internal", "internal"), ("Critical", "critical")],
                        allow_blank=False,
                        value="internal",
                        id="wiz-strict",
                        classes="wiz-pick",
                    )
                with Horizontal(classes="wiz-row"):
                    yield Static("Mode", classes="wiz-label")
                    yield Select(
                        [("Observe", "observe"), ("Enforce", "enforce")],
                        allow_blank=False,
                        value="observe",
                        id="wiz-mode",
                        classes="wiz-pick",
                    )
                with Horizontal(classes="wiz-row"):
                    yield Static("AI mode", classes="wiz-label")
                    yield Select(
                        [("Off", "off"), ("Assist", "assist"), ("Critical", "critical")],
                        allow_blank=False,
                        value="off",
                        id="wiz-ai",
                        classes="wiz-pick",
                    )
                with Horizontal(classes="wiz-row"):
                    yield Static("Save path", classes="wiz-label")
                    yield Input(value=str(self._dest), id="wiz-path", classes="wiz-pick")
                yield Button("Write starter config", id="wiz-save")
                yield Static("", id="wiz-status")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "wiz-save":
            return

        framework = str(self.query_one("#wiz-framework", Select).value or "fastapi")
        instances = str(self.query_one("#wiz-instances", Select).value or "single")
        strict = str(self.query_one("#wiz-strict", Select).value or "internal")
        mode = str(self.query_one("#wiz-mode", Select).value or "observe")
        ai_mode = str(self.query_one("#wiz-ai", Select).value or "off")
        self._dest = Path(self.query_one("#wiz-path", Input).value.strip() or str(self._dest))
        payload = starter_config(
            framework=framework,
            instances=instances,
            strictness=strict,
            mode=mode,
            ai_mode=ai_mode,
        )
        merge_sections(self._dest, payload)
        self.query_one("#wiz-status", Static).update(f"wrote {self._dest}")
        self.exit()


def run_wizard(dest: str | Path) -> None:
    SetupWizardApp(dest).run()
