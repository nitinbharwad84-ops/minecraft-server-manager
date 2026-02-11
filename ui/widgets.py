"""
ui/widgets.py
=============
Reusable Textual widgets for the Minecraft Server Manager TUI.

Provides:
  - StatusIndicator    – colored running/stopped badge
  - ResourceBar        – CPU/RAM/Disk usage bar
  - ServerLogView      – scrolling, color-coded log output
  - ConfirmDialog      – yes/no confirmation modal
  - ProgressIndicator  – download / task progress bar
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import (
    Button,
    Label,
    ProgressBar,
    RichLog,
    Static,
)
from rich.text import Text


# ──────────────────────────────────────────────
#  Status Indicator
# ──────────────────────────────────────────────

class StatusIndicator(Static):
    """Displays a colored ● RUNNING / ● STOPPED badge."""

    is_running: reactive[bool] = reactive(False)

    def render(self) -> Text:
        if self.is_running:
            return Text("● RUNNING", style="bold green")
        return Text("● STOPPED", style="bold red")


# ──────────────────────────────────────────────
#  Resource Bar
# ──────────────────────────────────────────────

class ResourceBar(Widget):
    """Horizontal bar showing resource usage (CPU, RAM, Disk)."""

    DEFAULT_CSS = """
    ResourceBar {
        height: 3;
        padding: 0 1;
    }
    ResourceBar .rb-label { width: 12; }
    ResourceBar .rb-bar   { width: 1fr; }
    ResourceBar .rb-value { width: 10; text-align: right; }
    """

    label: reactive[str] = reactive("Resource")
    value: reactive[float] = reactive(0.0)
    max_value: reactive[float] = reactive(100.0)
    unit: reactive[str] = reactive("%")

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label(self.label, classes="rb-label")
            yield ProgressBar(total=100, show_eta=False, show_percentage=True, classes="rb-bar")
            yield Label("", classes="rb-value", id="rb-val")

    def watch_value(self, new_value: float) -> None:
        try:
            bar = self.query_one(ProgressBar)
            pct = (new_value / self.max_value * 100) if self.max_value > 0 else 0
            bar.progress = min(pct, 100)
            lbl = self.query_one("#rb-val", Label)
            lbl.update(f"{new_value:.0f}{self.unit}")
        except Exception:
            pass


# ──────────────────────────────────────────────
#  Server Log View
# ──────────────────────────────────────────────

class ServerLogView(RichLog):
    """Color-coded server log viewer with auto-scroll."""

    DEFAULT_CSS = """
    ServerLogView {
        height: 100%;
        border: solid $secondary;
        padding: 0 1;
    }
    """

    def add_log_line(self, line: str) -> None:
        """Add a single log line with color coding."""
        if "[WARN" in line or "WARN" in line.upper()[:30]:
            self.write(Text(line, style="yellow"))
        elif "[ERROR" in line or "ERROR" in line.upper()[:30]:
            self.write(Text(line, style="bold red"))
        elif "[INFO" in line:
            self.write(Text(line, style=""))
        else:
            self.write(Text(line, style="dim"))

    def load_lines(self, lines: list[str]) -> None:
        """Load multiple log lines at once."""
        self.clear()
        for line in lines:
            self.add_log_line(line)


# ──────────────────────────────────────────────
#  Confirm Dialog
# ──────────────────────────────────────────────

class ConfirmDialog(Widget):
    """A simple yes/no confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmDialog {
        width: 50;
        height: auto;
        border: double $primary;
        padding: 2;
        background: $surface;
        layer: dialog;
    }
    ConfirmDialog #cd-msg { text-align: center; margin-bottom: 1; }
    ConfirmDialog #cd-buttons { align-horizontal: center; }
    """

    def __init__(self, message: str, dialog_id: str = "confirm") -> None:
        super().__init__(id=dialog_id)
        self._message = message

    def compose(self) -> ComposeResult:
        yield Label(self._message, id="cd-msg")
        with Horizontal(id="cd-buttons"):
            yield Button("Yes", variant="success", id="cd-yes")
            yield Button("No", variant="error", id="cd-no")


# ──────────────────────────────────────────────
#  Progress Indicator
# ──────────────────────────────────────────────

class ProgressIndicator(Widget):
    """Shows download / task progress with label."""

    DEFAULT_CSS = """
    ProgressIndicator {
        height: 3;
        padding: 0 1;
    }
    """

    task_label: reactive[str] = reactive("Downloading…")
    progress: reactive[float] = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Label(self.task_label, id="pi-label")
        yield ProgressBar(total=100, show_eta=True, show_percentage=True, id="pi-bar")

    def set_progress(self, current: float, total: float) -> None:
        """Update progress (0-100%)."""
        pct = (current / total * 100) if total > 0 else 0
        self.progress = pct
        try:
            self.query_one("#pi-bar", ProgressBar).progress = pct
        except Exception:
            pass
