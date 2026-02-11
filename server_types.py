"""
server_types.py
===============
Comprehensive Minecraft server software definitions with download APIs,
version resolution, and compatibility metadata.

Supported server types:
  - Vanilla    (Official Mojang server)
  - Paper      (High-performance Spigot fork)
  - Spigot     (Popular Bukkit fork)
  - Purpur     (Paper fork with extra features)
  - Fabric     (Lightweight mod loader)
  - Forge      (Most popular mod loader)
  - Quilt      (Modern modding platform)
  - Velocity   (Modern proxy)
  - BungeeCord (Legacy proxy)

Each server type provides:
  - Version resolution (latest/all available versions)
  - Download URL construction
  - Plugin/mod platform compatibility
  - Java version requirements
  - API authentication (if needed)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Result Object
# ──────────────────────────────────────────────

@dataclass
class Result:
    """Unified result object for server operations."""

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
#  Enums
# ──────────────────────────────────────────────

class ServerSoftware(str, Enum):
    """Enumeration of all supported server software."""

    PAPER = "paper"
    SPIGOT = "spigot"
    PURPUR = "purpur"
    FABRIC = "fabric"
    FORGE = "forge"
    QUILT = "quilt"
    VANILLA = "vanilla"
    VELOCITY = "velocity"
    BUNGEECORD = "bungeecord"


class PluginPlatform(str, Enum):
    """Plugin platforms each server type supports."""

    BUKKIT = "bukkit"
    SPIGOT = "spigot"
    PAPER = "paper"
    FABRIC = "fabric"
    FORGE = "forge"
    QUILT = "quilt"
    VELOCITY = "velocity"
    BUNGEECORD = "bungeecord"


# ──────────────────────────────────────────────
#  Server Type Dataclass
# ──────────────────────────────────────────────

@dataclass
class ServerType:
    """
    Represents a Minecraft server software type.

    Attributes:
        name:              Human-readable display name
        software:          The software enum value
        api_base:          Base URL for the download/version API
        plugin_platforms:  List of plugin platforms this server supports
        mod_sources:       List of mod sources (modrinth, curseforge)
        plugin_sources:    List of plugin sources (spigotmc, bukkit, hangar)
        min_java:          Minimum Java version required
        recommended_java:  Recommended Java version
        description:       Short description of the server type
        supports_plugins:  Whether this server type supports plugins
        supports_mods:     Whether this server type supports mods
        api_key_env:       Environment variable for API key (if needed)
        requires_auth:     Whether this API requires authentication
    """

    name: str
    software: ServerSoftware
    api_base: str
    plugin_platforms: List[PluginPlatform] = field(default_factory=list)
    mod_sources: List[str] = field(default_factory=list)
    plugin_sources: List[str] = field(default_factory=list)
    min_java: int = 17
    recommended_java: int = 21
    description: str = ""
    supports_plugins: bool = True
    supports_mods: bool = False
    api_key_env: Optional[str] = None
    requires_auth: bool = False

    # ================================================================
    #  VERSION RESOLUTION
    # ================================================================

    async def get_available_versions(
        self, session: aiohttp.ClientSession
    ) -> List[str]:
        """
        Fetch all available MC versions for this server software.

        Returns:
            List of version strings, sorted newest first
        """
        try:
            url = self._versions_url()
            if not url:
                logger.warning("No versions URL for %s", self.name)
                return []

            headers = self._get_headers()
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Failed to fetch versions for %s: HTTP %d",
                        self.name, resp.status,
                    )
                    return []
                data = await resp.json()
                versions = self._parse_versions(data)
                logger.info("Fetched %d versions for %s", len(versions), self.name)
                return versions

        except Exception as exc:
            logger.error("Error fetching versions for %s: %s", self.name, exc)
            return []

    async def is_version_supported(
        self, version: str, session: aiohttp.ClientSession
    ) -> bool:
        """
        Check if a specific version is available for this server type.

        Args:
            version: Minecraft version (e.g. "1.20.4")
            session: aiohttp session

        Returns:
            True if the version is supported
        """
        versions = await self.get_available_versions(session)
        return version in versions

    async def get_latest_version(
        self, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """
        Get the latest available MC version for this server type.

        Returns:
            Latest version string or None
        """
        versions = await self.get_available_versions(session)
        return versions[0] if versions else None

    # ================================================================
    #  DOWNLOAD URL RESOLUTION
    # ================================================================

    async def get_download_url(
        self,
        version: str,
        session: aiohttp.ClientSession,
    ) -> Optional[str]:
        """
        Resolve the download URL for a specific MC version.

        Args:
            version: Minecraft version (e.g. "1.20.4")
            session: aiohttp session

        Returns:
            Direct download URL or None if unavailable
        """
        try:
            if self.software == ServerSoftware.PAPER:
                return await self._paper_download_url(version, session)
            elif self.software == ServerSoftware.PURPUR:
                return await self._purpur_download_url(version, session)
            elif self.software == ServerSoftware.VANILLA:
                return await self._vanilla_download_url(version, session)
            elif self.software == ServerSoftware.FABRIC:
                return await self._fabric_download_url(version, session)
            elif self.software == ServerSoftware.QUILT:
                return await self._quilt_download_url(version, session)
            elif self.software == ServerSoftware.FORGE:
                return await self._forge_download_url(version, session)
            elif self.software == ServerSoftware.VELOCITY:
                return await self._velocity_download_url(version, session)
            elif self.software == ServerSoftware.BUNGEECORD:
                return await self._bungeecord_download_url(version, session)
            else:
                logger.warning(
                    "Download URL resolution not implemented for %s", self.name
                )
                return None

        except Exception as exc:
            logger.error(
                "Error resolving download URL for %s %s: %s",
                self.name, version, exc,
            )
            return None

    # ================================================================
    #  DOWNLOAD WITH PROGRESS
    # ================================================================

    async def download_server(
        self,
        version: str,
        dest_path: str | Path,
        session: aiohttp.ClientSession,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Result:
        """
        Download server software to a file with progress tracking.

        Args:
            version:           Minecraft version
            dest_path:         Destination file path
            session:           aiohttp session
            progress_callback: Optional callback(downloaded, total)

        Returns:
            Result with download status
        """
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        url = await self.get_download_url(version, session)
        if not url:
            return Result.fail(
                f"Could not resolve download URL for {self.name} {version}",
                error="Version not found or API error",
            )

        logger.info("Downloading %s %s from %s", self.name, version, url)

        try:
            headers = self._get_headers()
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return Result.fail(
                        f"Download failed: HTTP {resp.status}",
                        error=f"Server returned {resp.status}",
                        url=url,
                    )

                total_size = int(resp.headers.get("Content-Length", 0))
                downloaded = 0

                with open(dest, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(8192):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            progress_callback(downloaded, total_size)

            # Verify file
            actual_size = dest.stat().st_size
            logger.info(
                "Downloaded %s %s: %d bytes",
                self.name, version, actual_size,
            )

            if total_size and actual_size != total_size:
                logger.warning(
                    "Size mismatch: expected %d, got %d",
                    total_size, actual_size,
                )

            return Result.ok(
                f"Downloaded {self.name} {version}",
                path=str(dest),
                size_bytes=actual_size,
                url=url,
            )

        except Exception as exc:
            logger.error("Download failed: %s", exc)
            if dest.exists():
                dest.unlink()
            return Result.fail(
                f"Download failed: {exc}",
                error=str(exc),
                url=url,
            )

    # ================================================================
    #  JAVA VERSION MAPPING
    # ================================================================

    @staticmethod
    def java_version_for_mc(mc_version: str) -> int:
        """
        Return the minimum Java version required for a given MC version.

        Mapping:
            MC 1.21+      → Java 21
            MC 1.20.5+    → Java 21
            MC 1.17-1.20.4→ Java 17
            MC 1.12-1.16  → Java 11
            MC < 1.12     → Java 8
        """
        try:
            parts = mc_version.split(".")
            major = int(parts[1]) if len(parts) >= 2 else 0
            minor = int(parts[2]) if len(parts) >= 3 else 0

            if major >= 21 or (major == 20 and minor >= 5):
                return 21
            elif major >= 17:
                return 17
            elif major >= 12:
                return 11
            else:
                return 8
        except (ValueError, IndexError):
            return 17  # Safe default

    def get_java_requirement(self, mc_version: str) -> int:
        """Get minimum Java for this server + MC version."""
        return max(self.min_java, self.java_version_for_mc(mc_version))

    def get_java_recommendation(self, mc_version: str) -> int:
        """Get recommended Java for this server + MC version."""
        return max(self.recommended_java, self.java_version_for_mc(mc_version))

    # ================================================================
    #  PRIVATE: API HELPERS
    # ================================================================

    def _get_headers(self) -> Dict[str, str]:
        """Build headers including auth if required."""
        headers = {"User-Agent": "MinecraftServerManager/1.0"}

        if self.requires_auth and self.api_key_env:
            import os
            api_key = os.environ.get(self.api_key_env, "")
            if api_key:
                if self.software == ServerSoftware.FORGE:
                    headers["X-API-Key"] = api_key
                elif "curseforge" in self.api_base.lower():
                    headers["X-Api-Key"] = api_key

        return headers

    def _versions_url(self) -> Optional[str]:
        """Construct the versions-list endpoint URL."""
        urls = {
            ServerSoftware.PAPER: f"{self.api_base}/v2/projects/paper",
            ServerSoftware.PURPUR: f"{self.api_base}/v2",
            ServerSoftware.VANILLA: "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
            ServerSoftware.FABRIC: f"{self.api_base}/v2/versions/game",
            ServerSoftware.QUILT: "https://meta.quiltmc.org/v3/versions/game",
            ServerSoftware.VELOCITY: f"{self.api_base}/v2/projects/velocity",
            # Forge & BungeeCord don't have simple version list APIs
        }
        return urls.get(self.software)

    def _parse_versions(self, data: dict | list) -> List[str]:
        """Extract version strings from API-specific response shapes."""
        if self.software in (ServerSoftware.PAPER, ServerSoftware.VELOCITY):
            return data.get("versions", [])
        elif self.software == ServerSoftware.PURPUR:
            return data.get("versions", [])
        elif self.software == ServerSoftware.VANILLA:
            return [
                v["id"]
                for v in data.get("versions", [])
                if v.get("type") == "release"
            ]
        elif self.software == ServerSoftware.FABRIC:
            return [v["version"] for v in data if v.get("stable", False)]
        elif self.software == ServerSoftware.QUILT:
            return [v["version"] for v in data if v.get("stable", False)]
        return []

    # ================================================================
    #  PRIVATE: PER-SOFTWARE DOWNLOAD URL RESOLVERS
    # ================================================================

    async def _paper_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve Paper download: project → version → latest build → JAR."""
        builds_url = f"{self.api_base}/v2/projects/paper/versions/{version}/builds"
        async with session.get(builds_url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            builds = data.get("builds", [])
            if not builds:
                return None
            latest = builds[-1]
            build_num = latest["build"]
            jar_name = latest["downloads"]["application"]["name"]
            return (
                f"{self.api_base}/v2/projects/paper/versions/{version}"
                f"/builds/{build_num}/downloads/{jar_name}"
            )

    async def _purpur_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve Purpur download URL for the latest build."""
        return f"{self.api_base}/v2/{version}/latest/download"

    async def _vanilla_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve Vanilla server JAR from Mojang's version manifest."""
        manifest_url = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
        async with session.get(manifest_url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            for v in data.get("versions", []):
                if v["id"] == version:
                    version_url = v["url"]
                    async with session.get(version_url) as vresp:
                        if vresp.status != 200:
                            return None
                        vdata = await vresp.json()
                        return (
                            vdata.get("downloads", {})
                            .get("server", {})
                            .get("url")
                        )
        return None

    async def _fabric_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve Fabric server installer URL."""
        # Get latest loader version
        loader_url = f"{self.api_base}/v2/versions/loader"
        async with session.get(loader_url) as resp:
            if resp.status != 200:
                return None
            loaders = await resp.json()
            if not loaders:
                return None
            loader_version = loaders[0]["version"]

        # Get latest installer version
        installer_url = f"{self.api_base}/v2/versions/installer"
        async with session.get(installer_url) as resp:
            if resp.status != 200:
                return None
            installers = await resp.json()
            if not installers:
                return None
            installer_version = installers[0]["version"]

        return (
            f"{self.api_base}/v2/versions/loader/{version}/{loader_version}"
            f"/{installer_version}/server/jar"
        )

    async def _quilt_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve Quilt server installer URL."""
        # Get latest loader
        loader_url = "https://meta.quiltmc.org/v3/versions/loader"
        async with session.get(loader_url) as resp:
            if resp.status != 200:
                return None
            loaders = await resp.json()
            if not loaders:
                return None
            loader_version = loaders[0]["version"]

        # Get latest installer
        installer_url = "https://meta.quiltmc.org/v3/versions/installer"
        async with session.get(installer_url) as resp:
            if resp.status != 200:
                return None
            installers = await resp.json()
            if not installers:
                return None
            installer_version = installers[0]["version"]

        return (
            f"https://meta.quiltmc.org/v3/versions/loader/{version}/"
            f"{loader_version}/{installer_version}/server/jar"
        )

    async def _forge_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """
        Resolve Forge download URL.

        Note: Forge downloads are complex and require multi-step install.
        This returns the installer JAR, not the final server.
        """
        # Forge API is very complex and changes frequently
        # For now, return a generic URL pattern
        # In production, this would scrape the forge website or use a dedicated API
        logger.warning(
            "Forge download requires manual installation. "
            "Please visit https://files.minecraftforge.net"
        )
        return None

    async def _velocity_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve Velocity proxy download URL."""
        builds_url = f"{self.api_base}/v2/projects/velocity/versions/{version}/builds"
        async with session.get(builds_url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            builds = data.get("builds", [])
            if not builds:
                return None
            latest = builds[-1]
            build_num = latest["build"]
            jar_name = latest["downloads"]["application"]["name"]
            return (
                f"{self.api_base}/v2/projects/velocity/versions/{version}"
                f"/builds/{build_num}/downloads/{jar_name}"
            )

    async def _bungeecord_download_url(
        self, version: str, session: aiohttp.ClientSession
    ) -> Optional[str]:
        """Resolve BungeeCord download URL."""
        # BungeeCord doesn't have versioned builds per MC version
        # Return the latest build
        return "https://ci.md-5.net/job/BungeeCord/lastSuccessfulBuild/artifact/bootstrap/target/BungeeCord.jar"


# ──────────────────────────────────────────────
#  Server Type Registry
# ──────────────────────────────────────────────

SERVER_TYPES: Dict[str, ServerType] = {
    "vanilla": ServerType(
        name="Vanilla",
        software=ServerSoftware.VANILLA,
        api_base="https://launchermeta.mojang.com",
        plugin_platforms=[],
        mod_sources=[],
        plugin_sources=[],
        min_java=17,
        recommended_java=21,
        supports_plugins=False,
        supports_mods=False,
        description="Official Mojang server – no plugin or mod support",
    ),
    "paper": ServerType(
        name="Paper",
        software=ServerSoftware.PAPER,
        api_base="https://api.papermc.io",
        plugin_platforms=[PluginPlatform.BUKKIT, PluginPlatform.SPIGOT, PluginPlatform.PAPER],
        mod_sources=[],
        plugin_sources=["spigotmc", "bukkit", "hangar", "modrinth"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=False,
        description="High-performance Spigot fork with async chunk loading & extensive API",
    ),
    "spigot": ServerType(
        name="Spigot",
        software=ServerSoftware.SPIGOT,
        api_base="https://hub.spigotmc.org",
        plugin_platforms=[PluginPlatform.BUKKIT, PluginPlatform.SPIGOT],
        mod_sources=[],
        plugin_sources=["spigotmc", "bukkit"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=False,
        description="Optimized CraftBukkit fork – the most popular server software",
    ),
    "purpur": ServerType(
        name="Purpur",
        software=ServerSoftware.PURPUR,
        api_base="https://api.purpurmc.org",
        plugin_platforms=[PluginPlatform.BUKKIT, PluginPlatform.SPIGOT, PluginPlatform.PAPER],
        mod_sources=[],
        plugin_sources=["hangar", "spigotmc", "bukkit", "modrinth"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=False,
        description="Paper fork with extra gameplay configuration & features",
    ),
    "fabric": ServerType(
        name="Fabric",
        software=ServerSoftware.FABRIC,
        api_base="https://meta.fabricmc.net",
        plugin_platforms=[PluginPlatform.FABRIC],
        mod_sources=["modrinth", "curseforge"],
        plugin_sources=["modrinth"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=True,
        description="Lightweight, modular modding platform",
    ),
    "forge": ServerType(
        name="Forge",
        software=ServerSoftware.FORGE,
        api_base="https://files.minecraftforge.net",
        plugin_platforms=[PluginPlatform.FORGE],
        mod_sources=["curseforge", "modrinth"],
        plugin_sources=[],
        min_java=17,
        recommended_java=21,
        supports_plugins=False,
        supports_mods=True,
        description="Community-driven modding platform for large modpacks",
        requires_auth=False,
    ),
    "quilt": ServerType(
        name="Quilt",
        software=ServerSoftware.QUILT,
        api_base="https://meta.quiltmc.org",
        plugin_platforms=[PluginPlatform.QUILT],
        mod_sources=["modrinth"],
        plugin_sources=["modrinth"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=True,
        description="Modern modding API – fork of Fabric with improved tooling",
    ),
    "velocity": ServerType(
        name="Velocity",
        software=ServerSoftware.VELOCITY,
        api_base="https://api.papermc.io",
        plugin_platforms=[PluginPlatform.VELOCITY],
        mod_sources=[],
        plugin_sources=["hangar"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=False,
        description="Modern, high-performance proxy server for multi-server networks",
    ),
    "bungeecord": ServerType(
        name="BungeeCord",
        software=ServerSoftware.BUNGEECORD,
        api_base="https://ci.md-5.net",
        plugin_platforms=[PluginPlatform.BUNGEECORD],
        mod_sources=[],
        plugin_sources=["spigotmc"],
        min_java=17,
        recommended_java=21,
        supports_plugins=True,
        supports_mods=False,
        description="Legacy proxy server for multi-server networks",
    ),
}


# ──────────────────────────────────────────────
#  Public API Functions
# ──────────────────────────────────────────────

def get_server_type(name: str) -> Optional[ServerType]:
    """
    Look up a ServerType by name (case-insensitive).

    Args:
        name: Server type name (e.g. "paper", "fabric")

    Returns:
        ServerType or None if not found
    """
    return SERVER_TYPES.get(name.lower())


def get_all_server_types() -> List[ServerType]:
    """
    Return all registered server types.

    Returns:
        List of all ServerType instances
    """
    return list(SERVER_TYPES.values())


# Backward-compat alias
def list_server_types() -> List[ServerType]:
    """Alias for get_all_server_types (backward compatibility)."""
    return get_all_server_types()


async def download_server_software(
    server_type: str,
    version: str,
    dest_path: str | Path,
    session: aiohttp.ClientSession,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Result:
    """
    Download server software to a file.

    Args:
        server_type:       Server type name (e.g. "paper")
        version:           Minecraft version (e.g. "1.20.4")
        dest_path:         Destination file path
        session:           aiohttp session
        progress_callback: Optional callback(downloaded, total)

    Returns:
        Result with download status and file path
    """
    stype = get_server_type(server_type)
    if not stype:
        return Result.fail(
            f"Unknown server type: {server_type}",
            error=f"Valid types: {', '.join(SERVER_TYPES.keys())}",
        )

    return await stype.download_server(version, dest_path, session, progress_callback)


async def get_available_versions(
    server_type: str,
    session: aiohttp.ClientSession,
) -> List[str]:
    """
    Get list of available MC versions for a server type.

    Args:
        server_type: Server type name (e.g. "paper")
        session:     aiohttp session

    Returns:
        List of version strings, newest first
    """
    stype = get_server_type(server_type)
    if not stype:
        logger.error("Unknown server type: %s", server_type)
        return []

    return await stype.get_available_versions(session)


async def is_version_supported(
    server_type: str,
    version: str,
    session: aiohttp.ClientSession,
) -> bool:
    """
    Check if a specific version is available for a server type.

    Args:
        server_type: Server type name (e.g. "paper")
        version:     Minecraft version (e.g. "1.20.4")
        session:     aiohttp session

    Returns:
        True if the version is supported
    """
    stype = get_server_type(server_type)
    if not stype:
        return False

    return await stype.is_version_supported(version, session)
