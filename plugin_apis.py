"""
plugin_apis.py
==============
API clients for major Minecraft plugin/mod repositories.

Supported platforms:
  - **Modrinth**    – https://api.modrinth.com/v2
  - **Hangar**      – https://hangar.papermc.io/api/v1
  - **SpigotMC**    – https://api.spiget.org/v2 (Spiget mirror)
  - **CurseForge**  – https://api.curseforge.com/v1

Each client exposes:
  - search(query, …) → list of plugin results
  - get_plugin_info(plugin_id) → detailed info + dependencies
  - get_versions(plugin_id, …) → list of available versions
  - get_download_url(plugin_id, version_id) → download URL string
  - get_dependencies(plugin_id) → list of dependency names

Results are cached in-memory for 1 hour to reduce API load.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  In-Memory Cache (1 hour TTL)
# ──────────────────────────────────────────────

class _Cache:
    """Simple TTL cache for API responses."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._store: Dict[str, tuple[float, Any]] = {}
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.time() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()


_cache = _Cache(ttl_seconds=3600)


# ──────────────────────────────────────────────
#  Common Data Structures
# ──────────────────────────────────────────────

@dataclass
class PluginSearchResult:
    """Normalised search result returned by all API clients."""

    id: str
    name: str
    description: str
    author: str
    downloads: int
    rating: float = 0.0
    icon_url: Optional[str] = None
    source: str = ""                     # "modrinth", "hangar", "spigotmc", "curseforge"
    page_url: str = ""
    categories: List[str] = field(default_factory=list)
    mc_versions: List[str] = field(default_factory=list)


@dataclass
class PluginVersion:
    """Normalised version entry."""

    id: str
    version_number: str
    mc_versions: List[str] = field(default_factory=list)
    download_url: Optional[str] = None
    filename: Optional[str] = None
    release_date: Optional[str] = None
    channel: str = "release"             # release | beta | alpha
    dependencies: List[str] = field(default_factory=list)
    file_size: int = 0


@dataclass
class PluginInfo:
    """Detailed plugin information."""

    id: str
    name: str
    description: str
    long_description: str = ""
    author: str = ""
    authors: List[str] = field(default_factory=list)
    downloads: int = 0
    rating: float = 0.0
    icon_url: Optional[str] = None
    source: str = ""
    page_url: str = ""
    categories: List[str] = field(default_factory=list)
    mc_versions: List[str] = field(default_factory=list)
    versions: List[PluginVersion] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    optional_dependencies: List[str] = field(default_factory=list)
    license: str = ""
    source_url: str = ""
    issues_url: str = ""
    wiki_url: str = ""
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PluginDependency:
    """Plugin dependency information."""

    name: str
    plugin_id: str = ""
    required: bool = True
    version_range: str = ""
    source: str = ""


# ──────────────────────────────────────────────
#  Modrinth Client
# ──────────────────────────────────────────────

class ModrinthAPI:
    """Client for the Modrinth API v2."""

    BASE = "https://api.modrinth.com/v2"
    HEADERS = {"User-Agent": "MinecraftServerManager/1.0"}

    async def search(
        self,
        query: str,
        session: aiohttp.ClientSession,
        *,
        limit: int = 20,
        mc_version: Optional[str] = None,
        server_type: Optional[str] = None,
    ) -> List[PluginSearchResult]:
        """Search Modrinth for plugins/mods."""
        cache_key = f"modrinth:search:{query}:{mc_version}:{server_type}:{limit}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            "query": query,
            "limit": limit,
        }

        facets = self._build_facets(mc_version, server_type)
        if facets:
            params["facets"] = facets

        try:
            async with session.get(
                f"{self.BASE}/search", params=params, headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Modrinth search returned %d", resp.status)
                    return []
                data = await resp.json()

            results: List[PluginSearchResult] = []
            for hit in data.get("hits", []):
                results.append(PluginSearchResult(
                    id=hit["project_id"],
                    name=hit.get("title", ""),
                    description=hit.get("description", ""),
                    author=hit.get("author", ""),
                    downloads=hit.get("downloads", 0),
                    rating=0.0,
                    icon_url=hit.get("icon_url"),
                    source="modrinth",
                    page_url=f"https://modrinth.com/plugin/{hit.get('slug', '')}",
                    categories=hit.get("categories", []),
                    mc_versions=hit.get("versions", []),
                ))

            _cache.set(cache_key, results)
            return results

        except Exception as exc:
            logger.error("Modrinth search error: %s", exc)
            return []

    async def get_plugin_info(
        self,
        project_id: str,
        session: aiohttp.ClientSession,
    ) -> Optional[PluginInfo]:
        """Get detailed plugin information from Modrinth."""
        cache_key = f"modrinth:info:{project_id}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with session.get(
                f"{self.BASE}/project/{project_id}", headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            # Get team/authors
            authors = []
            team_id = data.get("team")
            if team_id:
                try:
                    async with session.get(
                        f"{self.BASE}/team/{team_id}/members", headers=self.HEADERS,
                    ) as tresp:
                        if tresp.status == 200:
                            members = await tresp.json()
                            authors = [
                                m.get("user", {}).get("username", "")
                                for m in members
                                if m.get("user", {}).get("username")
                            ]
                except Exception:
                    pass

            info = PluginInfo(
                id=data.get("id", project_id),
                name=data.get("title", ""),
                description=data.get("description", ""),
                long_description=data.get("body", ""),
                author=authors[0] if authors else "",
                authors=authors,
                downloads=data.get("downloads", 0),
                icon_url=data.get("icon_url"),
                source="modrinth",
                page_url=f"https://modrinth.com/plugin/{data.get('slug', '')}",
                categories=data.get("categories", []),
                mc_versions=data.get("game_versions", []),
                license=data.get("license", {}).get("id", "") if isinstance(data.get("license"), dict) else str(data.get("license", "")),
                source_url=data.get("source_url", ""),
                issues_url=data.get("issues_url", ""),
                wiki_url=data.get("wiki_url", ""),
                created_at=data.get("published", ""),
                updated_at=data.get("updated", ""),
            )

            _cache.set(cache_key, info)
            return info

        except Exception as exc:
            logger.error("Modrinth get_plugin_info error: %s", exc)
            return None

    async def get_versions(
        self,
        project_id: str,
        session: aiohttp.ClientSession,
        *,
        mc_version: Optional[str] = None,
        loader: Optional[str] = None,
    ) -> List[PluginVersion]:
        """Get available versions for a Modrinth project."""
        cache_key = f"modrinth:versions:{project_id}:{mc_version}:{loader}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, str] = {}
        if mc_version:
            params["game_versions"] = f'["{mc_version}"]'
        if loader:
            params["loaders"] = f'["{loader}"]'

        try:
            async with session.get(
                f"{self.BASE}/project/{project_id}/version",
                params=params, headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            versions: List[PluginVersion] = []
            for v in data:
                primary_file = v.get("files", [{}])[0] if v.get("files") else {}
                deps = [
                    d.get("project_id", "")
                    for d in v.get("dependencies", [])
                    if d.get("dependency_type") == "required"
                ]
                versions.append(PluginVersion(
                    id=v["id"],
                    version_number=v.get("version_number", ""),
                    mc_versions=v.get("game_versions", []),
                    download_url=primary_file.get("url"),
                    filename=primary_file.get("filename"),
                    release_date=v.get("date_published"),
                    channel=v.get("version_type", "release"),
                    dependencies=deps,
                    file_size=primary_file.get("size", 0),
                ))

            _cache.set(cache_key, versions)
            return versions

        except Exception as exc:
            logger.error("Modrinth get_versions error: %s", exc)
            return []

    async def get_download_url(
        self, project_id: str, version_id: str, session: aiohttp.ClientSession,
    ) -> Optional[str]:
        """Resolve the direct download URL for a specific version."""
        try:
            async with session.get(
                f"{self.BASE}/version/{version_id}", headers=self.HEADERS,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                files = data.get("files", [])
                if files:
                    return files[0].get("url")
        except Exception as exc:
            logger.error("Modrinth download URL error: %s", exc)
        return None

    async def get_dependencies(
        self,
        project_id: str,
        session: aiohttp.ClientSession,
        mc_version: Optional[str] = None,
    ) -> List[PluginDependency]:
        """Get plugin dependencies from the latest version."""
        versions = await self.get_versions(
            project_id, session, mc_version=mc_version
        )
        if not versions:
            return []

        deps: List[PluginDependency] = []
        latest = versions[0]

        # Also fetch from project info for any metadata deps
        try:
            async with session.get(
                f"{self.BASE}/version/{latest.id}", headers=self.HEADERS,
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for d in data.get("dependencies", []):
                        dep_type = d.get("dependency_type", "required")
                        deps.append(PluginDependency(
                            name=d.get("project_id", ""),
                            plugin_id=d.get("project_id", ""),
                            required=dep_type == "required",
                            version_range=d.get("version_id", ""),
                            source="modrinth",
                        ))
        except Exception as exc:
            logger.error("Modrinth dependencies error: %s", exc)

        return deps

    @staticmethod
    def _build_facets(
        mc_version: Optional[str], server_type: Optional[str]
    ) -> str:
        """Build Modrinth facet filter string."""
        parts: List[str] = []

        # Project type: plugin or mod
        parts.append('["project_type:plugin"]')

        if mc_version:
            parts.append(f'["versions:{mc_version}"]')
        if server_type:
            loader = server_type.lower()
            if loader in ("paper", "spigot", "purpur"):
                loader = "paper"
            parts.append(f'["categories:{loader}"]')

        if len(parts) <= 1:
            return ""
        return "[" + ",".join(parts) + "]"


# ──────────────────────────────────────────────
#  Hangar Client (PaperMC)
# ──────────────────────────────────────────────

class HangarAPI:
    """Client for the Hangar (PaperMC) API v1."""

    BASE = "https://hangar.papermc.io/api/v1"

    async def search(
        self,
        query: str,
        session: aiohttp.ClientSession,
        *,
        limit: int = 20,
        mc_version: Optional[str] = None,
    ) -> List[PluginSearchResult]:
        """Search Hangar for plugins."""
        cache_key = f"hangar:search:{query}:{mc_version}:{limit}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            "q": query,
            "limit": limit,
            "sort": "-downloads",
        }
        if mc_version:
            params["version"] = mc_version

        try:
            async with session.get(
                f"{self.BASE}/projects", params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Hangar search returned %d", resp.status)
                    return []
                data = await resp.json()

            results: List[PluginSearchResult] = []
            for project in data.get("result", []):
                namespace = project.get("namespace", {})
                slug = namespace.get("slug", "")
                owner = namespace.get("owner", "")
                stats = project.get("stats", {})

                results.append(PluginSearchResult(
                    id=slug,
                    name=project.get("name", ""),
                    description=project.get("description", ""),
                    author=owner,
                    downloads=stats.get("downloads", 0),
                    rating=stats.get("stars", 0),
                    icon_url=project.get("avatarUrl"),
                    source="hangar",
                    page_url=f"https://hangar.papermc.io/{owner}/{slug}",
                    categories=[project.get("category", "")],
                ))

            _cache.set(cache_key, results)
            return results

        except Exception as exc:
            logger.error("Hangar search error: %s", exc)
            return []

    async def get_plugin_info(
        self,
        project_slug: str,
        session: aiohttp.ClientSession,
    ) -> Optional[PluginInfo]:
        """Get detailed plugin info from Hangar."""
        cache_key = f"hangar:info:{project_slug}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with session.get(
                f"{self.BASE}/projects/{project_slug}",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            namespace = data.get("namespace", {})
            stats = data.get("stats", {})
            settings = data.get("settings", {})

            info = PluginInfo(
                id=namespace.get("slug", project_slug),
                name=data.get("name", ""),
                description=data.get("description", ""),
                long_description=data.get("description", ""),
                author=namespace.get("owner", ""),
                authors=[namespace.get("owner", "")],
                downloads=stats.get("downloads", 0),
                rating=stats.get("stars", 0),
                icon_url=data.get("avatarUrl"),
                source="hangar",
                page_url=f"https://hangar.papermc.io/{namespace.get('owner', '')}/{namespace.get('slug', '')}",
                categories=[data.get("category", "")],
                license=settings.get("license", {}).get("type", "") if isinstance(settings.get("license"), dict) else "",
                source_url=settings.get("links", {}).get("source", ""),
                issues_url=settings.get("links", {}).get("issues", ""),
                wiki_url=settings.get("links", {}).get("wiki", ""),
                created_at=data.get("createdAt", ""),
            )

            _cache.set(cache_key, info)
            return info

        except Exception as exc:
            logger.error("Hangar get_plugin_info error: %s", exc)
            return None

    async def get_versions(
        self,
        project_slug: str,
        session: aiohttp.ClientSession,
        *,
        mc_version: Optional[str] = None,
    ) -> List[PluginVersion]:
        """Get available versions for a Hangar project."""
        cache_key = f"hangar:versions:{project_slug}:{mc_version}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {"limit": 25}
        if mc_version:
            params["platformVersion"] = mc_version

        try:
            async with session.get(
                f"{self.BASE}/projects/{project_slug}/versions",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            versions: List[PluginVersion] = []
            for v in data.get("result", []):
                deps = []
                for platform_deps in v.get("pluginDependencies", {}).values():
                    for dep in platform_deps:
                        if dep.get("required", False):
                            deps.append(dep.get("name", ""))

                versions.append(PluginVersion(
                    id=v.get("name", ""),
                    version_number=v.get("name", ""),
                    mc_versions=self._extract_mc_versions(v),
                    download_url=None,  # Resolved separately
                    release_date=v.get("createdAt"),
                    channel=v.get("channel", {}).get("name", "release"),
                    dependencies=deps,
                ))

            _cache.set(cache_key, versions)
            return versions

        except Exception as exc:
            logger.error("Hangar get_versions error: %s", exc)
            return []

    async def get_download_url(
        self,
        project_slug: str,
        version_name: str,
        session: aiohttp.ClientSession,
        platform: str = "PAPER",
    ) -> Optional[str]:
        """Resolve the download URL for a Hangar version."""
        url = f"{self.BASE}/projects/{project_slug}/versions/{version_name}/{platform}/download"
        try:
            async with session.head(
                url, allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (200, 301, 302, 303):
                    return resp.headers.get("Location", url)
        except Exception as exc:
            logger.error("Hangar download URL error: %s", exc)
        return url  # Direct URL usually works

    async def get_dependencies(
        self,
        project_slug: str,
        session: aiohttp.ClientSession,
        mc_version: Optional[str] = None,
    ) -> List[PluginDependency]:
        """Get plugin dependencies from versions."""
        versions = await self.get_versions(project_slug, session, mc_version=mc_version)
        if not versions:
            return []

        deps: List[PluginDependency] = []
        for dep_name in versions[0].dependencies:
            deps.append(PluginDependency(
                name=dep_name,
                required=True,
                source="hangar",
            ))
        return deps

    @staticmethod
    def _extract_mc_versions(version_data: dict) -> List[str]:
        """Extract MC version list from a Hangar version response."""
        mc_versions: List[str] = []
        for platform_deps in version_data.get("platformDependencies", {}).values():
            mc_versions.extend(platform_deps)
        return list(set(mc_versions))


# ──────────────────────────────────────────────
#  SpigotMC Client (via Spiget API)
# ──────────────────────────────────────────────

class SpigotAPI:
    """Client for the Spiget API (SpigotMC resource mirror)."""

    BASE = "https://api.spiget.org/v2"

    async def search(
        self,
        query: str,
        session: aiohttp.ClientSession,
        *,
        limit: int = 20,
        mc_version: Optional[str] = None,
    ) -> List[PluginSearchResult]:
        """Search SpigotMC for resources."""
        cache_key = f"spigot:search:{query}:{limit}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {"size": limit, "sort": "-downloads"}

        try:
            async with session.get(
                f"{self.BASE}/search/resources/{query}",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("Spiget search returned %d", resp.status)
                    return []
                data = await resp.json()

            results: List[PluginSearchResult] = []
            for resource in data:
                rid = str(resource.get("id", ""))
                rating_data = resource.get("rating", {})

                # Decode base64 name if present
                name = resource.get("name", "")

                results.append(PluginSearchResult(
                    id=rid,
                    name=name,
                    description=resource.get("tag", ""),
                    author=str(resource.get("author", {}).get("id", "")),
                    downloads=resource.get("downloads", 0),
                    rating=float(rating_data.get("average", 0)) if isinstance(rating_data, dict) else 0.0,
                    icon_url=resource.get("icon", {}).get("url", ""),
                    source="spigotmc",
                    page_url=f"https://www.spigotmc.org/resources/{rid}/",
                    categories=[str(resource.get("category", {}).get("id", ""))],
                    mc_versions=resource.get("testedVersions", []),
                ))

            _cache.set(cache_key, results)
            return results

        except Exception as exc:
            logger.error("Spiget search error: %s", exc)
            return []

    async def get_plugin_info(
        self,
        resource_id: str,
        session: aiohttp.ClientSession,
    ) -> Optional[PluginInfo]:
        """Get detailed plugin info from SpigotMC."""
        cache_key = f"spigot:info:{resource_id}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with session.get(
                f"{self.BASE}/resources/{resource_id}",
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

            rating_data = data.get("rating", {})
            author_id = str(data.get("author", {}).get("id", ""))

            info = PluginInfo(
                id=str(data.get("id", resource_id)),
                name=data.get("name", ""),
                description=data.get("tag", ""),
                long_description="",  # Spiget doesn't provide long descriptions easily
                author=author_id,
                downloads=data.get("downloads", 0),
                rating=float(rating_data.get("average", 0)) if isinstance(rating_data, dict) else 0.0,
                icon_url=data.get("icon", {}).get("url", ""),
                source="spigotmc",
                page_url=f"https://www.spigotmc.org/resources/{resource_id}/",
                categories=[str(data.get("category", {}).get("id", ""))],
                mc_versions=data.get("testedVersions", []),
                created_at=str(data.get("releaseDate", "")),
                updated_at=str(data.get("updateDate", "")),
            )

            _cache.set(cache_key, info)
            return info

        except Exception as exc:
            logger.error("Spiget get_plugin_info error: %s", exc)
            return None

    async def get_versions(
        self,
        resource_id: str,
        session: aiohttp.ClientSession,
    ) -> List[PluginVersion]:
        """Get available versions for a Spiget resource."""
        cache_key = f"spigot:versions:{resource_id}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with session.get(
                f"{self.BASE}/resources/{resource_id}/versions",
                params={"size": 25, "sort": "-releaseDate"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            versions: List[PluginVersion] = []
            for v in data:
                vid = str(v.get("id", ""))
                versions.append(PluginVersion(
                    id=vid,
                    version_number=v.get("name", ""),
                    download_url=f"{self.BASE}/resources/{resource_id}/versions/{vid}/download",
                    release_date=str(v.get("releaseDate", "")),
                ))

            _cache.set(cache_key, versions)
            return versions

        except Exception as exc:
            logger.error("Spiget get_versions error: %s", exc)
            return []

    async def get_download_url(
        self,
        resource_id: str,
        version_id: str = "latest",
        session: aiohttp.ClientSession = None,
    ) -> Optional[str]:
        """Return the download URL for a Spiget resource."""
        if version_id == "latest":
            return f"{self.BASE}/resources/{resource_id}/download"
        return f"{self.BASE}/resources/{resource_id}/versions/{version_id}/download"

    async def get_dependencies(
        self,
        resource_id: str,
        session: aiohttp.ClientSession,
    ) -> List[PluginDependency]:
        """Get (limited) dependency info from SpigotMC."""
        # Spiget doesn't have a great dependencies API
        # We return an empty list; real deps are extracted from plugin.yml after install
        return []


# ──────────────────────────────────────────────
#  CurseForge Client
# ──────────────────────────────────────────────

class CurseForgeAPI:
    """
    Client for the CurseForge API v1.

    Requires an API key set via CURSEFORGE_API_KEY environment variable.
    Get one at: https://console.curseforge.com/
    """

    BASE = "https://api.curseforge.com/v1"
    GAME_ID_MINECRAFT = 432  # CurseForge game ID for Minecraft

    def __init__(self, api_key: Optional[str] = None) -> None:
        import os
        self.api_key = api_key or os.environ.get("CURSEFORGE_API_KEY", "")

    def _headers(self) -> Dict[str, str]:
        h: Dict[str, str] = {"User-Agent": "MinecraftServerManager/1.0"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    async def search(
        self,
        query: str,
        session: aiohttp.ClientSession,
        *,
        limit: int = 20,
        mc_version: Optional[str] = None,
        server_type: Optional[str] = None,
    ) -> List[PluginSearchResult]:
        """Search CurseForge for Minecraft mods/plugins."""
        if not self.api_key:
            logger.debug("CurseForge API key not set, skipping search")
            return []

        cache_key = f"curseforge:search:{query}:{mc_version}:{limit}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {
            "gameId": self.GAME_ID_MINECRAFT,
            "searchFilter": query,
            "pageSize": limit,
            "sortField": 2,  # Sort by popularity
            "sortOrder": "desc",
            "classId": 6,    # Mods class
        }
        if mc_version:
            params["gameVersion"] = mc_version

        # Map server type to modloader
        loader_map = {"forge": 1, "fabric": 4, "quilt": 5}
        if server_type and server_type.lower() in loader_map:
            params["modLoaderType"] = loader_map[server_type.lower()]

        try:
            async with session.get(
                f"{self.BASE}/mods/search",
                params=params, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning("CurseForge search returned %d", resp.status)
                    return []
                data = await resp.json()

            results: List[PluginSearchResult] = []
            for mod in data.get("data", []):
                authors = [a.get("name", "") for a in mod.get("authors", [])]
                categories = [c.get("name", "") for c in mod.get("categories", [])]

                results.append(PluginSearchResult(
                    id=str(mod.get("id", "")),
                    name=mod.get("name", ""),
                    description=mod.get("summary", ""),
                    author=authors[0] if authors else "",
                    downloads=mod.get("downloadCount", 0),
                    rating=mod.get("rating", 0.0),
                    icon_url=mod.get("logo", {}).get("url") if mod.get("logo") else None,
                    source="curseforge",
                    page_url=mod.get("links", {}).get("websiteUrl", ""),
                    categories=categories,
                ))

            _cache.set(cache_key, results)
            return results

        except Exception as exc:
            logger.error("CurseForge search error: %s", exc)
            return []

    async def get_plugin_info(
        self,
        mod_id: str,
        session: aiohttp.ClientSession,
    ) -> Optional[PluginInfo]:
        """Get detailed mod info from CurseForge."""
        if not self.api_key:
            return None

        cache_key = f"curseforge:info:{mod_id}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            async with session.get(
                f"{self.BASE}/mods/{mod_id}",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = (await resp.json()).get("data", {})

            authors = [a.get("name", "") for a in data.get("authors", [])]
            categories = [c.get("name", "") for c in data.get("categories", [])]

            info = PluginInfo(
                id=str(data.get("id", mod_id)),
                name=data.get("name", ""),
                description=data.get("summary", ""),
                long_description="",  # Would need another API call
                author=authors[0] if authors else "",
                authors=authors,
                downloads=data.get("downloadCount", 0),
                rating=data.get("rating", 0.0),
                icon_url=data.get("logo", {}).get("url") if data.get("logo") else None,
                source="curseforge",
                page_url=data.get("links", {}).get("websiteUrl", ""),
                categories=categories,
                source_url=data.get("links", {}).get("sourceUrl", ""),
                issues_url=data.get("links", {}).get("issuesUrl", ""),
                wiki_url=data.get("links", {}).get("wikiUrl", ""),
                created_at=data.get("dateCreated", ""),
                updated_at=data.get("dateModified", ""),
            )

            _cache.set(cache_key, info)
            return info

        except Exception as exc:
            logger.error("CurseForge get_plugin_info error: %s", exc)
            return None

    async def get_versions(
        self,
        mod_id: str,
        session: aiohttp.ClientSession,
        *,
        mc_version: Optional[str] = None,
    ) -> List[PluginVersion]:
        """Get available versions for a CurseForge mod."""
        if not self.api_key:
            return []

        cache_key = f"curseforge:versions:{mod_id}:{mc_version}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        params: Dict[str, Any] = {"pageSize": 25}
        if mc_version:
            params["gameVersion"] = mc_version

        try:
            async with session.get(
                f"{self.BASE}/mods/{mod_id}/files",
                params=params, headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

            # Release type mapping
            type_map = {1: "release", 2: "beta", 3: "alpha"}

            versions: List[PluginVersion] = []
            for f in data.get("data", []):
                deps = [
                    str(d.get("modId", ""))
                    for d in f.get("dependencies", [])
                    if d.get("relationType") == 3  # Required dependency
                ]
                versions.append(PluginVersion(
                    id=str(f.get("id", "")),
                    version_number=f.get("displayName", f.get("fileName", "")),
                    mc_versions=f.get("gameVersions", []),
                    download_url=f.get("downloadUrl"),
                    filename=f.get("fileName"),
                    release_date=f.get("fileDate"),
                    channel=type_map.get(f.get("releaseType", 1), "release"),
                    dependencies=deps,
                    file_size=f.get("fileLength", 0),
                ))

            _cache.set(cache_key, versions)
            return versions

        except Exception as exc:
            logger.error("CurseForge get_versions error: %s", exc)
            return []

    async def get_download_url(
        self,
        mod_id: str,
        file_id: str,
        session: aiohttp.ClientSession,
    ) -> Optional[str]:
        """Resolve CurseForge download URL."""
        if not self.api_key:
            return None

        try:
            async with session.get(
                f"{self.BASE}/mods/{mod_id}/files/{file_id}/download-url",
                headers=self._headers(),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("data")
        except Exception as exc:
            logger.error("CurseForge download URL error: %s", exc)
        return None

    async def get_dependencies(
        self,
        mod_id: str,
        session: aiohttp.ClientSession,
        mc_version: Optional[str] = None,
    ) -> List[PluginDependency]:
        """Get mod dependencies from CurseForge."""
        versions = await self.get_versions(mod_id, session, mc_version=mc_version)
        if not versions:
            return []

        deps: List[PluginDependency] = []
        for dep_id in versions[0].dependencies:
            deps.append(PluginDependency(
                name=dep_id,
                plugin_id=dep_id,
                required=True,
                source="curseforge",
            ))
        return deps


# ──────────────────────────────────────────────
#  Unified Search Helpers
# ──────────────────────────────────────────────

# Server type → which API sources to use
_SERVER_SOURCE_MAP: Dict[str, List[str]] = {
    "paper":      ["modrinth", "hangar", "spigotmc"],
    "spigot":     ["spigotmc", "modrinth"],
    "purpur":     ["hangar", "modrinth", "spigotmc"],
    "fabric":     ["modrinth", "curseforge"],
    "forge":      ["curseforge", "modrinth"],
    "quilt":      ["modrinth"],
    "vanilla":    [],
    "velocity":   ["hangar", "modrinth"],
    "bungeecord": ["spigotmc"],
}


async def search_plugins(
    query: str,
    server_type: str,
    mc_version: str,
    session: aiohttp.ClientSession,
    *,
    limit: int = 20,
) -> List[PluginSearchResult]:
    """
    Search for plugins across multiple sources based on server type.

    Args:
        query:       Search query
        server_type: Server software (paper, fabric, forge, etc.)
        mc_version:  Minecraft version (e.g. "1.20.4")
        session:     aiohttp session
        limit:       Max results per source

    Returns:
        Combined list sorted by downloads (most popular first)
    """
    sources = _SERVER_SOURCE_MAP.get(server_type.lower(), ["modrinth"])
    all_results: List[PluginSearchResult] = []

    modrinth = ModrinthAPI()
    hangar = HangarAPI()
    spigot = SpigotAPI()
    curseforge = CurseForgeAPI()

    if "modrinth" in sources:
        results = await modrinth.search(
            query, session, limit=limit, mc_version=mc_version,
            server_type=server_type,
        )
        all_results.extend(results)

    if "hangar" in sources:
        results = await hangar.search(
            query, session, limit=limit, mc_version=mc_version,
        )
        all_results.extend(results)

    if "spigotmc" in sources:
        results = await spigot.search(
            query, session, limit=limit, mc_version=mc_version,
        )
        all_results.extend(results)

    if "curseforge" in sources:
        results = await curseforge.search(
            query, session, limit=limit, mc_version=mc_version,
            server_type=server_type,
        )
        all_results.extend(results)

    # Sort by downloads (most popular first)
    all_results.sort(key=lambda r: r.downloads, reverse=True)
    return all_results


async def get_plugin_info(
    plugin_id: str,
    source: str,
    session: aiohttp.ClientSession,
) -> Optional[PluginInfo]:
    """
    Get detailed plugin information from a specific source.

    Args:
        plugin_id: Plugin identifier on the source platform
        source:    Source platform ("modrinth", "hangar", "spigotmc", "curseforge")
        session:   aiohttp session
    """
    if source == "modrinth":
        return await ModrinthAPI().get_plugin_info(plugin_id, session)
    elif source == "hangar":
        return await HangarAPI().get_plugin_info(plugin_id, session)
    elif source == "spigotmc":
        return await SpigotAPI().get_plugin_info(plugin_id, session)
    elif source == "curseforge":
        return await CurseForgeAPI().get_plugin_info(plugin_id, session)
    return None


async def get_download_url(
    plugin_id: str,
    version_id: str,
    source: str,
    session: aiohttp.ClientSession,
) -> Optional[str]:
    """
    Get direct download URL for a plugin version.

    Args:
        plugin_id:  Plugin identifier
        version_id: Version identifier
        source:     Source platform
        session:    aiohttp session
    """
    if source == "modrinth":
        return await ModrinthAPI().get_download_url(plugin_id, version_id, session)
    elif source == "hangar":
        return await HangarAPI().get_download_url(plugin_id, version_id, session)
    elif source == "spigotmc":
        return await SpigotAPI().get_download_url(plugin_id, version_id, session)
    elif source == "curseforge":
        return await CurseForgeAPI().get_download_url(plugin_id, version_id, session)
    return None


async def get_plugin_versions(
    plugin_id: str,
    source: str,
    session: aiohttp.ClientSession,
    mc_version: Optional[str] = None,
) -> List[PluginVersion]:
    """
    Get all available versions for a plugin.

    Args:
        plugin_id:  Plugin identifier
        source:     Source platform
        session:    aiohttp session
        mc_version: Optional MC version filter
    """
    if source == "modrinth":
        return await ModrinthAPI().get_versions(plugin_id, session, mc_version=mc_version)
    elif source == "hangar":
        return await HangarAPI().get_versions(plugin_id, session, mc_version=mc_version)
    elif source == "spigotmc":
        return await SpigotAPI().get_versions(plugin_id, session)
    elif source == "curseforge":
        return await CurseForgeAPI().get_versions(plugin_id, session, mc_version=mc_version)
    return []


async def get_plugin_dependencies(
    plugin_id: str,
    source: str,
    session: aiohttp.ClientSession,
    mc_version: Optional[str] = None,
) -> List[str]:
    """
    Return list of required plugin dependencies.

    Args:
        plugin_id:  Plugin identifier
        source:     Source platform
        session:    aiohttp session
        mc_version: Optional MC version filter

    Returns:
        List of dependency names/IDs
    """
    deps: List[PluginDependency] = []

    if source == "modrinth":
        deps = await ModrinthAPI().get_dependencies(plugin_id, session, mc_version)
    elif source == "hangar":
        deps = await HangarAPI().get_dependencies(plugin_id, session, mc_version)
    elif source == "curseforge":
        deps = await CurseForgeAPI().get_dependencies(plugin_id, session, mc_version)

    return [d.name for d in deps if d.required]


def clear_cache() -> None:
    """Clear the API response cache."""
    _cache.clear()
