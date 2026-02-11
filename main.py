#!/usr/bin/env python3
"""
main.py – Minecraft Server Manager TUI
=======================================
Entry point: tabbed Textual application with status bar header,
six navigation tabs, keyboard shortcuts, and headless CLI mode.
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.timer import Timer
from textual.widgets import (
    Button, Footer, Header, Label, Static,
    TabbedContent, TabPane,
)

# ──────────────────────────────────────────────
#  Logging
# ──────────────────────────────────────────────

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "manager.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("minecraft_server_manager")


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="⛏️  Minecraft Server Manager – Terminal UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--config", default="config.json", help="Path to config.json")
    p.add_argument("--type", default=None, help="Server type override")
    p.add_argument("--version", default=None, help="MC version override")
    p.add_argument("--ram", type=int, default=None, help="RAM in MB")
    p.add_argument("--headless", action="store_true", help="No TUI")
    p.add_argument(
        "--environment", choices=["local", "colab", "idx"], default=None,
    )
    return p.parse_args()


# ──────────────────────────────────────────────
#  Status Bar Widget
# ──────────────────────────────────────────────

class StatusBar(Static):
    """Top status bar showing server state at a glance."""

    server_running: reactive[bool] = reactive(False)
    java_ver: reactive[str] = reactive("?")
    mc_ver: reactive[str] = reactive("?")
    players: reactive[str] = reactive("0/20")

    def render(self) -> str:
        if self.server_running:
            srv = "[bold green]▶ Running[/]"
        else:
            srv = "[bold red]⏹ Stopped[/]"
        return (
            f"  Server: {srv}  │  "
            f"Java: {self.java_ver}  │  "
            f"MC: [cyan]{self.mc_ver}[/]  │  "
            f"Players: [yellow]{self.players}[/]"
        )


# ──────────────────────────────────────────────
#  Confirm Screen (modal)
# ──────────────────────────────────────────────

from textual.screen import ModalScreen


class ConfirmScreen(ModalScreen[bool]):
    """Yes / No confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    #confirm-box {
        width: 56; height: auto; max-height: 80%;
        border: double #58a6ff; padding: 2; background: #161b22;
    }
    #confirm-msg { text-align: center; margin-bottom: 1; }
    #confirm-btns { align-horizontal: center; }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._msg = message

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self._msg, id="confirm-msg")
            with Horizontal(id="confirm-btns"):
                yield Button("Yes", variant="success", id="cd-yes")
                yield Button("No", variant="error", id="cd-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "cd-yes")


# ──────────────────────────────────────────────
#  Main Application
# ──────────────────────────────────────────────

class MinecraftServerManagerApp(App):
    """Tabbed Minecraft Server Manager TUI."""

    TITLE = "⛏️ Minecraft Server Manager"
    SUB_TITLE = "Terminal Edition"
    CSS_PATH = "ui/styles.css"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f1", "show_tab('tab-dashboard')", "Dashboard", show=True),
        Binding("ctrl+p", "show_tab('tab-plugins')", "Plugins", show=True),
        Binding("ctrl+s", "save_current", "Save", show=True),
        Binding("ctrl+b", "create_backup", "Backup"),
    ]

    def __init__(self, config_path: str = "config.json", **kw: Any) -> None:
        super().__init__(**kw)
        self.config_path = config_path

        from server_manager import ServerManager
        from plugin_manager import PluginManager

        self.server_manager = ServerManager(config_path)
        srv = self.server_manager.get_server_config()
        self.plugin_manager = PluginManager(
            plugins_dir=self.server_manager.plugins_dir,
            registry_path="installed_plugins.json",
            server_type=srv.get("type", "paper"),
            mc_version=srv.get("version", "1.20.4"),
        )

    # ── Compose ────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield StatusBar(id="app-status-bar")

        with TabbedContent(
            "📊 Dashboard",
            "⚙️ Settings",
            "☕ Java",
            "🧩 Plugins",
            "📝 Editor",
            "📜 EULA",
            id="main-tabs",
        ):
            # Each TabPane populated in on_mount to keep compose light
            yield TabPane("📊 Dashboard", id="tab-dashboard")
            yield TabPane("⚙️ Settings", id="tab-settings")
            yield TabPane("☕ Java", id="tab-java")
            yield TabPane("🧩 Plugins", id="tab-plugins")
            yield TabPane("📝 Editor", id="tab-editor")
            yield TabPane("📜 EULA", id="tab-eula")

        yield Footer()

    # ── Mount ──────────────────────────────────

    def on_mount(self) -> None:
        logger.info("App started – env: %s", self.server_manager.environment)

        # Populate tabs lazily
        from ui.tabs.dashboard_tab import build_dashboard
        from ui.tabs.settings_tab import build_settings
        from ui.tabs.java_tab import build_java
        from ui.tabs.plugins_tab import build_plugins
        from ui.tabs.editor_tab import build_editor
        from ui.tabs.eula_tab import build_eula

        build_dashboard(self.query_one("#tab-dashboard", TabPane), self)
        build_settings(self.query_one("#tab-settings", TabPane), self)
        build_java(self.query_one("#tab-java", TabPane), self)
        build_plugins(self.query_one("#tab-plugins", TabPane), self)
        build_editor(self.query_one("#tab-editor", TabPane), self)
        build_eula(self.query_one("#tab-eula", TabPane), self)

        # Start periodic refresh
        self.set_interval(2.0, self._refresh_status)
        self._refresh_status()

    # ── Periodic refresh ───────────────────────

    def _refresh_status(self) -> None:
        """Update the status bar and dashboard stats."""
        try:
            status = self.server_manager.get_server_status()
            bar = self.query_one("#app-status-bar", StatusBar)
            bar.server_running = status.running
            bar.mc_ver = status.version or self.server_manager.get_server_config().get("version", "?")
            bar.players = f"{status.players_online}/{status.max_players or 20}"

            active_java = self.server_manager.java_manager.get_active()
            bar.java_ver = f"{active_java.version} ✅" if active_java else "⚠️"
        except Exception as exc:
            logger.debug("Status refresh: %s", exc)

    # ── Actions ────────────────────────────────

    def action_show_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_save_current(self) -> None:
        self.notify("💾 Save triggered (context-dependent)")

    def action_create_backup(self) -> None:
        try:
            result = self.server_manager.create_backup()
            if isinstance(result, tuple):
                ok, msg = result
            else:
                ok, msg = result.success, result.message
            self.notify(msg, severity="information" if ok else "error")
        except Exception as exc:
            self.notify(f"Backup failed: {exc}", severity="error")

    # ── Helpers for tabs ───────────────────────

    def confirm(self, message: str, callback) -> None:
        """Push a confirmation dialog; callback(bool) on dismiss."""
        def _on_dismiss(result: bool) -> None:
            callback(result)
        self.push_screen(ConfirmScreen(message), _on_dismiss)


# ──────────────────────────────────────────────
#  Headless CLI
# ──────────────────────────────────────────────

def run_headless(args: argparse.Namespace) -> None:
    from server_manager import ServerManager
    from rich.console import Console
    from rich.table import Table

    console = Console()
    mgr = ServerManager(args.config)
    console.print("\n[bold green]⛏️  Minecraft Server Manager[/] (headless)\n")

    cfg = mgr.get_server_config()
    t = Table(title="Server Configuration")
    t.add_column("Setting", style="cyan")
    t.add_column("Value", style="white")
    for k, v in cfg.items():
        t.add_row(k, str(v))
    console.print(t)

    status = mgr.get_server_status()
    console.print(f"\n[bold]Status:[/] {'🟢 Running' if status.running else '🔴 Stopped'}")
    console.print(f"[bold]Environment:[/] {mgr.environment}")
    res = mgr.get_system_resources()
    console.print(f"[bold]CPU:[/] {res.get('cpu_percent', '?')}%")
    console.print(f"[bold]RAM:[/] {res.get('ram_used_mb', '?')} / {res.get('ram_total_mb', '?')} MB\n")


# ──────────────────────────────────────────────
#  Entry Point
# ──────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if args.type or args.version or args.ram:
        cfg_path = Path(args.config)
        config = json.loads(cfg_path.read_text()) if cfg_path.exists() else {"server": {}}
        if args.type:
            config.setdefault("server", {})["type"] = args.type
        if args.version:
            config.setdefault("server", {})["version"] = args.version
        if args.ram:
            config.setdefault("server", {})["ram"] = args.ram
        cfg_path.write_text(json.dumps(config, indent=2))

    if args.headless:
        run_headless(args)
    else:
        MinecraftServerManagerApp(config_path=args.config).run()


if __name__ == "__main__":
    main()
