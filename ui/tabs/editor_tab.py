"""File Editor tab – file list, text editor, save/reset/backup."""
from __future__ import annotations
from typing import TYPE_CHECKING

from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button, DataTable, Label, Static, TabPane, TextArea,
)

if TYPE_CHECKING:
    from main import MinecraftServerManagerApp


def build_editor(pane: TabPane, app: "MinecraftServerManagerApp") -> None:
    fe = app.server_manager.file_editor

    pane.mount(Label("📝  File Editor", classes="panel-title"))

    layout = Horizontal(id="editor-layout")
    pane.mount(layout)

    # ── File list (left) ──
    left = Vertical(id="file-tree")
    layout.mount(left)
    left.mount(Label("📁 Files", classes="settings-group-title"))
    file_table = DataTable(id="file-list")
    left.mount(file_table)
    left.mount(Button("🔄 Refresh", id="ed-refresh", classes="action-btn btn-secondary btn-small"))

    # ── Editor (right) ──
    right = Vertical(id="editor-right")
    layout.mount(right)
    right.mount(Label("", id="ed-filename"))
    editor = TextArea(id="ed-textarea", language="toml", theme="monokai")
    right.mount(editor)

    statusbar = Label("No file loaded", id="editor-statusbar")
    right.mount(statusbar)

    btns = Horizontal(id="editor-buttons")
    right.mount(btns)
    btns.mount(Button("💾 Save", id="ed-save", classes="action-btn btn-start"))
    btns.mount(Button("↺ Reset", id="ed-reset", classes="action-btn btn-secondary"))
    btns.mount(Button("📋 Backup", id="ed-backup", classes="action-btn btn-primary"))
    btns.mount(Button("✅ Validate", id="ed-validate", classes="action-btn btn-warning"))

    _current_file: dict = {"path": None, "original": ""}

    def _init() -> None:
        try:
            ft = pane.query_one("#file-list", DataTable)
            ft.add_columns("File", "Type", "Size")
            _refresh_files()
        except Exception:
            pass

    def _refresh_files() -> None:
        try:
            ft = pane.query_one("#file-list", DataTable)
            ft.clear()
            files = fe.list_editable_files()
            for f in files:
                size = f"{f.size_bytes:,} B" if f.size_bytes < 10240 else f"{f.size_bytes // 1024} KB"
                ft.add_row(f.name, f.file_type, size)
        except Exception:
            pass

    def _load_file(name: str) -> None:
        try:
            from pathlib import Path
            fpath = Path(fe.server_dir) / name
            content = fe.read_file(fpath)
            _current_file["path"] = str(fpath)
            _current_file["original"] = content

            ta = pane.query_one("#ed-textarea", TextArea)
            ta.load_text(content)

            # Set syntax language based on extension
            ext = fpath.suffix.lower()
            lang_map = {".json": "json", ".yml": "yaml", ".yaml": "yaml", ".properties": "toml", ".txt": "markdown"}
            ta.language = lang_map.get(ext, "markdown")

            pane.query_one("#ed-filename", Label).update(f"[bold cyan]{name}[/]")
            pane.query_one("#editor-statusbar", Label).update(f"Loaded: {name} ({len(content)} chars)")
        except Exception as exc:
            app.notify(f"Cannot load: {exc}", severity="error")

    app.call_later(_init)

    # ── Events ──
    def _on_btn(event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "ed-refresh":
            _refresh_files()
        elif bid == "ed-save":
            if not _current_file["path"]:
                app.notify("No file loaded", severity="warning")
                return
            try:
                ta = pane.query_one("#ed-textarea", TextArea)
                result = fe.write_file(_current_file["path"], ta.text)
                ok = result.success if hasattr(result, "success") else True
                msg = result.message if hasattr(result, "message") else "Saved"
                app.notify(msg, severity="information" if ok else "error")
                pane.query_one("#editor-statusbar", Label).update(f"[green]Saved ✅[/]")
            except Exception as exc:
                app.notify(f"Save failed: {exc}", severity="error")
        elif bid == "ed-reset":
            if _current_file["original"]:
                pane.query_one("#ed-textarea", TextArea).load_text(_current_file["original"])
                app.notify("Reset to last saved version")
        elif bid == "ed-backup":
            if _current_file["path"]:
                try:
                    bp = fe.create_backup(_current_file["path"])
                    app.notify(f"Backup created: {bp}", severity="information")
                except Exception as exc:
                    app.notify(f"Backup failed: {exc}", severity="error")
        elif bid == "ed-validate":
            if _current_file["path"]:
                ta = pane.query_one("#ed-textarea", TextArea)
                result = fe.validate_file_content(_current_file["path"], ta.text)
                ok = result.success if hasattr(result, "success") else True
                msg = result.message if hasattr(result, "message") else "Valid"
                severity = "information" if ok else "error"
                app.notify(msg, severity=severity)
                color = "green" if ok else "red"
                pane.query_one("#editor-statusbar", Label).update(f"[{color}]{msg}[/]")

    def _on_row(event: DataTable.RowHighlighted) -> None:
        try:
            if event.data_table.id == "file-list":
                row = event.data_table.get_row_at(event.cursor_row)
                _load_file(row[0])
        except Exception:
            pass

    pane.on_button_pressed = _on_btn  # type: ignore[attr-defined]
    pane.on_data_table_row_highlighted = _on_row  # type: ignore[attr-defined]
