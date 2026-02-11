"""
plugin_validator.py
===================
Validates plugin compatibility with the current server configuration.

Checks:
  - Minecraft version compatibility
  - Server software compatibility (Paper vs Fabric vs Forge, etc.)
  - Plugin file integrity (valid JAR structure)
  - Dependency resolution (warns about missing dependencies)
  - Duplicate plugin detection
"""

from __future__ import annotations

import logging
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml  # PyYAML fallback — pydantic handles most validation

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Validation Results
# ──────────────────────────────────────────────

@dataclass
class ValidationIssue:
    """A single validation issue found during plugin checking."""
    severity: str  # "error", "warning", "info"
    message: str
    field: str = ""


@dataclass
class ValidationResult:
    """Aggregated result of all validation checks on a plugin."""
    plugin_name: str
    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)

    def add_error(self, message: str, field_name: str = "") -> None:
        self.issues.append(ValidationIssue("error", message, field_name))
        self.is_valid = False

    def add_warning(self, message: str, field_name: str = "") -> None:
        self.issues.append(ValidationIssue("warning", message, field_name))

    def add_info(self, message: str, field_name: str = "") -> None:
        self.issues.append(ValidationIssue("info", message, field_name))


# ──────────────────────────────────────────────
#  Plugin Metadata Extraction
# ──────────────────────────────────────────────

@dataclass
class PluginMeta:
    """Extracted metadata from a plugin JAR file."""
    name: str = "Unknown"
    version: str = "Unknown"
    main_class: str = ""
    api_version: Optional[str] = None
    description: str = ""
    authors: list[str] = field(default_factory=list)
    depend: list[str] = field(default_factory=list)      # Hard dependencies
    soft_depend: list[str] = field(default_factory=list)  # Soft dependencies
    load_before: list[str] = field(default_factory=list)
    plugin_type: str = "bukkit"  # bukkit, fabric, forge


def extract_plugin_meta(jar_path: str | Path) -> Optional[PluginMeta]:
    """
    Extract plugin metadata from a JAR file.

    Checks for:
      - ``plugin.yml``      → Bukkit/Spigot/Paper plugin
      - ``bungee.yml``      → BungeeCord plugin
      - ``velocity-plugin.json`` → Velocity plugin
      - ``fabric.mod.json`` → Fabric mod
      - ``META-INF/mods.toml``   → Forge mod
    """
    jar_path = Path(jar_path)
    if not jar_path.exists() or not jar_path.suffix == ".jar":
        return None

    try:
        with zipfile.ZipFile(jar_path, "r") as zf:
            names = zf.namelist()

            # Bukkit / Paper / Spigot
            if "plugin.yml" in names:
                return _parse_bukkit_yml(zf.read("plugin.yml").decode("utf-8"))

            # BungeeCord
            if "bungee.yml" in names:
                return _parse_bukkit_yml(zf.read("bungee.yml").decode("utf-8"), plugin_type="bungeecord")

            # Velocity
            if "velocity-plugin.json" in names:
                import json
                data = json.loads(zf.read("velocity-plugin.json"))
                return PluginMeta(
                    name=data.get("id", "Unknown"),
                    version=data.get("version", "Unknown"),
                    main_class=data.get("main", ""),
                    description=data.get("description", ""),
                    authors=data.get("authors", []),
                    plugin_type="velocity",
                )

            # Fabric
            if "fabric.mod.json" in names:
                import json
                data = json.loads(zf.read("fabric.mod.json"))
                return PluginMeta(
                    name=data.get("name", data.get("id", "Unknown")),
                    version=data.get("version", "Unknown"),
                    main_class=data.get("entrypoints", {}).get("main", [""])[0]
                    if isinstance(data.get("entrypoints", {}).get("main"), list) else "",
                    description=data.get("description", ""),
                    authors=[a if isinstance(a, str) else a.get("name", "")
                             for a in data.get("authors", [])],
                    plugin_type="fabric",
                )

            # Forge (mods.toml)
            for name in names:
                if name.endswith("mods.toml"):
                    return PluginMeta(name="Forge Mod", plugin_type="forge")

    except (zipfile.BadZipFile, Exception) as exc:
        logger.error("Failed to read JAR %s: %s", jar_path, exc)

    return None


def _parse_bukkit_yml(content: str, plugin_type: str = "bukkit") -> PluginMeta:
    """Parse a plugin.yml / bungee.yml YAML string into PluginMeta."""
    try:
        # Simple YAML parser for plugin.yml – avoids full PyYAML dependency
        data = _simple_yaml_parse(content)
        return PluginMeta(
            name=data.get("name", "Unknown"),
            version=str(data.get("version", "Unknown")),
            main_class=data.get("main", ""),
            api_version=data.get("api-version"),
            description=data.get("description", ""),
            authors=_ensure_list(data.get("authors", data.get("author", []))),
            depend=_ensure_list(data.get("depend", [])),
            soft_depend=_ensure_list(data.get("softdepend", [])),
            load_before=_ensure_list(data.get("loadbefore", [])),
            plugin_type=plugin_type,
        )
    except Exception as exc:
        logger.warning("Failed to parse plugin YAML: %s", exc)
        return PluginMeta(plugin_type=plugin_type)


def _simple_yaml_parse(content: str) -> dict:
    """
    Minimal YAML parser for plugin.yml files.
    Handles simple key: value pairs and lists (- item).
    For complex YAML, falls back to PyYAML if available.
    """
    try:
        import yaml as pyyaml
        return pyyaml.safe_load(content) or {}
    except ImportError:
        pass

    result = {}
    current_key = None
    current_list: list = []

    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        # List item
        if stripped.startswith("- "):
            if current_key:
                current_list.append(stripped[2:].strip().strip("'\""))
            continue
        elif current_key and current_list:
            result[current_key] = current_list
            current_list = []
            current_key = None

        # Key: value
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip().lower()
            value = value.strip().strip("'\"")

            if value:
                result[key] = value
                current_key = None
            else:
                current_key = key
                current_list = []

    if current_key and current_list:
        result[current_key] = current_list

    return result


def _ensure_list(value) -> list:
    """Ensure a value is a list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    return []


# ──────────────────────────────────────────────
#  Validator
# ──────────────────────────────────────────────

class PluginValidator:
    """
    Validates a plugin JAR against the current server configuration.

    Args:
        server_type:  Current server software (e.g. "paper", "fabric")
        mc_version:   Current Minecraft version (e.g. "1.20.4")
        plugins_dir:  Path to the server's plugins directory
    """

    def __init__(self, server_type: str, mc_version: str, plugins_dir: str | Path) -> None:
        self.server_type = server_type.lower()
        self.mc_version = mc_version
        self.plugins_dir = Path(plugins_dir)

    def validate(self, jar_path: str | Path) -> ValidationResult:
        """
        Run all validation checks on a plugin JAR.

        Returns a ValidationResult with any issues found.
        """
        jar_path = Path(jar_path)
        meta = extract_plugin_meta(jar_path)
        result = ValidationResult(
            plugin_name=meta.name if meta else jar_path.stem,
        )

        if meta is None:
            result.add_error("Could not extract plugin metadata from JAR file")
            return result

        # 1. File integrity
        self._check_jar_integrity(jar_path, result)

        # 2. Server type compatibility
        self._check_server_compatibility(meta, result)

        # 3. MC version compatibility
        self._check_mc_version(meta, result)

        # 4. Duplicate detection
        self._check_duplicates(meta, jar_path, result)

        # 5. Dependencies
        self._check_dependencies(meta, result)

        return result

    def validate_all(self) -> list[ValidationResult]:
        """Validate all JAR files in the plugins directory."""
        results = []
        if not self.plugins_dir.exists():
            return results

        for jar_file in self.plugins_dir.glob("*.jar"):
            results.append(self.validate(jar_file))

        return results

    # ── Individual Checks ───────────────────────

    def _check_jar_integrity(self, jar_path: Path, result: ValidationResult) -> None:
        """Verify the JAR file is a valid ZIP archive."""
        if not jar_path.exists():
            result.add_error(f"File not found: {jar_path}")
            return

        if jar_path.stat().st_size == 0:
            result.add_error("JAR file is empty (0 bytes)")
            return

        try:
            with zipfile.ZipFile(jar_path, "r") as zf:
                bad = zf.testzip()
                if bad:
                    result.add_warning(f"Corrupted file inside JAR: {bad}")
        except zipfile.BadZipFile:
            result.add_error("File is not a valid JAR/ZIP archive")

    def _check_server_compatibility(self, meta: PluginMeta, result: ValidationResult) -> None:
        """Check if the plugin type matches the server software."""
        compatibility_map = {
            "paper": ["bukkit"],
            "spigot": ["bukkit"],
            "purpur": ["bukkit"],
            "fabric": ["fabric"],
            "forge": ["forge"],
            "velocity": ["velocity"],
            "bungeecord": ["bungeecord"],
        }

        allowed = compatibility_map.get(self.server_type, [])
        if meta.plugin_type not in allowed:
            result.add_error(
                f"Plugin type '{meta.plugin_type}' is not compatible with "
                f"'{self.server_type}' server (expected: {', '.join(allowed)})",
                field_name="plugin_type",
            )

    def _check_mc_version(self, meta: PluginMeta, result: ValidationResult) -> None:
        """Check if the plugin's API version is compatible with the MC version."""
        if meta.api_version:
            try:
                api_parts = [int(x) for x in meta.api_version.split(".")]
                mc_parts = [int(x) for x in self.mc_version.split(".")]

                if api_parts[:2] > mc_parts[:2]:
                    result.add_warning(
                        f"Plugin targets API version {meta.api_version}, "
                        f"but server is running {self.mc_version}",
                        field_name="api_version",
                    )
            except ValueError:
                result.add_info(f"Could not parse API version: {meta.api_version}")

    def _check_duplicates(self, meta: PluginMeta, jar_path: Path, result: ValidationResult) -> None:
        """Check for duplicate plugins in the plugins directory."""
        if not self.plugins_dir.exists():
            return

        for other_jar in self.plugins_dir.glob("*.jar"):
            if other_jar == jar_path:
                continue
            other_meta = extract_plugin_meta(other_jar)
            if other_meta and other_meta.name == meta.name:
                result.add_warning(
                    f"Duplicate plugin detected: '{meta.name}' also exists as {other_jar.name}",
                    field_name="duplicate",
                )

    def _check_dependencies(self, meta: PluginMeta, result: ValidationResult) -> None:
        """Check if hard dependencies are present in the plugins directory."""
        if not meta.depend or not self.plugins_dir.exists():
            return

        installed_plugins = set()
        for jar_file in self.plugins_dir.glob("*.jar"):
            jar_meta = extract_plugin_meta(jar_file)
            if jar_meta:
                installed_plugins.add(jar_meta.name)

        for dep in meta.depend:
            if dep not in installed_plugins:
                result.add_warning(
                    f"Required dependency '{dep}' not found in plugins directory",
                    field_name="depend",
                )
