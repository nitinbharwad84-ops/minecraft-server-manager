"""
file_editor.py
==============
Comprehensive file editing system for Minecraft server configuration files.

Supports editing, validation, backup/restore for:
  - server.properties (key=value format)
  - YAML files (spigot.yml, bukkit.yml, paper-global.yml)
  - JSON files (ops.json, whitelist.json, banned-players.json)
  - Text files (eula.txt, motd.txt)
  - Plugin configs
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Result Objects
# ──────────────────────────────────────────────

@dataclass
class FileResult:
    """Result object for file operations."""
    success: bool
    message: str
    error: Optional[str] = None
    details: Dict = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str, **details) -> "FileResult":
        """Create a successful result."""
        return cls(success=True, message=message, details=details)

    @classmethod
    def fail(cls, message: str, error: Optional[str] = None, **details) -> "FileResult":
        """Create a failed result."""
        return cls(success=False, message=message, error=error, details=details)


@dataclass
class FileInfo:
    """Detailed file metadata."""
    path: str
    name: str
    size_bytes: int
    last_modified: str
    permissions: str
    encoding: str
    file_type: str
    is_readable: bool
    is_writable: bool
    exists: bool


# ──────────────────────────────────────────────
#  File Editor Class
# ──────────────────────────────────────────────

class FileEditor:
    """
    Comprehensive file editor for Minecraft server files.

    Handles reading, writing, validation, backup, and restore operations.
    """

    # Known editable files in server root
    KNOWN_FILES = {
        "server.properties": "Server configuration",
        "bukkit.yml": "Bukkit configuration (Paper/Spigot)",
        "spigot.yml": "Spigot configuration",
        "paper.yml": "Paper legacy configuration",
        "paper-global.yml": "Paper global configuration",
        "paper-world-defaults.yml": "Paper world defaults",
        "eula.txt": "Minecraft EULA",
        "ops.json": "Server operators list",
        "whitelist.json": "Whitelisted players",
        "banned-players.json": "Banned players list",
        "banned-ips.json": "Banned IP addresses",
        "usercache.json": "User cache",
        "server-icon.png": "Server icon (64x64)",
    }

    def __init__(self, server_dir: str | Path, backup_dir: Optional[str | Path] = None) -> None:
        """
        Initialize the file editor.

        Args:
            server_dir: Path to the server directory
            backup_dir: Path to store backups (default: server_dir/backups/file_edits)
        """
        self.server_dir = Path(server_dir)
        self.backup_dir = Path(backup_dir) if backup_dir else self.server_dir / "backups" / "file_edits"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    # ── 1. List Editable Files ──────────────────

    def list_editable_files(self) -> List[FileInfo]:
        """
        List all editable files in the server directory.

        Returns:
            List of FileInfo objects for each editable file
        """
        files: List[FileInfo] = []

        if not self.server_dir.exists():
            logger.warning("Server directory does not exist: %s", self.server_dir)
            return files

        # Root-level known files
        for filename in self.KNOWN_FILES.keys():
            file_path = self.server_dir / filename
            if file_path.exists():
                files.append(self.get_file_properties(str(file_path)))

        # Plugin config files
        plugins_dir = self.server_dir / "plugins"
        if plugins_dir.exists():
            for item in plugins_dir.rglob("*.yml"):
                if item.is_file() and "config" in item.name.lower():
                    files.append(self.get_file_properties(str(item)))

            for item in plugins_dir.rglob("config.yml"):
                if item.is_file():
                    files.append(self.get_file_properties(str(item)))

        # Additional config directories
        for config_dir in ["config", "configs"]:
            config_path = self.server_dir / config_dir
            if config_path.exists():
                for ext in ["*.yml", "*.yaml", "*.properties", "*.json", "*.txt"]:
                    for item in config_path.rglob(ext):
                        if item.is_file():
                            files.append(self.get_file_properties(str(item)))

        return files

    # ── 2. Read File ────────────────────────────

    def read_file(self, file_path: str | Path) -> str:
        """
        Safely read file content.

        Handles text and binary files, with encoding detection.

        Args:
            file_path: Path to the file

        Returns:
            File content as string, or error message
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return f"# ERROR: File not found: {file_path}"

        # Check if binary file
        if file_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".jar", ".zip"}:
            return f"# BINARY FILE: {file_path.name} ({file_path.stat().st_size} bytes)\n# Cannot display binary content."

        try:
            # Try UTF-8 first
            encoding = self._detect_encoding(file_path)
            content = file_path.read_text(encoding=encoding)
            logger.info("Read %d bytes from %s (encoding: %s)", len(content), file_path, encoding)
            return content

        except OSError as exc:
            error_msg = f"# ERROR: Cannot read file: {exc}"
            logger.error("Failed to read %s: %s", file_path, exc)
            return error_msg
        except Exception as exc:
            error_msg = f"# ERROR: Unexpected error: {exc}"
            logger.error("Unexpected error reading %s: %s", file_path, exc)
            return error_msg

    # ── 3. Write File ───────────────────────────

    def write_file(self, file_path: str | Path, content: str) -> FileResult:
        """
        Write content to a file with automatic backup.

        Args:
            file_path: Path to the file
            content: Content to write

        Returns:
            FileResult with operation status
        """
        file_path = Path(file_path)

        try:
            # Create backup if file exists
            backup_path = None
            if file_path.exists():
                backup_path = self.create_backup(str(file_path))
                logger.info("Created backup: %s", backup_path)

            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the file
            encoding = self._detect_encoding(file_path) if file_path.exists() else "utf-8"
            file_path.write_text(content, encoding=encoding)

            # Verify write
            if not file_path.exists():
                return FileResult.fail(
                    "Write verification failed",
                    error="File does not exist after write",
                    path=str(file_path),
                )

            written_size = file_path.stat().st_size
            logger.info("Wrote %d bytes to %s", written_size, file_path)

            return FileResult.ok(
                "File written successfully",
                path=str(file_path),
                size_bytes=written_size,
                backup_path=backup_path,
                encoding=encoding,
            )

        except OSError as exc:
            return FileResult.fail(
                "Failed to write file",
                error=str(exc),
                path=str(file_path),
            )
        except Exception as exc:
            return FileResult.fail(
                "Unexpected error during write",
                error=str(exc),
                path=str(file_path),
            )

    # ── 4. Get File Properties ──────────────────

    def get_file_properties(self, file_path: str | Path) -> FileInfo:
        """
        Get detailed file metadata.

        Args:
            file_path: Path to the file

        Returns:
            FileInfo object with detailed metadata
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return FileInfo(
                path=str(file_path),
                name=file_path.name,
                size_bytes=0,
                last_modified="N/A",
                permissions="N/A",
                encoding="unknown",
                file_type="unknown",
                is_readable=False,
                is_writable=False,
                exists=False,
            )

        try:
            stat = file_path.stat()
            last_modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

            # Check permissions
            is_readable = os.access(file_path, os.R_OK)
            is_writable = os.access(file_path, os.W_OK)

            # Get file type
            file_type = self._detect_file_type(file_path)

            # Get encoding
            encoding = self._detect_encoding(file_path) if is_readable else "unknown"

            # Format permissions (simplified)
            perms = f"r{'w' if is_writable else '-'}"

            return FileInfo(
                path=str(file_path),
                name=file_path.name,
                size_bytes=stat.st_size,
                last_modified=last_modified,
                permissions=perms,
                encoding=encoding,
                file_type=file_type,
                is_readable=is_readable,
                is_writable=is_writable,
                exists=True,
            )

        except OSError as exc:
            logger.error("Failed to get properties for %s: %s", file_path, exc)
            return FileInfo(
                path=str(file_path),
                name=file_path.name,
                size_bytes=0,
                last_modified="ERROR",
                permissions="ERROR",
                encoding="unknown",
                file_type="unknown",
                is_readable=False,
                is_writable=False,
                exists=True,
            )

    # ── 5. Validate File Content ────────────────

    def validate_file_content(self, file_path: str | Path, content: str) -> FileResult:
        """
        Validate file content based on file type.

        Args:
            file_path: Path to the file (used to detect type)
            content: Content to validate

        Returns:
            FileResult with validation status
        """
        file_path = Path(file_path)
        file_type = self._detect_file_type(file_path)

        try:
            if file_type == "properties":
                return self._validate_properties(content)
            elif file_type == "json":
                return self._validate_json(content)
            elif file_type == "yaml":
                return self._validate_yaml(content)
            else:
                return FileResult.ok("No validation needed for this file type", file_type=file_type)

        except Exception as exc:
            return FileResult.fail(
                "Validation error",
                error=str(exc),
                file_type=file_type,
            )

    # ── 6. Create Backup ────────────────────────

    def create_backup(self, file_path: str | Path) -> str:
        """
        Create a timestamped backup of a file.

        Args:
            file_path: Path to the file to backup

        Returns:
            Path to the backup file
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = f"{file_path.name}.{timestamp}.backup"
        backup_path = self.backup_dir / backup_name

        try:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)
            logger.info("Created backup: %s -> %s", file_path, backup_path)
            return str(backup_path)

        except OSError as exc:
            logger.error("Failed to create backup: %s", exc)
            raise

    # ── 7. Restore Backup ───────────────────────

    def restore_backup(self, original_path: str | Path, backup_path: str | Path) -> FileResult:
        """
        Restore a file from a backup.

        Args:
            original_path: Path where the file should be restored
            backup_path: Path to the backup file

        Returns:
            FileResult with restoration status
        """
        original_path = Path(original_path)
        backup_path = Path(backup_path)

        if not backup_path.exists():
            return FileResult.fail(
                "Backup file not found",
                error=f"Backup does not exist: {backup_path}",
            )

        try:
            # Create backup of current file if it exists
            pre_restore_backup = None
            if original_path.exists():
                pre_restore_backup = self.create_backup(str(original_path))

            # Restore from backup
            original_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup_path, original_path)

            # Verify
            if not original_path.exists():
                return FileResult.fail(
                    "Restoration verification failed",
                    error="File does not exist after restore",
                )

            logger.info("Restored %s from %s", original_path, backup_path)

            return FileResult.ok(
                "File restored successfully",
                original_path=str(original_path),
                backup_path=str(backup_path),
                pre_restore_backup=pre_restore_backup,
            )

        except OSError as exc:
            return FileResult.fail(
                "Failed to restore backup",
                error=str(exc),
                original_path=str(original_path),
                backup_path=str(backup_path),
            )

    # ── 8. Get File Syntax Hints ────────────────

    def get_file_syntax_hints(self, file_path: str | Path) -> Dict:
        """
        Get syntax hints and examples for a file type.

        Args:
            file_path: Path to the file

        Returns:
            Dictionary with hints, examples, and valid keys
        """
        file_path = Path(file_path)
        file_type = self._detect_file_type(file_path)
        filename = file_path.name.lower()

        if filename == "server.properties":
            return self._get_server_properties_hints()
        elif filename in ("ops.json", "whitelist.json", "banned-players.json"):
            return self._get_json_hints(filename)
        elif file_type == "yaml":
            return self._get_yaml_hints()
        elif file_type == "properties":
            return self._get_properties_hints()
        elif file_type == "json":
            return self._get_json_hints("generic")
        else:
            return {"hints": ["Plain text file - no special syntax"], "examples": []}

    # ── Private Helper Methods ──────────────────

    @staticmethod
    def _detect_encoding(file_path: Path) -> str:
        """Detect file encoding (UTF-8 or fallback to latin-1)."""
        try:
            file_path.read_text(encoding="utf-8")
            return "utf-8"
        except UnicodeDecodeError:
            return "latin-1"

    @staticmethod
    def _detect_file_type(file_path: Path) -> str:
        """Detect file type from extension."""
        ext = file_path.suffix.lower()
        type_map = {
            ".properties": "properties",
            ".yml": "yaml",
            ".yaml": "yaml",
            ".json": "json",
            ".txt": "text",
            ".png": "binary",
            ".jar": "binary",
        }
        return type_map.get(ext, "text")

    @staticmethod
    def _validate_properties(content: str) -> FileResult:
        """Validate .properties file format."""
        errors = []
        line_num = 0

        for line in content.splitlines():
            line_num += 1
            stripped = line.strip()

            # Skip empty lines and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Check for key=value format
            if "=" not in stripped:
                errors.append(f"Line {line_num}: Missing '=' separator: {stripped[:50]}")
                continue

            key, _, value = stripped.partition("=")
            if not key.strip():
                errors.append(f"Line {line_num}: Empty key")

        if errors:
            return FileResult.fail(
                "Properties validation failed",
                error="; ".join(errors[:5]),  # Show first 5 errors
                total_errors=len(errors),
            )

        return FileResult.ok("Properties file is valid", lines_checked=line_num)

    @staticmethod
    def _validate_json(content: str) -> FileResult:
        """Validate JSON syntax."""
        try:
            json.loads(content)
            return FileResult.ok("JSON is valid")
        except json.JSONDecodeError as exc:
            return FileResult.fail(
                "JSON validation failed",
                error=f"Line {exc.lineno}, Column {exc.colno}: {exc.msg}",
            )

    @staticmethod
    def _validate_yaml(content: str) -> FileResult:
        """Validate YAML syntax (basic check)."""
        try:
            # Basic YAML validation without PyYAML dependency
            # Check for common syntax errors
            errors = []
            for i, line in enumerate(content.splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("-") and ":" not in stripped:
                    # List item should have content
                    if len(stripped) <= 2:
                        errors.append(f"Line {i}: Empty list item")

            if errors:
                return FileResult.fail(
                    "YAML validation failed",
                    error="; ".join(errors[:3]),
                )

            return FileResult.ok("YAML appears valid (basic check)")

        except Exception as exc:
            return FileResult.fail("YAML validation error", error=str(exc))

    @staticmethod
    def _get_server_properties_hints() -> Dict:
        """Get hints for server.properties."""
        return {
            "description": "Minecraft server configuration file (key=value format)",
            "hints": [
                "Format: key=value (no spaces around =)",
                "Comments start with #",
                "Boolean values: true or false (lowercase)",
                "Number values: integers only",
            ],
            "valid_keys": [
                "server-port", "gamemode", "difficulty", "max-players", "pvp",
                "online-mode", "level-name", "motd", "view-distance",
                "simulation-distance", "spawn-protection", "enable-command-block",
                "allow-flight", "white-list", "max-world-size", "hardcore",
            ],
            "examples": [
                "max-players=20",
                "gamemode=survival",
                "difficulty=normal",
                "pvp=true",
                "motd=A Minecraft Server",
            ],
        }

    @staticmethod
    def _get_json_hints(filename: str) -> Dict:
        """Get hints for JSON files."""
        base = {
            "description": "JSON configuration file",
            "hints": [
                "Valid JSON syntax required",
                "Use double quotes for strings",
                "No trailing commas",
                "Boolean values: true or false (lowercase)",
            ],
        }

        if filename == "ops.json":
            base["examples"] = [
                '{',
                '  "uuid": "069a79f4-44e9-4726-a5be-fca90e38aaf5",',
                '  "name": "PlayerName",',
                '  "level": 4,',
                '  "bypassesPlayerLimit": false',
                '}',
            ]
        elif filename == "whitelist.json":
            base["examples"] = [
                '{',
                '  "uuid": "069a79f4-44e9-4726-a5be-fca90e38aaf5",',
                '  "name": "PlayerName"',
                '}',
            ]
        elif filename == "banned-players.json":
            base["examples"] = [
                '{',
                '  "uuid": "069a79f4-44e9-4726-a5be-fca90e38aaf5",',
                '  "name": "PlayerName",',
                '  "created": "2024-01-01 12:00:00 +0000",',
                '  "source": "Server",',
                '  "expires": "forever",',
                '  "reason": "Banned by an operator"',
                '}',
            ]
        else:
            base["examples"] = ['{"key": "value"}']

        return base

    @staticmethod
    def _get_yaml_hints() -> Dict:
        """Get hints for YAML files."""
        return {
            "description": "YAML configuration file",
            "hints": [
                "Indentation matters (use spaces, not tabs)",
                "Key-value pairs: key: value",
                "Lists start with -",
                "Comments start with #",
                "Boolean values: true or false",
            ],
            "examples": [
                "settings:",
                "  debug: false",
                "  max-players: 20",
                "worlds:",
                "  - world",
                "  - world_nether",
            ],
        }

    @staticmethod
    def _get_properties_hints() -> Dict:
        """Get generic hints for .properties files."""
        return {
            "description": "Configuration file (key=value format)",
            "hints": [
                "Format: key=value",
                "No spaces around =",
                "Comments start with #",
            ],
            "examples": [
                "setting=value",
                "enabled=true",
                "# This is a comment",
            ],
        }


# ──────────────────────────────────────────────
#  Convenience Functions
# ──────────────────────────────────────────────

def list_editable_files(server_dir: str | Path) -> List[FileInfo]:
    """
    Convenience function to list editable files.

    Args:
        server_dir: Path to server directory

    Returns:
        List of FileInfo objects
    """
    editor = FileEditor(server_dir)
    return editor.list_editable_files()
