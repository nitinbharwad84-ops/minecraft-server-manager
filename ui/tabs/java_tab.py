"""Java & System tab – installed Java versions, system info, install buttons."""
from __future__ import annotations
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Static, TabPane

if TYPE_CHECKING:
    from main import MinecraftServerManagerApp


def build_java(pane: TabPane, app: "MinecraftServerManagerApp") -> None:
    jm = app.server_manager.java_manager
    sm = app.server_manager

    pane.mount(Label("☕  Java & System", classes="panel-title"))

    # ── Java info panel ──
    info = Vertical(id="java-info")
    pane.mount(info)
    info.mount(Label("", id="java-active-label"))
    info.mount(Label("", id="java-required-label"))
    info.mount(Label("", id="java-compat-label"))

    # ── Installed versions table ──
    pane.mount(Label("📋 Installed Java Versions", classes="panel-title"))
    table = DataTable(id="java-list")
    pane.mount(table)

    # ── Actions ──
    actions = Horizontal(id="java-actions")
    pane.mount(actions)
    actions.mount(Button("🔍 Detect System Java", id="java-detect", classes="action-btn btn-primary"))
    actions.mount(Button("⬇ Install Java 17", id="java-inst-17", classes="action-btn btn-primary"))
    actions.mount(Button("⬇ Install Java 21", id="java-inst-21", classes="action-btn btn-primary"))
    actions.mount(Button("✓ Set Active", id="java-activate", classes="action-btn btn-start"))
    actions.mount(Button("🗑 Remove", id="java-remove", classes="action-btn btn-stop"))

    # ── System info panel ──
    sys_panel = Vertical(id="system-info")
    pane.mount(sys_panel)
    sys_panel.mount(Label("🖥️ System Information", classes="settings-group-title"))
    sys_panel.mount(Label("", id="sys-info-text"))

    # ── Initialization ──
    def _init() -> None:
        try:
            t = pane.query_one("#java-list", DataTable)
            t.add_columns("Version", "Path", "Vendor", "Status")
            _refresh()
            _refresh_sys()
        except Exception:
            pass

    def _refresh() -> None:
        try:
            t = pane.query_one("#java-list", DataTable)
            t.clear()
            active = jm.get_active()

            if active:
                pane.query_one("#java-active-label", Label).update(
                    f"[green]Active:[/] Java {active.version} ({active.vendor})"
                )
            else:
                pane.query_one("#java-active-label", Label).update("[yellow]Active: None (using system default)[/]")

            srv_cfg = sm.get_server_config()
            req = srv_cfg.get("java_version", 17)
            pane.query_one("#java-required-label", Label).update(f"Required for MC {srv_cfg.get('version', '?')}: Java {req}")

            if active and active.version >= req:
                pane.query_one("#java-compat-label", Label).update("[green]✅ Compatible[/]")
            elif active:
                pane.query_one("#java-compat-label", Label).update("[red]❌ Incompatible – need Java {req}+[/]")
            else:
                pane.query_one("#java-compat-label", Label).update("[yellow]⚠️ No Java detected[/]")

            for inst in jm.list_installed():
                is_active = "✓ Active" if (active and active.version == inst.version) else ""
                valid = "✅ Valid" if inst.is_valid() else "❌ Invalid"
                status = f"{is_active} {valid}".strip()
                t.add_row(str(inst.version), str(inst.path), inst.vendor, status)
        except Exception:
            pass

    def _refresh_sys() -> None:
        try:
            import platform as plat
            res = sm.get_system_resources()
            lines = [
                f"OS: {plat.system()} {plat.release()}",
                f"CPU: {res.get('cpu_count', '?')} cores @ {res.get('cpu_percent', '?')}%",
                f"RAM: {res.get('ram_used_mb', '?')} / {res.get('ram_total_mb', '?')} MB ({res.get('ram_percent', '?')}%)",
                f"Disk: {res.get('disk_used_gb', '?')} / {res.get('disk_total_gb', '?')} GB",
                f"Python: {plat.python_version()}",
            ]
            pane.query_one("#sys-info-text", Label).update("\n".join(lines))
        except Exception:
            pass

    app.call_later(_init)

    # ── Events ──
    def _on_btn(event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "java-detect":
            found = jm.detect_system_java()
            _refresh()
            app.notify(f"Found {len(found)} Java installation(s)")
        elif bid in ("java-inst-17", "java-inst-21"):
            ver = 17 if "17" in bid else 21
            app.notify(f"Installing Java {ver}… please wait")

            async def _do() -> None:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    result = await jm.download_java(ver, session)
                    if result:
                        jm.set_active(ver)
                        app.notify(f"✅ Java {ver} installed!", severity="information")
                    else:
                        app.notify(f"❌ Failed to install Java {ver}", severity="error")
                _refresh()

            app.run_worker(_do())
        elif bid == "java-activate":
            t = pane.query_one("#java-list", DataTable)
            if t.cursor_row is not None:
                row = t.get_row_at(t.cursor_row)
                v = int(row[0])
                if jm.set_active(v):
                    app.notify(f"Java {v} set as active")
                    _refresh()
                else:
                    app.notify("Failed", severity="error")
        elif bid == "java-remove":
            t = pane.query_one("#java-list", DataTable)
            if t.cursor_row is not None:
                row = t.get_row_at(t.cursor_row)
                v = int(row[0])
                if jm.remove(v):
                    app.notify(f"Java {v} removed")
                    _refresh()
                else:
                    app.notify("Cannot remove system installs", severity="error")

    pane.on_button_pressed = _on_btn  # type: ignore[attr-defined]
