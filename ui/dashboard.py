"""
ui/dashboard.py
===============
Main TUI dashboard — shows server status, console, and resource usage.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static, Input
from textual.timer import Timer

from ui.widgets import StatusIndicator, ResourceBar, ServerLogView


class DashboardScreen(Screen):
    """Primary dashboard screen with server controls and monitoring."""

    BINDINGS = [
        ("s", "toggle_server", "Start/Stop"),
        ("j", "push_screen('java')", "Java"),
        ("p", "push_screen('plugins')", "Plugins"),
        ("e", "push_screen('editor')", "Editor"),
        ("b", "create_backup", "Backup"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, server_manager) -> None:
        super().__init__()
        self.server_manager = server_manager
        self._refresh_timer: Timer | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Container(id="dashboard"):
            # ── Status Panel (spans full width) ──
            with Vertical(id="status-panel", classes="panel"):
                yield Label("⛏️  Server Status", classes="panel-title")
                with Horizontal():
                    yield StatusIndicator(id="status-indicator")
                    yield Label("", id="server-info")
                with Horizontal():
                    yield Button("▶ Start", id="btn-start", classes="action-btn btn-start")
                    yield Button("■ Stop", id="btn-stop", classes="action-btn btn-stop")
                    yield Button("↻ Restart", id="btn-restart", classes="action-btn btn-primary")
                    yield Button("💾 Backup", id="btn-backup", classes="action-btn btn-primary")

            # ── Console Panel ──
            with Vertical(id="console-panel", classes="panel"):
                yield Label("📋 Console", classes="panel-title")
                yield ServerLogView(id="log-view")
                yield Input(placeholder="Type server command…", id="cmd-input")

            # ── Resources Panel ──
            with Vertical(id="resources-panel", classes="panel"):
                yield Label("📊 System Resources", classes="panel-title")
                yield ResourceBar(id="cpu-bar")
                yield ResourceBar(id="ram-bar")
                yield ResourceBar(id="disk-bar")
                yield Label("", id="uptime-label")

        yield Footer()

    def on_mount(self) -> None:
        """Initialize dashboard state and start refresh timer."""
        # Configure resource bars
        cpu_bar = self.query_one("#cpu-bar", ResourceBar)
        cpu_bar.label = "CPU"
        cpu_bar.unit = "%"

        ram_bar = self.query_one("#ram-bar", ResourceBar)
        ram_bar.label = "RAM"
        ram_bar.unit = " MB"

        disk_bar = self.query_one("#disk-bar", ResourceBar)
        disk_bar.label = "Disk"
        disk_bar.unit = " GB"

        # Start periodic refresh
        self._refresh_timer = self.set_interval(2.0, self._refresh_status)
        self._refresh_status()

    def _refresh_status(self) -> None:
        """Update all dashboard widgets with current server state."""
        status = self.server_manager.get_status()
        resources = self.server_manager.get_system_resources()

        # Status indicator
        indicator = self.query_one("#status-indicator", StatusIndicator)
        indicator.is_running = status.running

        # Server info
        info_parts = [f"Type: {status.server_type.title()}", f"Version: {status.version}"]
        if status.running:
            mins = int(status.uptime_seconds // 60)
            info_parts.append(f"Uptime: {mins}m")
            info_parts.append(f"RAM: {status.ram_used_mb:.0f} MB")
        self.query_one("#server-info", Label).update("  |  ".join(info_parts))

        # Resource bars
        self.query_one("#cpu-bar", ResourceBar).value = resources["cpu_percent"]
        ram_bar = self.query_one("#ram-bar", ResourceBar)
        ram_bar.value = resources["ram_used_mb"]
        ram_bar.max_value = resources["ram_total_mb"]
        disk_bar = self.query_one("#disk-bar", ResourceBar)
        disk_bar.value = resources["disk_used_gb"]
        disk_bar.max_value = resources["disk_total_gb"]

        # Log tail
        log_view = self.query_one("#log-view", ServerLogView)
        log_lines = self.server_manager.get_log_tail(30)
        if log_lines:
            log_view.load_lines(log_lines)

    # ── Button Handlers ─────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-start":
            ok, msg = self.server_manager.start()
            self.notify(msg, severity="information" if ok else "error")
        elif btn_id == "btn-stop":
            ok, msg = self.server_manager.stop()
            self.notify(msg, severity="information" if ok else "error")
        elif btn_id == "btn-restart":
            ok, msg = self.server_manager.restart()
            self.notify(msg, severity="information" if ok else "error")
        elif btn_id == "btn-backup":
            self.action_create_backup()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Send a command to the server console."""
        if event.input.id == "cmd-input" and event.value.strip():
            sent = self.server_manager.send_command(event.value.strip())
            if sent:
                self.notify(f"Sent: {event.value.strip()}")
            else:
                self.notify("Server not running", severity="error")
            event.input.value = ""

    # ── Actions ─────────────────────────────────

    def action_toggle_server(self) -> None:
        if self.server_manager.is_running():
            ok, msg = self.server_manager.stop()
        else:
            ok, msg = self.server_manager.start()
        self.notify(msg, severity="information" if ok else "error")

    def action_create_backup(self) -> None:
        ok, msg = self.server_manager.create_backup()
        self.notify(msg, severity="information" if ok else "error")
