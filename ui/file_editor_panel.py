"""
ui/file_editor_panel.py
=======================
Full-featured Textual screen for editing Minecraft server configuration files.

Layout:
  LEFT   – Categorized file browser with metadata
  CENTER – Text editor with line numbers & syntax support
  RIGHT  – File properties, syntax hints, validation status
  BOTTOM – Action bar (save, reset, backup, restore, delete)

Keyboard Shortcuts:
  Ctrl+S  – Save            Ctrl+Z  – Undo
  Ctrl+Y  – Redo            Ctrl+F  – Find / Replace
  Ctrl+G  – Go to line      Ctrl+W  – Toggle word wrap
  Ctrl+R  – Toggle read-only
  Escape  – Back to dashboard
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    OptionList,
    RichLog,
    Select,
    Static,
    Switch,
    TextArea,
    Tree,
)
from textual.widgets.option_list import Option
from textual.widgets.tree import TreeNode

from file_editor import FileEditor, FileInfo, FileResult


# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────

# Categories for grouping files in the browser
FILE_CATEGORIES: Dict[str, List[str]] = {
    "⚙️  Server Config": [
        "server.properties",
        "eula.txt",
    ],
    "👥 Server Settings": [
        "ops.json",
        "whitelist.json",
        "banned-players.json",
        "banned-ips.json",
        "usercache.json",
    ],
    "🔧 Minecraft Config": [
        "bukkit.yml",
        "spigot.yml",
        "paper.yml",
        "paper-global.yml",
        "paper-world-defaults.yml",
    ],
    "🔌 Plugin Configs": [],  # dynamically populated
}

# server.properties key descriptions
PROPERTY_DESCRIPTIONS: Dict[str, str] = {
    "server-port": "Port the server listens on (default 25565)",
    "gamemode": "Default game mode: survival, creative, adventure, spectator",
    "difficulty": "World difficulty: peaceful, easy, normal, hard",
    "max-players": "Maximum simultaneous players",
    "pvp": "Allow player-vs-player combat",
    "online-mode": "Verify players against Mojang (set false for offline)",
    "level-name": "Name of the world folder",
    "motd": "Message shown in the server list",
    "view-distance": "Render distance in chunks (2-32)",
    "simulation-distance": "Tick distance in chunks (2-32)",
    "spawn-protection": "Radius around spawn protected from building",
    "enable-command-block": "Allow command blocks",
    "allow-flight": "Allow flying in survival mode",
    "white-list": "Enable the player whitelist",
    "max-world-size": "Maximum world border radius",
    "hardcore": "One life – death bans the player",
    "level-seed": "World generation seed",
    "level-type": "World type: minecraft:normal, flat, etc.",
    "server-ip": "IP address to bind to (leave blank for all)",
    "enable-rcon": "Enable remote console",
    "rcon.password": "RCON password",
    "rcon.port": "RCON port (default 25575)",
    "enable-query": "Enable GameSpy4 query protocol",
    "query.port": "Query port (default 25565)",
    "enforce-whitelist": "Kick non-whitelisted players on reload",
    "max-tick-time": "Max ms per tick before watchdog kills server (-1 disable)",
    "network-compression-threshold": "Packet compression threshold in bytes",
    "op-permission-level": "Default OP permission level (1-4)",
    "player-idle-timeout": "Minutes before kicking idle players (0 = never)",
    "prevent-proxy-connections": "Kick players connecting via proxy/VPN",
    "rate-limit": "Max packets per second before kick (0 = disable)",
    "resource-pack": "URL to server resource pack",
    "spawn-animals": "Allow animal spawning",
    "spawn-monsters": "Allow monster spawning",
    "spawn-npcs": "Allow villager spawning",
}


# ──────────────────────────────────────────────
#  Confirm Dialog (inline)
# ──────────────────────────────────────────────

class ConfirmDialog(Static):
    """Modal-like confirmation dialog rendered inline."""

    DEFAULT_CSS = """
    ConfirmDialog {
        width: 60;
        height: auto;
        max-height: 14;
        border: double $primary;
        padding: 1 2;
        background: $surface;
        layer: dialog;
        dock: bottom;
    }
    ConfirmDialog .cd-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        margin-bottom: 1;
    }
    ConfirmDialog .cd-msg {
        width: 100%;
        margin-bottom: 1;
    }
    ConfirmDialog .cd-btns {
        align-horizontal: center;
        height: 3;
    }
    """

    class Confirmed(Message):
        def __init__(self, dialog_id: str) -> None:
            super().__init__()
            self.dialog_id = dialog_id

    class Cancelled(Message):
        def __init__(self, dialog_id: str) -> None:
            super().__init__()
            self.dialog_id = dialog_id

    def __init__(self, title: str, message: str, dialog_id: str = "confirm") -> None:
        super().__init__(id=dialog_id)
        self._title = title
        self._message = message
        self._dialog_id = dialog_id

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="cd-title")
        yield Label(self._message, classes="cd-msg")
        with Horizontal(classes="cd-btns"):
            yield Button("Yes", variant="success", id="cd-yes")
            yield Button("No", variant="error", id="cd-no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cd-yes":
            self.post_message(self.Confirmed(self._dialog_id))
        else:
            self.post_message(self.Cancelled(self._dialog_id))
        self.remove()


# ──────────────────────────────────────────────
#  Search / Replace Bar
# ──────────────────────────────────────────────

class SearchReplaceBar(Static):
    """Inline search and replace bar."""

    DEFAULT_CSS = """
    SearchReplaceBar {
        height: auto;
        max-height: 5;
        padding: 0 1;
        background: $surface-darken-1;
        display: none;
    }
    SearchReplaceBar.visible { display: block; }
    SearchReplaceBar Input { width: 1fr; margin: 0 1; }
    SearchReplaceBar Button { min-width: 10; }
    """

    class SearchRequested(Message):
        def __init__(self, query: str) -> None:
            super().__init__()
            self.query = query

    class ReplaceRequested(Message):
        def __init__(self, query: str, replacement: str) -> None:
            super().__init__()
            self.query = query
            self.replacement = replacement

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Input(placeholder="Find…", id="search-input")
            yield Button("Find", id="btn-find", variant="primary")
        with Horizontal():
            yield Input(placeholder="Replace with…", id="replace-input")
            yield Button("Replace All", id="btn-replace", variant="warning")
            yield Button("✕ Close", id="btn-close-search", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-find":
            query = self.query_one("#search-input", Input).value.strip()
            if query:
                self.post_message(self.SearchRequested(query))
        elif event.button.id == "btn-replace":
            query = self.query_one("#search-input", Input).value.strip()
            replacement = self.query_one("#replace-input", Input).value
            if query:
                self.post_message(self.ReplaceRequested(query, replacement))
        elif event.button.id == "btn-close-search":
            self.remove_class("visible")


# ──────────────────────────────────────────────
#  Go-To Line Dialog
# ──────────────────────────────────────────────

class GoToLineBar(Static):
    """Small inline bar to jump to a line number."""

    DEFAULT_CSS = """
    GoToLineBar {
        height: 3;
        padding: 0 1;
        background: $surface-darken-1;
        display: none;
    }
    GoToLineBar.visible { display: block; }
    GoToLineBar Input { width: 20; margin: 0 1; }
    """

    class GoTo(Message):
        def __init__(self, line: int) -> None:
            super().__init__()
            self.line = line

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Label("Go to line:")
            yield Input(placeholder="Line number", id="goto-input", type="integer")
            yield Button("Go", id="btn-goto", variant="primary")
            yield Button("✕", id="btn-close-goto", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-goto":
            self._submit()
        elif event.button.id == "btn-close-goto":
            self.remove_class("visible")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "goto-input":
            self._submit()

    def _submit(self) -> None:
        raw = self.query_one("#goto-input", Input).value.strip()
        if raw.isdigit():
            self.post_message(self.GoTo(int(raw)))
            self.remove_class("visible")


# ──────────────────────────────────────────────
#  File Editor Screen
# ──────────────────────────────────────────────

class FileEditorScreen(Screen):
    """
    Three-panel file editor screen.

    LEFT   = categorised file browser
    CENTER = text editor
    RIGHT  = properties / hints / validation
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", priority=True),
        Binding("ctrl+s", "save_file", "Save", priority=True),
        Binding("ctrl+z", "undo", "Undo"),
        Binding("ctrl+y", "redo", "Redo"),
        Binding("ctrl+f", "toggle_search", "Find/Replace"),
        Binding("ctrl+g", "toggle_goto", "Go to Line"),
        Binding("ctrl+w", "toggle_wrap", "Word Wrap"),
        Binding("ctrl+r", "toggle_readonly", "Read-Only"),
    ]

    DEFAULT_CSS = """
    FileEditorScreen {
        layout: horizontal;
    }

    /* ── Left: File Browser ─────────────── */
    #file-browser {
        width: 28;
        min-width: 24;
        border-right: solid $primary;
        padding: 0;
    }
    #file-browser-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        padding: 1;
        background: $primary;
        color: $text;
    }
    #file-tree {
        height: 1fr;
        padding: 0 1;
    }

    /* ── Center: Editor ─────────────────── */
    #editor-center {
        width: 1fr;
    }
    #editor-header {
        height: 3;
        padding: 0 2;
        background: $primary-darken-1;
    }
    #editor-filename {
        text-style: bold;
        width: 1fr;
    }
    #editor-cursor-pos {
        width: auto;
        min-width: 18;
        text-align: right;
    }
    #text-editor {
        height: 1fr;
    }
    #editor-action-bar {
        height: 3;
        padding: 0 1;
        background: $primary-darken-2;
    }
    #editor-action-bar Button {
        min-width: 14;
        margin: 0 1;
    }

    /* ── Right: Properties / Help ────────── */
    #props-panel {
        width: 32;
        min-width: 28;
        border-left: solid $primary;
        padding: 0;
    }
    #props-title {
        text-style: bold;
        text-align: center;
        width: 100%;
        padding: 1;
        background: $accent;
        color: $text;
    }
    #props-scroll {
        height: 1fr;
        padding: 1;
    }
    .props-section-title {
        text-style: bold;
        margin-top: 1;
        color: $secondary;
    }
    .props-hint {
        color: $text-muted;
        margin-left: 1;
    }
    .props-valid   { color: $success; text-style: bold; }
    .props-invalid { color: $error;   text-style: bold; }
    #quick-insert {
        margin-top: 1;
    }
    #quick-insert Button {
        width: 100%;
        margin: 0 0 1 0;
    }
    """

    # ── Reactive State ──────────────────────────

    current_file: reactive[Optional[str]] = reactive(None)
    is_modified: reactive[bool] = reactive(False)
    is_readonly: reactive[bool] = reactive(False)
    word_wrap: reactive[bool] = reactive(False)

    def __init__(self, server_dir: str) -> None:
        super().__init__()
        self.server_dir = server_dir
        self.editor = FileEditor(server_dir)
        self._original_content: str = ""
        self._backups_for_current: List[str] = []

    # ── Compose ─────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal():
            # ═══ LEFT: File Browser ═══
            with Vertical(id="file-browser"):
                yield Label("📁 Server Files", id="file-browser-title")
                yield Tree("server/", id="file-tree")

            # ═══ CENTER: Editor ═══
            with Vertical(id="editor-center"):
                # Editor header
                with Horizontal(id="editor-header"):
                    yield Label("No file open", id="editor-filename")
                    yield Label("Ln 1, Col 1", id="editor-cursor-pos")

                # Search / Replace bar (hidden by default)
                yield SearchReplaceBar(id="search-bar")

                # Go-to-line bar (hidden by default)
                yield GoToLineBar(id="goto-bar")

                # Main text area
                yield TextArea(
                    "",
                    id="text-editor",
                    show_line_numbers=True,
                    tab_size=4,
                    language="text",
                )

                # Bottom action bar
                with Horizontal(id="editor-action-bar"):
                    yield Button("💾 Save", id="btn-save", variant="primary")
                    yield Button("↩ Reset", id="btn-reset", variant="default")
                    yield Button("📦 Backup", id="btn-backup", variant="success")
                    yield Button("♻ Restore", id="btn-restore", variant="warning")
                    yield Button("🗑 Delete", id="btn-delete", variant="error")

            # ═══ RIGHT: Properties / Help ═══
            with Vertical(id="props-panel"):
                yield Label("📋 Properties & Help", id="props-title")
                with VerticalScroll(id="props-scroll"):
                    # File info section
                    yield Label("📄 File Info", classes="props-section-title")
                    yield Label("No file selected", id="props-file-info")

                    # Validation section
                    yield Label("✅ Validation", classes="props-section-title")
                    yield Label("—", id="props-validation")

                    # Syntax hints
                    yield Label("💡 Syntax Hints", classes="props-section-title")
                    yield Label("Open a file to see hints", id="props-hints")

                    # Property descriptions (for server.properties)
                    yield Label("📖 Property Docs", classes="props-section-title", id="props-docs-title")
                    yield Static("", id="props-docs")

                    # Quick insert
                    yield Label("⚡ Quick Insert", classes="props-section-title", id="quick-insert-title")
                    with Vertical(id="quick-insert"):
                        yield Button("gamemode=survival", id="qi-gamemode")
                        yield Button("difficulty=normal", id="qi-difficulty")
                        yield Button("max-players=20", id="qi-maxplayers")
                        yield Button("pvp=true", id="qi-pvp")
                        yield Button("online-mode=true", id="qi-online")

        yield Footer()

    # ── Mount ───────────────────────────────────

    def on_mount(self) -> None:
        self._populate_file_tree()
        # Hide quick-insert & docs sections initially
        self._set_quick_insert_visible(False)

    # ── File Tree Population ────────────────────

    def _populate_file_tree(self) -> None:
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        tree.root.expand()

        all_files = self.editor.list_editable_files()
        name_to_info: Dict[str, FileInfo] = {f.name: f for f in all_files}

        # Build categorised branches
        plugin_configs: List[FileInfo] = []

        for category, filenames in FILE_CATEGORIES.items():
            if category == "🔌 Plugin Configs":
                continue  # handled below

            branch = tree.root.add(category)

            for fname in filenames:
                info = name_to_info.pop(fname, None)
                if info is not None:
                    size_str = self._human_size(info.size_bytes)
                    node = branch.add_leaf(f"{fname}  ({size_str})")
                    node.data = info

        # Plugin configs – everything left that lives under plugins/
        plugins_branch = tree.root.add("🔌 Plugin Configs")
        for info in all_files:
            path_lower = info.path.replace("\\", "/").lower()
            if "/plugins/" in path_lower and info.name in name_to_info:
                size_str = self._human_size(info.size_bytes)
                node = plugins_branch.add_leaf(f"{info.name}  ({size_str})")
                node.data = info
                name_to_info.pop(info.name, None)

        # Anything remaining goes into an "Other" category
        if name_to_info:
            other_branch = tree.root.add("📄 Other Files")
            for info in name_to_info.values():
                size_str = self._human_size(info.size_bytes)
                node = other_branch.add_leaf(f"{info.name}  ({size_str})")
                node.data = info

    # ── Tree Events ─────────────────────────────

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        node = event.node
        if node.data and isinstance(node.data, FileInfo):
            self._open_file(node.data)

    # ── Open / Load File ────────────────────────

    def _open_file(self, info: FileInfo) -> None:
        if self.is_modified:
            # Ask to save first – mount a confirm dialog
            dialog = ConfirmDialog(
                "Unsaved Changes",
                f"'{self._current_name()}' has unsaved changes.\nDiscard and open new file?",
                dialog_id="confirm-discard",
            )
            dialog._pending_info = info  # type: ignore[attr-defined]
            self.mount(dialog)
            return

        self._load_file(info)

    def _load_file(self, info: FileInfo) -> None:
        content = self.editor.read_file(info.path)
        self._original_content = content
        self.current_file = info.path

        # Configure editor
        text_area = self.query_one("#text-editor", TextArea)
        text_area.load_text(content)
        text_area.read_only = self.is_readonly

        # Set syntax language
        lang = self._language_for_file(info.name)
        try:
            text_area.language = lang
        except Exception:
            text_area.language = None

        self.is_modified = False

        # Update header
        self.query_one("#editor-filename", Label).update(
            f"📝 {info.name}"
        )

        # Update right panel
        self._update_file_info(info)
        self._update_syntax_hints(info)
        self._update_validation(content, info.path)
        self._update_property_docs(info.name)

        self.notify(f"Opened {info.name}")

    # ── Text Change Detection ───────────────────

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "text-editor":
            current = event.text_area.text
            self.is_modified = current != self._original_content

            # Update header with modified indicator
            name = self._current_name()
            marker = " *" if self.is_modified else ""
            self.query_one("#editor-filename", Label).update(
                f"📝 {name}{marker}"
            )

            # Live validation
            if self.current_file:
                self._update_validation(current, self.current_file)

    def on_text_area_selection_changed(self, event) -> None:
        """Update cursor position display."""
        try:
            ta = self.query_one("#text-editor", TextArea)
            cursor = ta.cursor_location
            line = cursor[0] + 1
            col = cursor[1] + 1
            self.query_one("#editor-cursor-pos", Label).update(
                f"Ln {line}, Col {col}"
            )
        except Exception:
            pass

    # ── Button Handlers ─────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn = event.button.id or ""

        if btn == "btn-save":
            self.action_save_file()
        elif btn == "btn-reset":
            self._reset_file()
        elif btn == "btn-backup":
            self._create_backup()
        elif btn == "btn-restore":
            self._show_restore_options()
        elif btn == "btn-delete":
            self._confirm_delete()
        elif btn.startswith("qi-"):
            self._quick_insert(btn)
        elif btn.startswith("restore-"):
            self._do_restore(btn)

    # ── Confirm Dialog Handling ─────────────────

    def on_confirm_dialog_confirmed(self, event: ConfirmDialog.Confirmed) -> None:
        if event.dialog_id == "confirm-discard":
            # Find the pending info and load
            for child in self.query(ConfirmDialog):
                if hasattr(child, "_pending_info"):
                    self.is_modified = False
                    self._load_file(child._pending_info)
                    break
        elif event.dialog_id == "confirm-delete":
            self._do_delete()

    def on_confirm_dialog_cancelled(self, event: ConfirmDialog.Cancelled) -> None:
        pass  # dialog removes itself

    # ── Search / Replace ────────────────────────

    def on_search_replace_bar_search_requested(
        self, event: SearchReplaceBar.SearchRequested
    ) -> None:
        ta = self.query_one("#text-editor", TextArea)
        content = ta.text
        query = event.query
        count = content.lower().count(query.lower())
        if count:
            self.notify(f"Found {count} match(es) for '{query}'")
        else:
            self.notify(f"No matches for '{query}'", severity="warning")

    def on_search_replace_bar_replace_requested(
        self, event: SearchReplaceBar.ReplaceRequested
    ) -> None:
        ta = self.query_one("#text-editor", TextArea)
        old = ta.text
        new = old.replace(event.query, event.replacement)
        count = old.count(event.query)

        if count:
            ta.load_text(new)
            self.notify(f"Replaced {count} occurrence(s)")
        else:
            self.notify("No matches found", severity="warning")

    # ── Go To Line ──────────────────────────────

    def on_go_to_line_bar_go_to(self, event: GoToLineBar.GoTo) -> None:
        ta = self.query_one("#text-editor", TextArea)
        line_idx = max(0, event.line - 1)
        try:
            ta.move_cursor((line_idx, 0))
            ta.scroll_cursor_visible()
            self.notify(f"Jumped to line {event.line}")
        except Exception:
            self.notify("Invalid line number", severity="warning")

    # ── Actions (keyboard shortcuts) ────────────

    def action_save_file(self) -> None:
        if not self.current_file:
            self.notify("No file open", severity="warning")
            return
        if self.is_readonly:
            self.notify("File is read-only", severity="warning")
            return

        ta = self.query_one("#text-editor", TextArea)
        content = ta.text

        # Validate first
        validation = self.editor.validate_file_content(self.current_file, content)
        if not validation.success:
            self.notify(
                f"⚠ Validation warnings: {validation.error}\nSaving anyway…",
                severity="warning",
            )

        result = self.editor.write_file(self.current_file, content)

        if result.success:
            self._original_content = content
            self.is_modified = False
            backup = result.details.get("backup_path", "")
            msg = f"✅ Saved {self._current_name()}"
            if backup:
                msg += f"\n  Backup: {Path(backup).name}"
            self.notify(msg)

            # Refresh header
            self.query_one("#editor-filename", Label).update(
                f"📝 {self._current_name()}"
            )

            # Refresh file info & validation
            info = self.editor.get_file_properties(self.current_file)
            self._update_file_info(info)
            self._update_validation(content, self.current_file)
        else:
            self.notify(f"❌ Save failed: {result.error}", severity="error")

    def action_undo(self) -> None:
        ta = self.query_one("#text-editor", TextArea)
        ta.action_undo()

    def action_redo(self) -> None:
        ta = self.query_one("#text-editor", TextArea)
        ta.action_redo()

    def action_toggle_search(self) -> None:
        bar = self.query_one("#search-bar", SearchReplaceBar)
        bar.toggle_class("visible")
        if bar.has_class("visible"):
            try:
                bar.query_one("#search-input", Input).focus()
            except Exception:
                pass

    def action_toggle_goto(self) -> None:
        bar = self.query_one("#goto-bar", GoToLineBar)
        bar.toggle_class("visible")
        if bar.has_class("visible"):
            try:
                bar.query_one("#goto-input", Input).focus()
            except Exception:
                pass

    def action_toggle_wrap(self) -> None:
        self.word_wrap = not self.word_wrap
        ta = self.query_one("#text-editor", TextArea)
        ta.soft_wrap = self.word_wrap
        state = "ON" if self.word_wrap else "OFF"
        self.notify(f"Word wrap: {state}")

    def action_toggle_readonly(self) -> None:
        self.is_readonly = not self.is_readonly
        ta = self.query_one("#text-editor", TextArea)
        ta.read_only = self.is_readonly
        state = "ON 🔒" if self.is_readonly else "OFF ✏️"
        self.notify(f"Read-only: {state}")

    # ── Reset (discard changes) ─────────────────

    def _reset_file(self) -> None:
        if not self.current_file:
            self.notify("No file open", severity="warning")
            return

        ta = self.query_one("#text-editor", TextArea)
        ta.load_text(self._original_content)
        self.is_modified = False
        self.query_one("#editor-filename", Label).update(
            f"📝 {self._current_name()}"
        )
        self.notify("Changes discarded")

    # ── Backup ──────────────────────────────────

    def _create_backup(self) -> None:
        if not self.current_file:
            self.notify("No file open", severity="warning")
            return
        try:
            backup_path = self.editor.create_backup(self.current_file)
            self.notify(f"📦 Backup created:\n  {Path(backup_path).name}")
        except Exception as exc:
            self.notify(f"Backup failed: {exc}", severity="error")

    # ── Restore ─────────────────────────────────

    def _show_restore_options(self) -> None:
        if not self.current_file:
            self.notify("No file open", severity="warning")
            return

        # Find backups for current file
        current_name = Path(self.current_file).name
        backups = sorted(
            self.editor.backup_dir.glob(f"{current_name}.*.backup"),
            reverse=True,
        )

        if not backups:
            self.notify("No backups found for this file", severity="warning")
            return

        self._backups_for_current = [str(b) for b in backups[:10]]

        # Mount a selection list
        items = "\n".join(
            f"  {i+1}. {Path(b).name}" for i, b in enumerate(self._backups_for_current)
        )
        self.notify(f"Available backups:\n{items}\n\nType backup number in console to restore.")

        # For simplicity, restore latest backup
        dialog = ConfirmDialog(
            "Restore Backup",
            f"Restore from latest backup?\n{Path(backups[0]).name}",
            dialog_id="confirm-restore",
        )
        self.mount(dialog)

    def _do_restore(self, btn_id: str) -> None:
        pass  # handled via confirm dialog

    def on_confirm_dialog_confirmed_restore(self, event: ConfirmDialog.Confirmed) -> None:
        if event.dialog_id == "confirm-restore" and self._backups_for_current:
            result = self.editor.restore_backup(
                self.current_file, self._backups_for_current[0]
            )
            if result.success:
                content = self.editor.read_file(self.current_file)
                self._original_content = content
                ta = self.query_one("#text-editor", TextArea)
                ta.load_text(content)
                self.is_modified = False
                self.notify("✅ File restored from backup")
            else:
                self.notify(f"Restore failed: {result.error}", severity="error")

    # ── Delete ──────────────────────────────────

    def _confirm_delete(self) -> None:
        if not self.current_file:
            self.notify("No file open", severity="warning")
            return

        dialog = ConfirmDialog(
            "⚠️  Delete File",
            f"Permanently delete {self._current_name()}?\nA backup will be created first.",
            dialog_id="confirm-delete",
        )
        self.mount(dialog)

    def _do_delete(self) -> None:
        if not self.current_file:
            return
        try:
            # Backup first
            self.editor.create_backup(self.current_file)
            Path(self.current_file).unlink()
            self.notify(f"🗑 Deleted {self._current_name()} (backup saved)")

            # Clear editor
            self.current_file = None
            self._original_content = ""
            self.is_modified = False
            ta = self.query_one("#text-editor", TextArea)
            ta.load_text("")
            self.query_one("#editor-filename", Label).update("No file open")

            # Refresh tree
            self._populate_file_tree()
        except Exception as exc:
            self.notify(f"Delete failed: {exc}", severity="error")

    # ── Quick Insert ────────────────────────────

    def _quick_insert(self, btn_id: str) -> None:
        inserts = {
            "qi-gamemode": "gamemode=survival",
            "qi-difficulty": "difficulty=normal",
            "qi-maxplayers": "max-players=20",
            "qi-pvp": "pvp=true",
            "qi-online": "online-mode=true",
        }
        text = inserts.get(btn_id, "")
        if text:
            ta = self.query_one("#text-editor", TextArea)
            ta.insert(text + "\n")
            self.notify(f"Inserted: {text}")

    # ── Right Panel Updates ─────────────────────

    def _update_file_info(self, info: FileInfo) -> None:
        size = self._human_size(info.size_bytes)
        modified = info.last_modified[:19] if info.last_modified not in ("N/A", "ERROR") else info.last_modified
        perms = info.permissions
        encoding = info.encoding
        ftype = info.file_type

        text = (
            f"Name:     {info.name}\n"
            f"Size:     {size}\n"
            f"Modified: {modified}\n"
            f"Type:     {ftype}\n"
            f"Encoding: {encoding}\n"
            f"Access:   {perms}\n"
            f"Path:     …/{Path(info.path).relative_to(self.server_dir)}"
        )
        self.query_one("#props-file-info", Label).update(text)

    def _update_syntax_hints(self, info: FileInfo) -> None:
        hints_data = self.editor.get_file_syntax_hints(info.path)
        lines = []

        desc = hints_data.get("description", "")
        if desc:
            lines.append(desc)
            lines.append("")

        for hint in hints_data.get("hints", []):
            lines.append(f"  • {hint}")

        examples = hints_data.get("examples", [])
        if examples:
            lines.append("")
            lines.append("Examples:")
            for ex in examples:
                lines.append(f"  {ex}")

        self.query_one("#props-hints", Label).update("\n".join(lines) or "No hints available")

    def _update_validation(self, content: str, file_path: str) -> None:
        result = self.editor.validate_file_content(file_path, content)
        lbl = self.query_one("#props-validation", Label)

        if result.success:
            lbl.update(f"✅ {result.message}")
            lbl.remove_class("props-invalid")
            lbl.add_class("props-valid")
        else:
            error_text = result.error or "Unknown error"
            lbl.update(f"❌ {result.message}\n   {error_text}")
            lbl.remove_class("props-valid")
            lbl.add_class("props-invalid")

    def _update_property_docs(self, filename: str) -> None:
        docs_title = self.query_one("#props-docs-title", Label)
        docs_widget = self.query_one("#props-docs", Static)

        if filename.lower() == "server.properties":
            docs_title.display = True
            docs_widget.display = True
            self._set_quick_insert_visible(True)

            lines = []
            for key, desc in PROPERTY_DESCRIPTIONS.items():
                lines.append(f"[bold]{key}[/bold]")
                lines.append(f"  {desc}")
                lines.append("")
            docs_widget.update("\n".join(lines))
        else:
            docs_title.display = False
            docs_widget.display = False
            self._set_quick_insert_visible(False)

    def _set_quick_insert_visible(self, visible: bool) -> None:
        try:
            self.query_one("#quick-insert-title", Label).display = visible
            self.query_one("#quick-insert", Vertical).display = visible
        except Exception:
            pass

    # ── Helpers ──────────────────────────────────

    def _current_name(self) -> str:
        if self.current_file:
            return Path(self.current_file).name
        return "untitled"

    @staticmethod
    def _human_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"

    @staticmethod
    def _language_for_file(filename: str) -> Optional[str]:
        ext = Path(filename).suffix.lower()
        lang_map = {
            ".properties": None,       # no built-in Textual language
            ".json": "json",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".txt": None,
            ".toml": "toml",
            ".py": "python",
            ".cfg": None,
        }
        return lang_map.get(ext, None)
