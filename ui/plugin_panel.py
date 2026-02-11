"""
ui/plugin_panel.py
==================
Textual screen for searching, installing, and managing plugins.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, DataTable, Footer, Header, Input, Label, Static, TabbedContent, TabPane,
)

from plugin_manager import PluginManager


class PluginScreen(Screen):
    """Plugin management screen with search, install, and manage tabs."""

    BINDINGS = [
        ("escape", "app.pop_screen", "Back"),
    ]

    def __init__(self, plugin_manager: PluginManager) -> None:
        super().__init__()
        self.plugin_manager = plugin_manager

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with TabbedContent():
            # ── Search Tab ──
            with TabPane("🔍 Search", id="tab-search"):
                with Vertical():
                    with Horizontal(id="plugin-search"):
                        yield Input(placeholder="Search plugins…", id="search-input")
                        yield Button("Search", id="btn-search", classes="action-btn btn-primary")
                    yield DataTable(id="search-results", classes="data-table")
                    with Horizontal():
                        yield Button("⬇ Install Selected", id="btn-install", classes="action-btn btn-start")

            # ── Installed Tab ──
            with TabPane("📦 Installed", id="tab-installed"):
                with Vertical():
                    yield DataTable(id="installed-table", classes="data-table")
                    with Horizontal():
                        yield Button("🔄 Check Updates", id="btn-updates", classes="action-btn btn-primary")
                        yield Button("🗑 Remove", id="btn-remove", classes="action-btn btn-stop")

        yield Footer()

    def on_mount(self) -> None:
        # Search results table
        search_tbl = self.query_one("#search-results", DataTable)
        search_tbl.add_columns("Name", "Author", "Downloads", "Source")

        # Installed table
        inst_tbl = self.query_one("#installed-table", DataTable)
        inst_tbl.add_columns("Name", "Version", "Source", "MC Version", "Installed")
        self._refresh_installed()

    def _refresh_installed(self) -> None:
        tbl = self.query_one("#installed-table", DataTable)
        tbl.clear()
        for p in self.plugin_manager.list_installed():
            tbl.add_row(p.name, p.version, p.source, p.mc_version, p.installed_at[:10])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id
        if btn == "btn-search":
            self._do_search()
        elif btn == "btn-install":
            self._do_install()
        elif btn == "btn-remove":
            self._do_remove()
        elif btn == "btn-updates":
            self.notify("Checking for updates…")
            self.run_worker(self._check_updates())

    def _do_search(self) -> None:
        query = self.query_one("#search-input", Input).value.strip()
        if not query:
            self.notify("Enter a search term", severity="warning")
            return
        self.notify(f"Searching for '{query}'…")
        self.run_worker(self._search(query))

    async def _search(self, query: str) -> None:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            results = await self.plugin_manager.search(query, session, limit=20)

        tbl = self.query_one("#search-results", DataTable)
        tbl.clear()
        self._search_results = results

        for r in results:
            dl = f"{r.downloads:,}" if r.downloads else "N/A"
            tbl.add_row(r.name, r.author, dl, r.source)

        self.notify(f"Found {len(results)} plugins")

    def _do_install(self) -> None:
        tbl = self.query_one("#search-results", DataTable)
        if not hasattr(self, "_search_results") or tbl.cursor_row is None:
            self.notify("Select a plugin first", severity="warning")
            return
        idx = tbl.cursor_row
        if 0 <= idx < len(self._search_results):
            plugin = self._search_results[idx]
            self.notify(f"Installing {plugin.name}…")
            self.run_worker(self._install(plugin))

    async def _install(self, plugin) -> None:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            ok, msg = await self.plugin_manager.install(plugin, session)
            self.notify(msg, severity="information" if ok else "error")
        self._refresh_installed()

    def _do_remove(self) -> None:
        tbl = self.query_one("#installed-table", DataTable)
        if tbl.cursor_row is None:
            return
        row = tbl.get_row_at(tbl.cursor_row)
        name = row[0]
        ok, msg = self.plugin_manager.remove(name)
        self.notify(msg, severity="information" if ok else "error")
        self._refresh_installed()

    async def _check_updates(self) -> None:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            updates = await self.plugin_manager.check_updates(session)
        if updates:
            names = ", ".join(p.name for p, _ in updates)
            self.notify(f"Updates available: {names}")
        else:
            self.notify("All plugins are up to date")
