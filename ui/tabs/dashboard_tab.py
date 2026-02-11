"""Dashboard tab – server controls, quick stats, logs, recent actions."""
from __future__ import annotations
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, Static, TabPane
from ui.widgets import StatusIndicator, ResourceBar, ServerLogView

if TYPE_CHECKING:
    from main import MinecraftServerManagerApp


def build_dashboard(pane: TabPane, app: "MinecraftServerManagerApp") -> None:
    """Mount dashboard widgets into the tab pane."""
    sm = app.server_manager

    # ── Quick Stats row ──
    stats = Horizontal(id="quick-stats")

    mem_card = Vertical(classes="stat-card")
    mem_card.mount(Label("—", id="stat-mem-val", classes="stat-value"))
    mem_card.mount(Label("Memory", classes="stat-label"))

    tps_card = Vertical(classes="stat-card")
    tps_card.mount(Label("20.0", id="stat-tps-val", classes="stat-value"))
    tps_card.mount(Label("TPS", classes="stat-label"))

    players_card = Vertical(classes="stat-card")
    players_card.mount(Label("0", id="stat-players-val", classes="stat-value"))
    players_card.mount(Label("Players", classes="stat-label"))

    uptime_card = Vertical(classes="stat-card")
    uptime_card.mount(Label("—", id="stat-uptime-val", classes="stat-value"))
    uptime_card.mount(Label("Uptime", classes="stat-label"))

    stats.mount(mem_card)
    stats.mount(tps_card)
    stats.mount(players_card)
    stats.mount(uptime_card)
    pane.mount(stats)

    # ── Server Controls ──
    controls = Horizontal(id="server-controls")
    controls.mount(Button("▶ Start", id="dash-start", classes="action-btn btn-start"))
    controls.mount(Button("■ Stop", id="dash-stop", classes="action-btn btn-stop"))
    controls.mount(Button("↻ Restart", id="dash-restart", classes="action-btn btn-primary"))
    controls.mount(Button("💾 Backup", id="dash-backup", classes="action-btn btn-secondary"))
    pane.mount(controls)

    # ── Main split ──
    main = Horizontal(id="dashboard-main")

    # Console
    left = Vertical(id="dash-left")
    left.mount(Label("📋 Server Console", classes="panel-title"))
    left.mount(ServerLogView(id="log-view"))
    left.mount(Input(placeholder="Type server command…", id="cmd-input"))

    # Resources
    right = Vertical(id="dash-right")
    right.mount(Label("📊 System Resources", classes="panel-title"))
    cpu = ResourceBar(id="cpu-bar")
    ram = ResourceBar(id="ram-bar")
    disk = ResourceBar(id="disk-bar")
    right.mount(cpu)
    right.mount(ram)
    right.mount(disk)
    right.mount(Label("", id="uptime-label"))

    # Recent actions
    right.mount(Label("📝 Recent Actions", classes="panel-title"))
    actions_table = DataTable(id="actions-table")
    right.mount(actions_table)

    main.mount(left)
    main.mount(right)
    pane.mount(main)

    # ── Configure after mount ──
    def _post_mount() -> None:
        try:
            cpu.label = "CPU"
            cpu.unit = "%"
            ram.label = "RAM"
            ram.unit = " MB"
            disk.label = "Disk"
            disk.unit = " GB"
            at = pane.query_one("#actions-table", DataTable)
            at.add_columns("Time", "Action", "Result")
        except Exception:
            pass

    app.call_later(_post_mount)

    # ── Wire events ──
    def _on_btn(event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "dash-start":
            result = sm.start_server()
            _ok = result.success if hasattr(result, "success") else result[0] if isinstance(result, tuple) else bool(result)
            _msg = result.message if hasattr(result, "message") else result[1] if isinstance(result, tuple) else str(result)
            app.notify(_msg, severity="information" if _ok else "error")
            _add_action("Start Server", _msg)
        elif bid == "dash-stop":
            def _do_stop(confirmed: bool) -> None:
                if not confirmed:
                    return
                result = sm.stop_server()
                _ok = result.success if hasattr(result, "success") else result[0] if isinstance(result, tuple) else bool(result)
                _msg = result.message if hasattr(result, "message") else result[1] if isinstance(result, tuple) else str(result)
                app.notify(_msg, severity="information" if _ok else "error")
                _add_action("Stop Server", _msg)
            app.confirm("⚠️ Stop the server?", _do_stop)
        elif bid == "dash-restart":
            result = sm.restart_server()
            _ok = result.success if hasattr(result, "success") else result[0] if isinstance(result, tuple) else bool(result)
            _msg = result.message if hasattr(result, "message") else result[1] if isinstance(result, tuple) else str(result)
            app.notify(_msg, severity="information" if _ok else "error")
            _add_action("Restart Server", _msg)
        elif bid == "dash-backup":
            app.action_create_backup()
            _add_action("Backup", "Triggered")

    def _on_input(event: Input.Submitted) -> None:
        if event.input.id == "cmd-input" and event.value.strip():
            sent = sm.send_command(event.value.strip())
            if sent:
                app.notify(f"Sent: {event.value.strip()}")
                _add_action("Command", event.value.strip())
            else:
                app.notify("Server not running", severity="error")
            event.input.value = ""

    from datetime import datetime

    def _add_action(action: str, result: str) -> None:
        try:
            t = pane.query_one("#actions-table", DataTable)
            now = datetime.now().strftime("%H:%M:%S")
            t.add_row(now, action, result[:40])
        except Exception:
            pass

    pane.on_button_pressed = _on_btn  # type: ignore[attr-defined]
    pane.on_input_submitted = _on_input  # type: ignore[attr-defined]

    # Periodic status refresh
    def _refresh() -> None:
        try:
            status = sm.get_server_status()
            resources = sm.get_system_resources()

            pane.query_one("#stat-mem-val", Label).update(f"{status.ram_used_mb:.0f} MB")
            pane.query_one("#stat-tps-val", Label).update(f"{status.tps:.1f}")
            pane.query_one("#stat-players-val", Label).update(str(status.players_online))
            if status.running:
                mins = int(status.uptime_seconds // 60)
                pane.query_one("#stat-uptime-val", Label).update(f"{mins}m")
            else:
                pane.query_one("#stat-uptime-val", Label).update("—")

            cpu.value = resources.get("cpu_percent", 0)
            ram.value = resources.get("ram_used_mb", 0)
            ram.max_value = resources.get("ram_total_mb", 100)
            disk.value = resources.get("disk_used_gb", 0)
            disk.max_value = resources.get("disk_total_gb", 100)

            log_lines = sm.get_recent_logs(50)
            if log_lines:
                lv = pane.query_one("#log-view", ServerLogView)
                lv.load_lines(log_lines)
        except Exception:
            pass

    app.set_interval(2.5, _refresh)
