"""Plugins tab – search, install, uninstall, update plugins."""
from __future__ import annotations
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, DataTable, Input, Label, ProgressBar, Static, TabPane,
)

if TYPE_CHECKING:
    from main import MinecraftServerManagerApp


def build_plugins(pane: TabPane, app: "MinecraftServerManagerApp") -> None:
    pm = app.plugin_manager

    pane.mount(Label("🧩  Plugin Manager", classes="panel-title"))

    # ── Search row ──
    search_row = Horizontal(id="plugin-search-row")
    search_row.mount(Input(placeholder="Search plugins…", id="plug-query"))
    search_row.mount(Button("🔍 Search", id="plug-search", classes="action-btn btn-primary"))
    search_row.mount(Button("🔄 Check Updates", id="plug-updates", classes="action-btn btn-secondary"))
    pane.mount(search_row)

    # ── Progress ──
    pane.mount(Label("", id="plug-progress-label"))
    pane.mount(ProgressBar(total=100, show_eta=False, id="plug-progress"))

    # ── Search results table ──
    pane.mount(Label("🔎 Search Results", classes="panel-title"))
    results_table = DataTable(id="plug-results")
    pane.mount(results_table)

    # ── Detail panel ──
    detail = Vertical(id="plugin-details")
    detail.mount(Label("Select a plugin to view details", id="plug-detail-text"))
    pane.mount(detail)

    # ── Action buttons ──
    actions = Horizontal()
    actions.mount(Button("⬇ Install", id="plug-install", classes="action-btn btn-start"))
    actions.mount(Button("🗑 Uninstall", id="plug-uninstall", classes="action-btn btn-stop"))
    actions.mount(Button("⬆ Update", id="plug-update", classes="action-btn btn-warning"))
    actions.mount(Button("📁 Install from File", id="plug-file", classes="action-btn btn-secondary"))
    pane.mount(actions)

    # ── Installed plugins ──
    pane.mount(Label("📦 Installed Plugins", classes="panel-title"))
    installed_table = DataTable(id="plug-installed")
    pane.mount(installed_table)

    # ── Search results cache ──
    _search_results: list = []

    def _init() -> None:
        try:
            rt = pane.query_one("#plug-results", DataTable)
            rt.add_columns("Name", "Source", "Downloads", "MC Version", "Rating")
            it = pane.query_one("#plug-installed", DataTable)
            it.add_columns("Name", "Version", "Source", "Installed")
            pane.query_one("#plug-progress", ProgressBar).display = False
            pane.query_one("#plug-progress-label", Label).display = False
            _refresh_installed()
        except Exception:
            pass

    def _refresh_installed() -> None:
        try:
            it = pane.query_one("#plug-installed", DataTable)
            it.clear()
            for p in pm.get_installed_plugins():
                it.add_row(p.name, p.version, p.source, p.installed_at[:10] if p.installed_at else "—")
        except Exception:
            pass

    def _show_progress(msg: str) -> None:
        try:
            pane.query_one("#plug-progress", ProgressBar).display = True
            pane.query_one("#plug-progress-label", Label).display = True
            pane.query_one("#plug-progress-label", Label).update(msg)
        except Exception:
            pass

    def _hide_progress() -> None:
        try:
            pane.query_one("#plug-progress", ProgressBar).display = False
            pane.query_one("#plug-progress-label", Label).display = False
        except Exception:
            pass

    app.call_later(_init)

    # ── Event handlers ──
    def _on_btn(event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "plug-search":
            _do_search()
        elif bid == "plug-install":
            _do_install()
        elif bid == "plug-uninstall":
            _do_uninstall()
        elif bid == "plug-update":
            _do_update()
        elif bid == "plug-updates":
            _do_check_updates()
        elif bid == "plug-file":
            app.notify("Use: install_from_file('<path>') via console", severity="information")

    def _do_search() -> None:
        query = pane.query_one("#plug-query", Input).value.strip()
        if not query:
            app.notify("Enter a search query", severity="warning")
            return
        _show_progress(f"Searching for '{query}'…")

        async def _search() -> None:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                results = await pm.search_plugins(query, session=session)
            _search_results.clear()
            _search_results.extend(results)
            rt = pane.query_one("#plug-results", DataTable)
            rt.clear()
            for r in results:
                rt.add_row(
                    r.name,
                    r.source,
                    f"{r.downloads:,}" if r.downloads else "—",
                    ", ".join(r.mc_versions[:2]) if r.mc_versions else "—",
                    f"★ {r.rating:.1f}" if r.rating else "—",
                )
            _hide_progress()
            app.notify(f"Found {len(results)} plugin(s)")

        app.run_worker(_search())

    def _do_install() -> None:
        rt = pane.query_one("#plug-results", DataTable)
        if rt.cursor_row is None or not _search_results:
            app.notify("Select a plugin first", severity="warning")
            return
        idx = rt.cursor_row
        if idx >= len(_search_results):
            return
        plugin = _search_results[idx]
        _show_progress(f"Installing {plugin.name}…")

        async def _install() -> None:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                result = await pm.install_plugin(plugin.name, session=session, plugin=plugin)
            ok = result.success if hasattr(result, "success") else result[0]
            msg = result.message if hasattr(result, "message") else result[1]
            app.notify(msg, severity="information" if ok else "error")
            _hide_progress()
            _refresh_installed()

        app.run_worker(_install())

    def _do_uninstall() -> None:
        it = pane.query_one("#plug-installed", DataTable)
        if it.cursor_row is None:
            app.notify("Select an installed plugin", severity="warning")
            return
        row = it.get_row_at(it.cursor_row)
        name = row[0]

        def _confirmed(yes: bool) -> None:
            if not yes:
                return
            result = pm.uninstall_plugin(name)
            ok = result.success if hasattr(result, "success") else result[0]
            msg = result.message if hasattr(result, "message") else result[1]
            app.notify(msg, severity="information" if ok else "error")
            _refresh_installed()

        app.confirm(f"🗑 Uninstall '{name}'?", _confirmed)

    def _do_update() -> None:
        it = pane.query_one("#plug-installed", DataTable)
        if it.cursor_row is None:
            app.notify("Select an installed plugin", severity="warning")
            return
        row = it.get_row_at(it.cursor_row)
        name = row[0]
        _show_progress(f"Updating {name}…")

        async def _update() -> None:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                result = await pm.update_plugin(name, session=session)
            ok = result.success if hasattr(result, "success") else result[0]
            msg = result.message if hasattr(result, "message") else result[1]
            app.notify(msg, severity="information" if ok else "error")
            _hide_progress()
            _refresh_installed()

        app.run_worker(_update())

    def _do_check_updates() -> None:
        _show_progress("Checking for updates…")

        async def _check() -> None:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                updates = await pm.check_plugin_updates(session=session)
            if updates:
                lines = [f"{k} → {v}" for k, v in updates.items()]
                app.notify(f"Updates: {', '.join(lines)}", severity="information")
            else:
                app.notify("All plugins up to date ✅")
            _hide_progress()

        app.run_worker(_check())

    # ── Row selection ──
    def _on_row_select(event: DataTable.RowHighlighted) -> None:
        try:
            if event.data_table.id == "plug-results" and _search_results:
                idx = event.cursor_row
                if idx < len(_search_results):
                    p = _search_results[idx]
                    detail_text = (
                        f"[bold]{p.name}[/] ({p.source})\n"
                        f"Downloads: {p.downloads:,}  |  "
                        f"MC: {', '.join(p.mc_versions[:3]) if p.mc_versions else '—'}\n"
                        f"{p.description[:200] if p.description else 'No description'}"
                    )
                    pane.query_one("#plug-detail-text", Label).update(detail_text)
        except Exception:
            pass

    pane.on_button_pressed = _on_btn  # type: ignore[attr-defined]
    pane.on_data_table_row_highlighted = _on_row_select  # type: ignore[attr-defined]
