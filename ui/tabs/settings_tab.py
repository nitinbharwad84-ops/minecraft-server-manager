"""Settings tab – MC version, server type, world, gameplay, RAM."""
from __future__ import annotations
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, Input, Label, Select, Static, Switch, TabPane,
)

if TYPE_CHECKING:
    from main import MinecraftServerManagerApp

SERVER_TYPES = [
    ("Vanilla", "vanilla"), ("Paper", "paper"), ("Spigot", "spigot"),
    ("Purpur", "purpur"), ("Fabric", "fabric"), ("Forge", "forge"),
    ("Quilt", "quilt"),
]

DIFFICULTIES = [
    ("Peaceful", "peaceful"), ("Easy", "easy"),
    ("Normal", "normal"), ("Hard", "hard"),
]

GAMEMODES = [
    ("Survival", "survival"), ("Creative", "creative"),
    ("Adventure", "adventure"), ("Spectator", "spectator"),
]


def build_settings(pane: TabPane, app: "MinecraftServerManagerApp") -> None:
    sm = app.server_manager
    cfg = sm.get_server_config()

    pane.mount(Label("⚙️  Server Settings", classes="panel-title"))

    # ── Server Config Group ──
    g1 = Vertical(classes="settings-group")
    g1.mount(Label("🖥️ Server Configuration", classes="settings-group-title"))

    r1 = Horizontal(classes="settings-row")
    r1.mount(Label("Server Type:", classes="settings-label"))
    r1.mount(Select(SERVER_TYPES, value=cfg.get("type", "paper"), id="set-type", classes="settings-input"))
    g1.mount(r1)

    r2 = Horizontal(classes="settings-row")
    r2.mount(Label("MC Version:", classes="settings-label"))
    r2.mount(Input(value=cfg.get("version", "1.20.1"), id="set-version", classes="settings-input"))
    g1.mount(r2)

    r3 = Horizontal(classes="settings-row")
    r3.mount(Label("World Name:", classes="settings-label"))
    r3.mount(Input(value=cfg.get("world_name", "world"), id="set-world", classes="settings-input"))
    g1.mount(r3)

    r4 = Horizontal(classes="settings-row")
    r4.mount(Label("Server Port:", classes="settings-label"))
    r4.mount(Input(value=str(cfg.get("port", 25565)), id="set-port", classes="settings-input"))
    g1.mount(r4)

    r5 = Horizontal(classes="settings-row")
    r5.mount(Label("MOTD:", classes="settings-label"))
    r5.mount(Input(value=cfg.get("motd", "A Minecraft Server"), id="set-motd", classes="settings-input"))
    g1.mount(r5)

    pane.mount(g1)

    # ── Gameplay Group ──
    g2 = Vertical(classes="settings-group")
    g2.mount(Label("🎮 Gameplay", classes="settings-group-title"))

    r6 = Horizontal(classes="settings-row")
    r6.mount(Label("Difficulty:", classes="settings-label"))
    r6.mount(Select(DIFFICULTIES, value=cfg.get("difficulty", "normal"), id="set-diff", classes="settings-input"))
    g2.mount(r6)

    r7 = Horizontal(classes="settings-row")
    r7.mount(Label("Gamemode:", classes="settings-label"))
    r7.mount(Select(GAMEMODES, value=cfg.get("gamemode", "survival"), id="set-gm", classes="settings-input"))
    g2.mount(r7)

    r8 = Horizontal(classes="settings-row")
    r8.mount(Label("PvP Enabled:", classes="settings-label"))
    r8.mount(Switch(value=cfg.get("pvp", True), id="set-pvp"))
    g2.mount(r8)

    r9 = Horizontal(classes="settings-row")
    r9.mount(Label("Online Mode:", classes="settings-label"))
    r9.mount(Switch(value=cfg.get("online_mode", True), id="set-online"))
    g2.mount(r9)

    pane.mount(g2)

    # ── Performance Group ──
    g3 = Vertical(classes="settings-group")
    g3.mount(Label("⚡ Performance", classes="settings-group-title"))

    r10 = Horizontal(classes="settings-row")
    r10.mount(Label("Max Players:", classes="settings-label"))
    r10.mount(Input(value=str(cfg.get("max_players", 20)), id="set-maxp", classes="settings-input"))
    g3.mount(r10)

    r11 = Horizontal(classes="settings-row")
    r11.mount(Label("RAM (MB):", classes="settings-label"))
    r11.mount(Input(value=str(cfg.get("ram", 2048)), id="set-ram", classes="settings-input"))
    g3.mount(r11)

    r12 = Horizontal(classes="settings-row")
    r12.mount(Label("View Distance:", classes="settings-label"))
    r12.mount(Input(value=str(cfg.get("view_distance", 10)), id="set-vd", classes="settings-input"))
    g3.mount(r12)

    r13 = Horizontal(classes="settings-row")
    r13.mount(Label("Sim Distance:", classes="settings-label"))
    r13.mount(Input(value=str(cfg.get("simulation_distance", 10)), id="set-sd", classes="settings-input"))
    g3.mount(r13)

    pane.mount(g3)

    # ── Save Button ──
    save_row = Horizontal()
    save_row.mount(Button("💾 Save Settings", id="set-save", classes="action-btn btn-primary"))
    save_row.mount(Button("↺ Reset to Defaults", id="set-reset", classes="action-btn btn-secondary"))
    pane.mount(save_row)
    pane.mount(Label("", id="set-status"))

    # ── Event handling ──
    def _on_btn(event: Button.Pressed) -> None:
        if event.button.id == "set-save":
            try:
                updates = {
                    "type": pane.query_one("#set-type", Select).value,
                    "version": pane.query_one("#set-version", Input).value,
                    "world_name": pane.query_one("#set-world", Input).value,
                    "port": int(pane.query_one("#set-port", Input).value),
                    "motd": pane.query_one("#set-motd", Input).value,
                    "difficulty": pane.query_one("#set-diff", Select).value,
                    "gamemode": pane.query_one("#set-gm", Select).value,
                    "pvp": pane.query_one("#set-pvp", Switch).value,
                    "online_mode": pane.query_one("#set-online", Switch).value,
                    "max_players": int(pane.query_one("#set-maxp", Input).value),
                    "ram": int(pane.query_one("#set-ram", Input).value),
                    "view_distance": int(pane.query_one("#set-vd", Input).value),
                    "simulation_distance": int(pane.query_one("#set-sd", Input).value),
                }
                sm.update_server_config(**updates)
                app.notify("✅ Settings saved!", severity="information")
                pane.query_one("#set-status", Label).update("[green]Settings saved successfully[/]")
            except Exception as exc:
                app.notify(f"❌ {exc}", severity="error")
                pane.query_one("#set-status", Label).update(f"[red]Error: {exc}[/]")
        elif event.button.id == "set-reset":
            app.notify("Settings reset to defaults", severity="information")

    pane.on_button_pressed = _on_btn  # type: ignore[attr-defined]
