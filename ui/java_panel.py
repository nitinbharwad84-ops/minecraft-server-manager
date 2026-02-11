"""
ui/java_panel.py
================
Textual screen for managing Java installations.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, DataTable, Footer, Header, Label, Static,
)

from java_manager import JavaManager


class JavaScreen(Screen):
    """Java version management screen."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
        ("d", "detect_java", "Detect"),
    ]

    def __init__(self, java_manager: JavaManager) -> None:
        super().__init__()
        self.java_manager = java_manager

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Vertical(classes="panel"):
            yield Label("☕  Java Version Manager", classes="panel-title")
            yield Label("", id="active-java-label")

            # Installed versions table
            yield DataTable(id="java-table", classes="data-table")

            # Action buttons
            with Horizontal(id="java-actions"):
                yield Button("🔍 Detect System Java", id="btn-detect", classes="action-btn btn-primary")
                yield Button("⬇ Install Java 17", id="btn-install-17", classes="action-btn btn-primary")
                yield Button("⬇ Install Java 21", id="btn-install-21", classes="action-btn btn-primary")
                yield Button("✓ Set Active", id="btn-set-active", classes="action-btn btn-start")
                yield Button("🗑 Remove", id="btn-remove", classes="action-btn btn-stop")

        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#java-table", DataTable)
        table.add_columns("Version", "Path", "Vendor", "Status")
        self._refresh_table()

    def _refresh_table(self) -> None:
        table = self.query_one("#java-table", DataTable)
        table.clear()

        active = self.java_manager.get_active()
        active_label = self.query_one("#active-java-label", Label)

        if active:
            active_label.update(f"Active: Java {active.version} ({active.vendor}) — {active.path}")
        else:
            active_label.update("Active: None (will use system default)")

        for inst in self.java_manager.list_installed():
            is_active = "✓ Active" if (active and active.version == inst.version) else ""
            valid = "✓ Valid" if inst.is_valid() else "✗ Invalid"
            status = f"{is_active} {valid}".strip()
            table.add_row(str(inst.version), inst.path, inst.vendor, status)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "btn-detect":
            self.action_detect_java()
        elif btn == "btn-install-17":
            self.notify("Installing Java 17… (this may take a few minutes)")
            self.run_worker(self._install_java(17))
        elif btn == "btn-install-21":
            self.notify("Installing Java 21… (this may take a few minutes)")
            self.run_worker(self._install_java(21))
        elif btn == "btn-set-active":
            self._set_active_from_selection()
        elif btn == "btn-remove":
            self._remove_from_selection()

    def action_detect_java(self) -> None:
        found = self.java_manager.detect_system_java()
        self._refresh_table()
        self.notify(f"Found {len(found)} Java installation(s)")

    async def _install_java(self, version: int) -> None:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            result = await self.java_manager.download_java(version, session)
            if result:
                self.java_manager.set_active(version)
                self.notify(f"Java {version} installed successfully!")
            else:
                self.notify(f"Failed to install Java {version}", severity="error")
        self._refresh_table()

    def _set_active_from_selection(self) -> None:
        table = self.query_one("#java-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            version = int(row[0])
            if self.java_manager.set_active(version):
                self.notify(f"Java {version} set as active")
                self._refresh_table()
            else:
                self.notify("Failed to set active", severity="error")

    def _remove_from_selection(self) -> None:
        table = self.query_one("#java-table", DataTable)
        if table.cursor_row is not None:
            row = table.get_row_at(table.cursor_row)
            version = int(row[0])
            if self.java_manager.remove(version):
                self.notify(f"Java {version} removed")
                self._refresh_table()
            else:
                self.notify("Cannot remove system installs", severity="error")
