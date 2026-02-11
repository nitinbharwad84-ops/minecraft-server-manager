"""EULA & Setup tab – status, text viewer, accept button, setup wizard."""
from __future__ import annotations
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Label, Static, TabPane, TextArea

if TYPE_CHECKING:
    from main import MinecraftServerManagerApp


def build_eula(pane: TabPane, app: "MinecraftServerManagerApp") -> None:
    em = app.server_manager.eula_manager
    sm = app.server_manager

    pane.mount(Label("📜  EULA & Setup", classes="panel-title"))

    # ── EULA Status ──
    status_panel = Vertical(id="eula-status")
    pane.mount(status_panel)
    status_panel.mount(Label("", id="eula-status-label"))
    status_panel.mount(Label("", id="eula-url"))

    # ── EULA Text Viewer ──
    pane.mount(Label("📄 Minecraft EULA", classes="panel-title"))
    eula_text = TextArea(id="eula-text-view", read_only=True, theme="monokai")
    container = Vertical(id="eula-text-container")
    pane.mount(container)
    container.mount(eula_text)

    # ── Actions ──
    actions = Horizontal(id="eula-actions")
    pane.mount(actions)
    actions.mount(Button("✅ Accept EULA", id="eula-accept", classes="action-btn btn-start"))
    actions.mount(Button("❌ Decline EULA", id="eula-decline", classes="action-btn btn-stop"))
    actions.mount(Button("🔄 Check Status", id="eula-check", classes="action-btn btn-secondary"))

    # ── Setup Wizard Section ──
    pane.mount(Label(""))
    pane.mount(Label("🧙 Quick Setup Wizard", classes="panel-title"))

    wizard = Vertical(classes="settings-group")
    pane.mount(wizard)
    wizard.mount(Label(
        "First time? Click below to run the setup wizard.\n"
        "This will accept the EULA, generate server.properties,\n"
        "and ensure Java is configured.",
        id="wizard-desc",
    ))
    wizard.mount(Button("🚀 Run Setup Wizard", id="eula-wizard", classes="action-btn btn-primary"))
    wizard.mount(Label("", id="wizard-status"))

    # ── Properties quick editor ──
    pane.mount(Label(""))
    pane.mount(Label("⚙️ server.properties Quick Edit", classes="panel-title"))
    props_area = TextArea(id="props-editor", language="toml", theme="monokai")
    pane.mount(props_area)

    props_btns = Horizontal()
    pane.mount(props_btns)
    props_btns.mount(Button("💾 Save Properties", id="props-save", classes="action-btn btn-primary"))
    props_btns.mount(Button("🔄 Reload", id="props-reload", classes="action-btn btn-secondary"))

    # ── Init ──
    def _init() -> None:
        _refresh_status()
        _load_eula_text()
        _load_properties()

    def _refresh_status() -> None:
        try:
            accepted = em.check_eula_status()
            lbl = pane.query_one("#eula-status-label", Label)
            if accepted:
                lbl.update("[bold green]✅ EULA Status: ACCEPTED[/]")
            else:
                lbl.update("[bold red]❌ EULA Status: NOT ACCEPTED[/]")
            pane.query_one("#eula-url", Label).update(
                f"[dim]Official: {em.get_eula_url()}[/]"
            )
        except Exception:
            pass

    def _load_eula_text() -> None:
        try:
            text = em.get_eula_text()
            pane.query_one("#eula-text-view", TextArea).load_text(text)
        except Exception:
            pass

    def _load_properties() -> None:
        try:
            props = sm.get_server_properties()
            lines = [f"{k}={v}" for k, v in props.items()]
            pane.query_one("#props-editor", TextArea).load_text("\n".join(lines))
        except Exception:
            pane.query_one("#props-editor", TextArea).load_text("# server.properties not found\n# Start the server once to generate it.")

    app.call_later(_init)

    # ── Events ──
    def _on_btn(event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "eula-accept":
            result = em.auto_accept_eula()
            ok = result.success if hasattr(result, "success") else bool(result)
            msg = result.message if hasattr(result, "message") else ("EULA accepted" if ok else "Failed")
            app.notify(msg, severity="information" if ok else "error")
            _refresh_status()
        elif bid == "eula-decline":
            def _confirmed(yes: bool) -> None:
                if not yes:
                    return
                ok = em.decline()
                app.notify(
                    "EULA declined" if ok else "Failed to decline",
                    severity="information" if ok else "error",
                )
                _refresh_status()
            app.confirm("⚠️ Decline EULA? Server won't start.", _confirmed)
        elif bid == "eula-check":
            _refresh_status()
            app.notify("EULA status refreshed")
        elif bid == "eula-wizard":
            _run_wizard()
        elif bid == "props-save":
            try:
                text = pane.query_one("#props-editor", TextArea).text
                for line in text.strip().split("\n"):
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        sm.update_server_properties(k.strip(), v.strip())
                app.notify("✅ Properties saved!", severity="information")
            except Exception as exc:
                app.notify(f"Save failed: {exc}", severity="error")
        elif bid == "props-reload":
            _load_properties()
            app.notify("Properties reloaded")

    def _run_wizard() -> None:
        steps = []
        wl = pane.query_one("#wizard-status", Label)

        # Step 1: EULA
        result = em.auto_accept_eula()
        ok = result.success if hasattr(result, "success") else bool(result)
        steps.append(f"{'✅' if ok else '❌'} EULA: {'accepted' if ok else 'failed'}")

        # Step 2: Generate server.properties
        try:
            sm.generate_server_properties()
            steps.append("✅ server.properties generated")
        except Exception as exc:
            steps.append(f"❌ server.properties: {exc}")

        # Step 3: Java check
        try:
            active = sm.java_manager.get_active()
            if active:
                steps.append(f"✅ Java {active.version} ready")
            else:
                found = sm.java_manager.detect_system_java()
                if found:
                    steps.append(f"✅ Found {len(found)} Java install(s)")
                else:
                    steps.append("⚠️ No Java found – install from Java tab")
        except Exception as exc:
            steps.append(f"❌ Java: {exc}")

        wl.update("\n".join(steps))
        _refresh_status()
        _load_properties()
        app.notify("Setup wizard complete!")

    pane.on_button_pressed = _on_btn  # type: ignore[attr-defined]
