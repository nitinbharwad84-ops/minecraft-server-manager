"""
plugin_manager.py
=================
High-level plugin lifecycle management.

Orchestrates:
  - Searching for plugins across Modrinth, Hangar, SpigotMC, and CurseForge
  - Installing / updating / removing plugins with dependency resolution
  - Tracking installed plugins in installed_plugins.json
  - Validation before installation
  - Backup management for plugin JARs
  - Update checking across all installed plugins
  - Manual file-based installation
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import aiohttp

from plugin_apis import (
    CurseForgeAPI,
    HangarAPI,
    ModrinthAPI,
    PluginDependency,
    PluginInfo,
    PluginSearchResult,
    PluginVersion,
    SpigotAPI,
    get_plugin_dependencies,
    get_plugin_info,
    get_plugin_versions,
    search_plugins,
)
from plugin_validator import PluginValidator, ValidationResult, extract_plugin_meta

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Result Dataclass
# ──────────────────────────────────────────────

@dataclass
class Result:
    """Unified result for plugin operations."""

    success: bool
    message: str
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str, **details: Any) -> "Result":
        return cls(success=True, message=message, details=details)

    @classmethod
    def fail(cls, message: str, error: Optional[str] = None, **details: Any) -> "Result":
        return cls(success=False, message=message, error=error, details=details)


# ──────────────────────────────────────────────
#  Installed Plugin Record
# ──────────────────────────────────────────────

class InstalledPlugin:
    """Represents a plugin installed in the server's plugins directory."""

    def __init__(
        self,
        name: str,
        version: str,
        source: str,
        source_id: str,
        filename: str,
        installed_at: str,
        mc_version: str = "",
        auto_update: bool = False,
        dependencies: Optional[List[str]] = None,
        file_size: int = 0,
        description: str = "",
        author: str = "",
    ) -> None:
        self.name = name
        self.version = version
        self.source = source          # "modrinth", "hangar", "spigotmc", "curseforge", "manual"
        self.source_id = source_id    # ID on the source platform
        self.filename = filename
        self.installed_at = installed_at
        self.mc_version = mc_version
        self.auto_update = auto_update
        self.dependencies = dependencies or []
        self.file_size = file_size
        self.description = description
        self.author = author

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "source_id": self.source_id,
            "filename": self.filename,
            "installed_at": self.installed_at,
            "mc_version": self.mc_version,
            "auto_update": self.auto_update,
            "dependencies": self.dependencies,
            "file_size": self.file_size,
            "description": self.description,
            "author": self.author,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InstalledPlugin":
        return cls(
            name=data.get("name", ""),
            version=data.get("version", ""),
            source=data.get("source", ""),
            source_id=data.get("source_id", ""),
            filename=data.get("filename", ""),
            installed_at=data.get("installed_at", ""),
            mc_version=data.get("mc_version", ""),
            auto_update=data.get("auto_update", False),
            dependencies=data.get("dependencies", []),
            file_size=data.get("file_size", 0),
            description=data.get("description", ""),
            author=data.get("author", ""),
        )


# ──────────────────────────────────────────────
#  Plugin Manager
# ──────────────────────────────────────────────

class PluginManager:
    """
    Manages the full plugin lifecycle.

    Args:
        plugins_dir:     Path to the server's plugins directory
        registry_path:   Path to installed_plugins.json
        server_type:     Current server type (e.g. "paper")
        mc_version:      Current Minecraft version (e.g. "1.20.4")
        backup_dir:      Path for plugin backups (default: plugins/backups)
        server_manager:  Optional reference to ServerManager for restart
    """

    def __init__(
        self,
        plugins_dir: str | Path,
        registry_path: str | Path,
        server_type: str = "paper",
        mc_version: str = "1.20.4",
        backup_dir: Optional[str | Path] = None,
        server_manager: Optional[Any] = None,
    ) -> None:
        self.plugins_dir = Path(plugins_dir)
        self.registry_path = Path(registry_path)
        self.server_type = server_type
        self.mc_version = mc_version
        self.backup_dir = Path(backup_dir) if backup_dir else self.plugins_dir / "backups"
        self.server_manager = server_manager

        # API clients
        self.modrinth = ModrinthAPI()
        self.hangar = HangarAPI()
        self.spigot = SpigotAPI()
        self.curseforge = CurseForgeAPI()

        # Validator
        self.validator = PluginValidator(server_type, mc_version, self.plugins_dir)

        # Installed plugins registry
        self.installed: List[InstalledPlugin] = []
        self._load_registry()

        # Ensure directories exist
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "PluginManager init: dir=%s type=%s mc=%s registered=%d",
            self.plugins_dir, server_type, mc_version, len(self.installed),
        )

    # ================================================================
    #  SEARCH
    # ================================================================

    async def search_plugins(
        self,
        query: str,
        session: aiohttp.ClientSession,
        *,
        server_type: Optional[str] = None,
        mc_version: Optional[str] = None,
        sources: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[PluginSearchResult]:
        """
        Search for plugins across all configured sources.

        Args:
            query:       Search query string
            session:     aiohttp session
            server_type: Override server type (defaults to self.server_type)
            mc_version:  Override MC version (defaults to self.mc_version)
            sources:     Explicit list of sources (overrides server_type mapping)
            limit:       Max results per source

        Returns:
            Combined and sorted list of PluginSearchResult
        """
        stype = server_type or self.server_type
        mcver = mc_version or self.mc_version

        if sources:
            # Use explicit source list
            all_results: List[PluginSearchResult] = []

            if "modrinth" in sources:
                results = await self.modrinth.search(
                    query, session, limit=limit, mc_version=mcver,
                    server_type=stype,
                )
                all_results.extend(results)
            if "hangar" in sources:
                results = await self.hangar.search(
                    query, session, limit=limit, mc_version=mcver,
                )
                all_results.extend(results)
            if "spigotmc" in sources:
                results = await self.spigot.search(
                    query, session, limit=limit, mc_version=mcver,
                )
                all_results.extend(results)
            if "curseforge" in sources:
                results = await self.curseforge.search(
                    query, session, limit=limit, mc_version=mcver,
                    server_type=stype,
                )
                all_results.extend(results)

            all_results.sort(key=lambda r: r.downloads, reverse=True)
            return all_results
        else:
            # Use the unified helper that maps server_type → sources
            return await search_plugins(
                query, stype, mcver, session, limit=limit,
            )

    # Backward-compat alias
    async def search(
        self,
        query: str,
        session: aiohttp.ClientSession,
        *,
        sources: Optional[List[str]] = None,
        limit: int = 15,
    ) -> List[PluginSearchResult]:
        """Backward-compatible search method."""
        return await self.search_plugins(
            query, session, sources=sources, limit=limit,
        )

    # ================================================================
    #  INSTALL PLUGIN
    # ================================================================

    async def install_plugin(
        self,
        plugin_name: str,
        version: Optional[str] = None,
        auto_deps: bool = True,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        source: Optional[str] = None,
        plugin: Optional[PluginSearchResult] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Result:
        """
        Install a plugin by name (searches if no PluginSearchResult provided).

        Args:
            plugin_name:       Plugin name to search for
            version:           Specific version (default: latest compatible)
            auto_deps:         Auto-install dependencies
            session:           aiohttp session (created if None)
            source:            Preferred source platform
            plugin:            Pre-resolved PluginSearchResult
            progress_callback: Optional async callable(downloaded, total)

        Returns:
            Result with installation details
        """
        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession()

        try:
            # 1. Find the plugin if not provided
            if plugin is None:
                results = await self.search_plugins(
                    plugin_name, session, limit=5,
                )
                if not results:
                    return Result.fail(
                        f"Plugin '{plugin_name}' not found",
                        error="No results from any source",
                    )

                # Filter by source if specified
                if source:
                    filtered = [r for r in results if r.source == source]
                    plugin = filtered[0] if filtered else results[0]
                else:
                    plugin = results[0]

            logger.info(
                "Installing plugin: %s from %s (id=%s)",
                plugin.name, plugin.source, plugin.id,
            )

            # 2. Resolve the version and download URL
            download_url, resolved_version = await self._resolve_version(
                plugin, session, version,
            )
            if not download_url:
                return Result.fail(
                    f"Could not resolve download URL for {plugin.name}",
                    error="Version not found or API error",
                )

            # 3. Check for dependencies and install if auto_deps
            if auto_deps:
                dep_result = await self._install_dependencies(
                    plugin, session, progress_callback,
                )
                if not dep_result.success:
                    logger.warning(
                        "Some dependencies failed for %s: %s",
                        plugin.name, dep_result.message,
                    )

            # 4. Determine filename
            filename = self._safe_filename(plugin.name, download_url)

            # 5. Check if already installed (same version)
            existing = self.get_plugin(plugin.name)
            if existing and existing.version == resolved_version:
                return Result.ok(
                    f"{plugin.name} v{resolved_version} is already installed",
                    already_installed=True,
                    filename=existing.filename,
                )

            # 6. Backup existing version if updating
            if existing:
                self._backup_plugin(existing)

            # 7. Download the JAR
            dest = self.plugins_dir / filename
            downloaded = await self._download_file(
                download_url, dest, session, progress_callback,
            )
            if not downloaded:
                return Result.fail(
                    f"Download failed for {plugin.name}",
                    error="HTTP error or network issue",
                    url=download_url,
                )

            # 8. Validate the plugin
            validation = self.validator.validate(dest)
            if not validation.is_valid:
                errors = "; ".join(
                    i.message for i in validation.issues if i.severity == "error"
                )
                dest.unlink(missing_ok=True)
                return Result.fail(
                    f"Validation failed for {plugin.name}: {errors}",
                    error=errors,
                )

            # 9. Extract metadata from JAR
            meta = extract_plugin_meta(dest)
            if meta:
                resolved_version = meta.version or resolved_version

            # 10. Register the installation
            file_size = dest.stat().st_size
            record = InstalledPlugin(
                name=plugin.name,
                version=resolved_version,
                source=plugin.source,
                source_id=plugin.id,
                filename=filename,
                installed_at=datetime.now(tz=timezone.utc).isoformat(),
                mc_version=self.mc_version,
                dependencies=meta.depend if meta else [],
                file_size=file_size,
                description=plugin.description,
                author=plugin.author,
            )

            # Remove previous version from registry
            self.installed = [p for p in self.installed if p.name != plugin.name]
            self.installed.append(record)
            self._save_registry()

            logger.info(
                "Installed plugin: %s v%s (%s, %d bytes)",
                plugin.name, resolved_version, filename, file_size,
            )

            return Result.ok(
                f"Successfully installed {plugin.name} v{resolved_version}",
                name=plugin.name,
                version=resolved_version,
                filename=filename,
                source=plugin.source,
                file_size=file_size,
            )

        except Exception as exc:
            logger.error("Plugin install failed: %s", exc)
            return Result.fail(
                f"Installation failed: {exc}",
                error=str(exc),
            )

        finally:
            if own_session:
                await session.close()

    # Backward-compat alias
    async def install(
        self,
        plugin: PluginSearchResult,
        session: aiohttp.ClientSession,
        *,
        version_id: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Tuple[bool, str]:
        """Backward-compatible install method returning (bool, str)."""
        result = await self.install_plugin(
            plugin.name,
            version=version_id,
            session=session,
            plugin=plugin,
            progress_callback=progress_callback,
        )
        return result.success, result.message

    # ================================================================
    #  UNINSTALL PLUGIN
    # ================================================================

    def uninstall_plugin(self, plugin_name: str) -> Result:
        """
        Uninstall a plugin.

        Creates a backup, removes the JAR, and updates the registry.

        Args:
            plugin_name: Name of the plugin to remove
        """
        record = self.get_plugin(plugin_name)
        if not record:
            return Result.fail(
                f"Plugin '{plugin_name}' not found in registry",
                error="Not installed",
            )

        # Backup the JAR before removal
        jar_path = self.plugins_dir / record.filename
        backup_path = None
        if jar_path.exists():
            backup_path = self._backup_plugin(record)
            jar_path.unlink()
            logger.info("Deleted plugin JAR: %s", jar_path)

        # Remove plugin data directory if exists
        data_dir = self.plugins_dir / record.name
        if data_dir.exists() and data_dir.is_dir():
            logger.info("Plugin data directory exists: %s (not removed)", data_dir)

        # Remove from registry
        self.installed = [p for p in self.installed if p.name != plugin_name]
        self._save_registry()

        logger.info("Uninstalled plugin: %s", plugin_name)
        return Result.ok(
            f"Removed plugin: {plugin_name}",
            name=plugin_name,
            backup=str(backup_path) if backup_path else None,
        )

    # Backward-compat alias
    def remove(self, plugin_name: str) -> Tuple[bool, str]:
        """Remove a plugin (backward-compat wrapper)."""
        result = self.uninstall_plugin(plugin_name)
        return result.success, result.message

    # ================================================================
    #  UPDATE PLUGIN
    # ================================================================

    async def update_plugin(
        self,
        plugin_name: str,
        *,
        session: Optional[aiohttp.ClientSession] = None,
        progress_callback: Optional[Callable] = None,
    ) -> Result:
        """
        Update a plugin to the latest version.

        Backs up current version, downloads new version, replaces JAR.

        Args:
            plugin_name:       Name of the plugin to update
            session:           aiohttp session
            progress_callback: Optional progress callback
        """
        record = self.get_plugin(plugin_name)
        if not record:
            return Result.fail(
                f"Plugin '{plugin_name}' not found",
                error="Not installed",
            )

        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession()

        try:
            # Get available versions
            versions = await self._get_versions(record, session)
            if not versions:
                return Result.fail(
                    f"No versions found for {plugin_name}",
                    error="API returned no versions",
                )

            latest = versions[0]

            # Check if already up to date
            if latest.version_number == record.version:
                return Result.ok(
                    f"{plugin_name} is already up to date (v{record.version})",
                    current_version=record.version,
                    latest_version=latest.version_number,
                )

            logger.info(
                "Updating %s: %s → %s",
                plugin_name, record.version, latest.version_number,
            )

            # Backup current JAR
            self._backup_plugin(record)

            # Resolve download URL
            download_url = await self._resolve_download_from_version(
                record, latest, session,
            )
            if not download_url:
                return Result.fail(
                    f"Could not resolve download URL for {plugin_name} update",
                    error="Version download URL unavailable",
                )

            # Download new version
            dest = self.plugins_dir / record.filename
            downloaded = await self._download_file(
                download_url, dest, session, progress_callback,
            )
            if not downloaded:
                return Result.fail(
                    f"Download failed for {plugin_name} update",
                    error="HTTP error or network issue",
                )

            # Validate
            validation = self.validator.validate(dest)
            if not validation.is_valid:
                errors = "; ".join(
                    i.message for i in validation.issues if i.severity == "error"
                )
                # Restore backup
                self._restore_latest_backup(record)
                return Result.fail(
                    f"Validation failed for updated {plugin_name}: {errors}",
                    error=errors,
                )

            # Update registry
            old_version = record.version
            record.version = latest.version_number
            record.installed_at = datetime.now(tz=timezone.utc).isoformat()
            record.file_size = dest.stat().st_size
            self._save_registry()

            logger.info(
                "Updated %s: %s → %s",
                plugin_name, old_version, latest.version_number,
            )

            return Result.ok(
                f"Updated {plugin_name}: {old_version} → {latest.version_number}",
                name=plugin_name,
                old_version=old_version,
                new_version=latest.version_number,
            )

        except Exception as exc:
            logger.error("Plugin update failed: %s", exc)
            return Result.fail(
                f"Update failed: {exc}", error=str(exc),
            )

        finally:
            if own_session:
                await session.close()

    # ================================================================
    #  GET INSTALLED PLUGINS
    # ================================================================

    def get_installed_plugins(self) -> List[InstalledPlugin]:
        """
        Return all installed plugins, verifying JARs still exist.

        Cleans up registry entries for missing JARs.
        """
        valid: List[InstalledPlugin] = []
        removed = 0

        for plugin in self.installed:
            jar_path = self.plugins_dir / plugin.filename
            if jar_path.exists():
                valid.append(plugin)
            else:
                logger.warning(
                    "Plugin JAR missing for %s: %s", plugin.name, jar_path,
                )
                removed += 1

        if removed > 0:
            self.installed = valid
            self._save_registry()
            logger.info("Cleaned up %d missing plugins from registry", removed)

        return list(valid)

    # Backward-compat alias
    def list_installed(self) -> List[InstalledPlugin]:
        """Alias for get_installed_plugins."""
        return self.get_installed_plugins()

    def get_plugin(self, name: str) -> Optional[InstalledPlugin]:
        """Find an installed plugin by name (case-insensitive)."""
        name_lower = name.lower()
        return next(
            (p for p in self.installed if p.name.lower() == name_lower),
            None,
        )

    # ================================================================
    #  CHECK UPDATES
    # ================================================================

    async def check_plugin_updates(
        self,
        session: Optional[aiohttp.ClientSession] = None,
    ) -> Dict[str, str]:
        """
        Check all installed plugins for available updates.

        Returns:
            Dict of plugin_name → new_version for plugins with updates
        """
        own_session = session is None
        if own_session:
            session = aiohttp.ClientSession()

        updates: Dict[str, str] = {}

        try:
            for plugin in self.installed:
                if plugin.source == "manual":
                    continue

                try:
                    versions = await self._get_versions(plugin, session)
                    if versions:
                        latest = versions[0]
                        if latest.version_number != plugin.version:
                            updates[plugin.name] = latest.version_number
                            logger.info(
                                "Update available for %s: %s → %s",
                                plugin.name, plugin.version, latest.version_number,
                            )
                except Exception as exc:
                    logger.warning(
                        "Update check failed for %s: %s", plugin.name, exc,
                    )

        finally:
            if own_session:
                await session.close()

        return updates

    # Backward-compat alias
    async def check_updates(
        self, session: aiohttp.ClientSession,
    ) -> List[Tuple[InstalledPlugin, PluginVersion]]:
        """Backward-compatible update checker returning tuples."""
        result: List[Tuple[InstalledPlugin, PluginVersion]] = []

        for plugin in self.installed:
            if plugin.source == "manual":
                continue
            try:
                versions = await self._get_versions(plugin, session)
                if versions:
                    latest = versions[0]
                    if latest.version_number != plugin.version:
                        result.append((plugin, latest))
            except Exception as exc:
                logger.warning(
                    "Update check failed for %s: %s", plugin.name, exc,
                )

        return result

    # ================================================================
    #  INSTALL FROM FILE
    # ================================================================

    def install_from_file(self, file_path: str | Path) -> Result:
        """
        Install a plugin from a local JAR file.

        Validates, copies to plugins directory, and registers.

        Args:
            file_path: Path to the JAR file
        """
        source_path = Path(file_path)

        if not source_path.exists():
            return Result.fail(
                f"File not found: {source_path}",
                error="File does not exist",
            )

        if source_path.suffix.lower() != ".jar":
            return Result.fail(
                f"Not a JAR file: {source_path.name}",
                error="Only .jar files are supported",
            )

        # Validate
        validation = self.validator.validate(source_path)
        if not validation.is_valid:
            errors = "; ".join(
                i.message for i in validation.issues if i.severity == "error"
            )
            return Result.fail(
                f"Validation failed: {errors}",
                error=errors,
            )

        # Extract metadata
        meta = extract_plugin_meta(source_path)
        name = meta.name if meta else source_path.stem
        version = meta.version if meta else "unknown"

        # Copy to plugins directory
        dest = self.plugins_dir / source_path.name
        if dest.exists():
            # Backup existing
            existing = self.get_plugin(name)
            if existing:
                self._backup_plugin(existing)

        try:
            shutil.copy2(str(source_path), str(dest))
        except (OSError, shutil.Error) as exc:
            return Result.fail(
                f"Failed to copy plugin: {exc}",
                error=str(exc),
            )

        # Register
        file_size = dest.stat().st_size
        record = InstalledPlugin(
            name=name,
            version=version,
            source="manual",
            source_id="",
            filename=source_path.name,
            installed_at=datetime.now(tz=timezone.utc).isoformat(),
            mc_version=self.mc_version,
            dependencies=meta.depend if meta else [],
            file_size=file_size,
            description=meta.description if meta else "",
            author=", ".join(meta.authors) if meta else "",
        )

        self.installed = [p for p in self.installed if p.name != name]
        self.installed.append(record)
        self._save_registry()

        logger.info("Installed plugin from file: %s v%s", name, version)

        return Result.ok(
            f"Installed {name} v{version} from file",
            name=name,
            version=version,
            filename=source_path.name,
            file_size=file_size,
        )

    # ================================================================
    #  BACKUP & RESTORE
    # ================================================================

    def _backup_plugin(self, plugin: InstalledPlugin) -> Optional[Path]:
        """Create a backup of a plugin JAR."""
        jar_path = self.plugins_dir / plugin.filename
        if not jar_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(
            c if c.isalnum() or c in "-_." else "-" for c in plugin.name
        )
        backup_name = f"{safe_name}_{plugin.version}_{timestamp}.jar"
        backup_path = self.backup_dir / backup_name

        try:
            shutil.copy2(str(jar_path), str(backup_path))
            logger.info("Backed up plugin: %s → %s", jar_path, backup_path)
            return backup_path
        except (OSError, shutil.Error) as exc:
            logger.error("Failed to backup plugin %s: %s", plugin.name, exc)
            return None

    def _restore_latest_backup(self, plugin: InstalledPlugin) -> bool:
        """Restore the most recent backup of a plugin."""
        safe_name = "".join(
            c if c.isalnum() or c in "-_." else "-" for c in plugin.name
        )
        pattern = f"{safe_name}_*.jar"
        backups = sorted(
            self.backup_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if not backups:
            logger.warning("No backups found for %s", plugin.name)
            return False

        dest = self.plugins_dir / plugin.filename
        try:
            shutil.copy2(str(backups[0]), str(dest))
            logger.info("Restored plugin from backup: %s", backups[0])
            return True
        except (OSError, shutil.Error) as exc:
            logger.error("Failed to restore plugin %s: %s", plugin.name, exc)
            return False

    # ================================================================
    #  DEPENDENCY RESOLUTION
    # ================================================================

    async def _install_dependencies(
        self,
        plugin: PluginSearchResult,
        session: aiohttp.ClientSession,
        progress_callback: Optional[Callable] = None,
        _resolved: Optional[Set[str]] = None,
    ) -> Result:
        """
        Resolve and install required dependencies.

        Prevents circular dependencies with _resolved set.
        """
        if _resolved is None:
            _resolved = set()

        # Avoid circular dependencies
        if plugin.id in _resolved:
            return Result.ok("Already resolved")
        _resolved.add(plugin.id)

        try:
            dep_names = await get_plugin_dependencies(
                plugin.id, plugin.source, session, self.mc_version,
            )
        except Exception as exc:
            logger.warning("Failed to fetch dependencies for %s: %s", plugin.name, exc)
            return Result.ok("Dependencies could not be checked (non-fatal)")

        if not dep_names:
            return Result.ok("No dependencies required")

        failed: List[str] = []
        installed_deps: List[str] = []

        for dep_id in dep_names:
            # Skip if already installed
            if any(p.source_id == dep_id for p in self.installed):
                continue

            logger.info("Installing dependency: %s for %s", dep_id, plugin.name)

            try:
                # Get dependency info
                dep_info = await get_plugin_info(dep_id, plugin.source, session)
                if not dep_info:
                    logger.warning("Could not find dependency: %s", dep_id)
                    failed.append(dep_id)
                    continue

                # Create a PluginSearchResult for the dependency
                dep_plugin = PluginSearchResult(
                    id=dep_info.id,
                    name=dep_info.name,
                    description=dep_info.description,
                    author=dep_info.author,
                    downloads=dep_info.downloads,
                    source=plugin.source,
                )

                # Recursive install (with auto_deps=True to fetch transitive deps)
                result = await self.install_plugin(
                    dep_info.name,
                    session=session,
                    plugin=dep_plugin,
                    auto_deps=True,
                    progress_callback=progress_callback,
                )

                if result.success:
                    installed_deps.append(dep_info.name)
                else:
                    failed.append(dep_id)
                    logger.warning(
                        "Failed to install dependency %s: %s",
                        dep_id, result.message,
                    )

            except Exception as exc:
                logger.error("Error installing dependency %s: %s", dep_id, exc)
                failed.append(dep_id)

        if failed:
            return Result.fail(
                f"Some dependencies failed: {', '.join(failed)}",
                error="Dependency installation incomplete",
                installed=installed_deps,
                failed=failed,
            )

        return Result.ok(
            f"Installed {len(installed_deps)} dependencies",
            installed=installed_deps,
        )

    # ================================================================
    #  PRIVATE HELPERS
    # ================================================================

    async def _resolve_version(
        self,
        plugin: PluginSearchResult,
        session: aiohttp.ClientSession,
        version_id: Optional[str] = None,
    ) -> Tuple[Optional[str], str]:
        """
        Resolve download URL and version string.

        Returns:
            (download_url, version_string)
        """
        if plugin.source == "modrinth":
            versions = await self.modrinth.get_versions(
                plugin.id, session, mc_version=self.mc_version,
            )
            if not versions:
                return None, ""

            target = versions[0]  # Latest compatible
            if version_id:
                match = next(
                    (v for v in versions if v.id == version_id or v.version_number == version_id),
                    None,
                )
                if match:
                    target = match

            return target.download_url, target.version_number

        elif plugin.source == "hangar":
            versions = await self.hangar.get_versions(
                plugin.id, session, mc_version=self.mc_version,
            )
            if not versions:
                return None, ""

            target = versions[0]
            if version_id:
                match = next(
                    (v for v in versions if v.id == version_id or v.version_number == version_id),
                    None,
                )
                if match:
                    target = match

            url = await self.hangar.get_download_url(
                plugin.id, target.id, session,
            )
            return url, target.version_number

        elif plugin.source == "spigotmc":
            url = await self.spigot.get_download_url(
                plugin.id, version_id or "latest", session,
            )
            return url, version_id or "latest"

        elif plugin.source == "curseforge":
            versions = await self.curseforge.get_versions(
                plugin.id, session, mc_version=self.mc_version,
            )
            if not versions:
                return None, ""

            target = versions[0]
            if version_id:
                match = next(
                    (v for v in versions if v.id == version_id),
                    None,
                )
                if match:
                    target = match

            url = target.download_url
            if not url:
                url = await self.curseforge.get_download_url(
                    plugin.id, target.id, session,
                )
            return url, target.version_number

        return None, ""

    # Backward-compat alias
    async def _resolve_download_url(
        self,
        plugin: PluginSearchResult,
        session: aiohttp.ClientSession,
        version_id: Optional[str],
    ) -> Optional[str]:
        """Resolve download URL (backward compat)."""
        url, _ = await self._resolve_version(plugin, session, version_id)
        return url

    async def _resolve_download_from_version(
        self,
        record: InstalledPlugin,
        version: PluginVersion,
        session: aiohttp.ClientSession,
    ) -> Optional[str]:
        """Resolve download URL from an InstalledPlugin + PluginVersion."""
        if version.download_url:
            return version.download_url

        if record.source == "modrinth":
            return await self.modrinth.get_download_url(
                record.source_id, version.id, session,
            )
        elif record.source == "hangar":
            return await self.hangar.get_download_url(
                record.source_id, version.id, session,
            )
        elif record.source == "spigotmc":
            return await self.spigot.get_download_url(
                record.source_id, version.id, session,
            )
        elif record.source == "curseforge":
            return await self.curseforge.get_download_url(
                record.source_id, version.id, session,
            )
        return None

    async def _get_versions(
        self,
        plugin: InstalledPlugin,
        session: aiohttp.ClientSession,
    ) -> List[PluginVersion]:
        """Fetch versions from the correct API based on plugin source."""
        if plugin.source == "modrinth":
            return await self.modrinth.get_versions(
                plugin.source_id, session, mc_version=self.mc_version,
            )
        elif plugin.source == "hangar":
            return await self.hangar.get_versions(
                plugin.source_id, session, mc_version=self.mc_version,
            )
        elif plugin.source == "spigotmc":
            return await self.spigot.get_versions(plugin.source_id, session)
        elif plugin.source == "curseforge":
            return await self.curseforge.get_versions(
                plugin.source_id, session, mc_version=self.mc_version,
            )
        return []

    @staticmethod
    async def _download_file(
        url: str,
        dest: Path,
        session: aiohttp.ClientSession,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """Download a file from a URL to a local path."""
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error(
                        "Download failed: HTTP %d from %s", resp.status, url,
                    )
                    return False

                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                with open(dest, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(8192):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            await progress_callback(downloaded, total)

            return True
        except Exception as exc:
            logger.error("Download error: %s", exc)
            return False

    @staticmethod
    def _safe_filename(name: str, url: str) -> str:
        """Generate a safe JAR filename from plugin name and URL."""
        # Try to get filename from URL
        url_filename = url.rsplit("/", 1)[-1] if "/" in url else ""
        if url_filename.endswith(".jar"):
            # Sanitize the URL filename
            safe = "".join(
                c if c.isalnum() or c in "-_." else "-" for c in url_filename
            )
            return safe

        # Sanitize the plugin name
        safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in name)
        return f"{safe}.jar"

    # ================================================================
    #  REGISTRY PERSISTENCE
    # ================================================================

    def _load_registry(self) -> None:
        """Load installed plugins from installed_plugins.json."""
        if not self.registry_path.exists():
            return
        try:
            with open(self.registry_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.installed = [
                InstalledPlugin.from_dict(p) for p in data.get("plugins", [])
            ]
            logger.debug("Loaded %d plugins from registry", len(self.installed))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load plugin registry: %s", exc)

    def _save_registry(self) -> None:
        """Persist installed plugins to installed_plugins.json."""
        data = {
            "plugins": [p.to_dict() for p in self.installed],
            "server_type": self.server_type,
            "mc_version": self.mc_version,
            "plugin_count": len(self.installed),
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            with open(self.registry_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            logger.error("Could not save plugin registry: %s", exc)
