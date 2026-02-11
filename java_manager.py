"""
java_manager.py
===============
Comprehensive Java version management for the Minecraft server.

Capabilities:
  - Detect system-installed Java versions (Windows / Linux / macOS / Colab / IDX)
  - Download Eclipse Adoptium (Temurin) JDKs with progress
  - Install / uninstall / switch active Java version
  - Version-to-Minecraft compatibility mapping
  - Persist state to java_versions.json
  - Platform-specific path handling (registry, JAVA_HOME, common dirs)
  - Portable mode for cloud environments (Colab / IDX)

Cross-platform notes:
  Windows  – Program Files, JAVA_HOME, PATH
  Linux    – /usr/lib/jvm, /opt/java, SDKMAN, apt / yum detection
  macOS    – /Library/Java/JavaVirtualMachines, Homebrew, SDKMAN
  Colab    – /usr/lib/jvm  (pre-installed 11)
  IDX      – /usr/lib/jvm  (pre-installed 17)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────

ADOPTIUM_API = "https://api.adoptium.net/v3"

# Map platform.system() → Adoptium OS identifier
_OS_MAP: Dict[str, str] = {
    "Linux": "linux",
    "Darwin": "mac",
    "Windows": "windows",
}

# Map platform.machine() → Adoptium arch identifier
_ARCH_MAP: Dict[str, str] = {
    "x86_64": "x64",
    "AMD64": "x64",
    "x86": "x32",
    "i686": "x32",
    "i386": "x32",
    "aarch64": "aarch64",
    "arm64": "aarch64",
    "armv7l": "arm",
}

# Minecraft version → minimum Java version mapping (comprehensive)
_MC_JAVA_MAP: List[Tuple[Tuple[int, int], int]] = [
    # (major, minor_threshold) → java_version
    # Evaluated top-down; first match wins
    # MC 1.21+ → Java 21
    ((1, 21), 21),
    # MC 1.20.5+ → Java 21
    ((1, 20), 17),  # handled per-minor below
    # MC 1.17+ → Java 17
    ((1, 17), 17),
    # MC 1.12+ → Java 11  (some servers work with 8 but 11 recommended)
    ((1, 12), 11),
    # MC < 1.12 → Java 8
    ((0, 0), 8),
]

# Maximum Java version known to work with each MC range
_MC_JAVA_MAX: Dict[str, int] = {
    "1.8":  8,
    "1.12": 11,
    "1.16": 16,
    "1.17": 21,
    "1.18": 21,
    "1.19": 21,
    "1.20": 21,
    "1.21": 21,
}


# ──────────────────────────────────────────────
#  Result Object
# ──────────────────────────────────────────────

@dataclass
class Result:
    """Unified result for JavaManager operations."""

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
#  JavaVersion Dataclass
# ──────────────────────────────────────────────

@dataclass
class JavaVersion:
    """Detailed representation of a Java installation."""

    version: int                   # Major version (8, 11, 17, 21)
    path: str                      # Root JDK directory
    vendor: str = "unknown"        # adoptium | system | homebrew | sdkman | ...
    architecture: str = "x64"      # x64, aarch64, x32, arm
    full_version: str = ""         # e.g. "17.0.9+9"
    installed_at: str = ""         # ISO timestamp
    is_default: bool = False       # Whether this is the default Java
    source: str = "detected"       # detected | downloaded | manual

    @property
    def java_binary(self) -> str:
        """Return the full path to the ``java`` executable."""
        binary = "java.exe" if platform.system() == "Windows" else "java"
        # macOS Adoptium: Contents/Home/bin/java
        mac_path = os.path.join(self.path, "Contents", "Home", "bin", binary)
        if os.path.isfile(mac_path):
            return mac_path
        return os.path.join(self.path, "bin", binary)

    def is_valid(self) -> bool:
        """Return True if the java binary exists and is executable."""
        jb = self.java_binary
        return os.path.isfile(jb) and os.access(jb, os.X_OK)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "path": self.path,
            "vendor": self.vendor,
            "architecture": self.architecture,
            "full_version": self.full_version,
            "installed_at": self.installed_at,
            "is_default": self.is_default,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JavaVersion":
        return cls(
            version=data.get("version", 0),
            path=data.get("path", ""),
            vendor=data.get("vendor", "unknown"),
            architecture=data.get("architecture", "x64"),
            full_version=data.get("full_version", ""),
            installed_at=data.get("installed_at", ""),
            is_default=data.get("is_default", False),
            source=data.get("source", "detected"),
        )


# ──────────────────────────────────────────────
#  Backward-Compat Alias
# ──────────────────────────────────────────────
# server_manager.py & ui/java_panel.py use JavaInstallation
JavaInstallation = JavaVersion


# ──────────────────────────────────────────────
#  JavaManager
# ──────────────────────────────────────────────

class JavaManager:
    """
    Comprehensive Java version manager.

    Args:
        java_dir:            Directory where downloaded JDKs are stored
        java_versions_path:  Path to java_versions.json
    """

    # ================================================================
    #  INITIALIZATION
    # ================================================================

    def __init__(
        self,
        java_dir: str | Path,
        java_versions_path: str | Path,
    ) -> None:
        self.java_dir = Path(java_dir)
        self.java_versions_path = Path(java_versions_path)
        self.installations: List[JavaVersion] = []
        self.active: Optional[JavaVersion] = None

        # Platform info
        self._system = platform.system()   # Windows | Linux | Darwin
        self._machine = platform.machine() # AMD64, x86_64, aarch64, ...
        self._os_id = _OS_MAP.get(self._system, "linux")
        self._arch_id = _ARCH_MAP.get(self._machine, "x64")

        # Environment detection
        self._is_colab = self._detect_colab()
        self._is_idx = self._detect_idx()
        self._is_portable = self._is_colab or self._is_idx

        # Ensure directory exists
        self.java_dir.mkdir(parents=True, exist_ok=True)
        self._load_state()

        logger.info(
            "JavaManager init: system=%s arch=%s colab=%s idx=%s dir=%s",
            self._system, self._arch_id, self._is_colab, self._is_idx, self.java_dir,
        )

    # ================================================================
    #  JAVA DETECTION
    # ================================================================

    def get_installed_java_versions(self) -> List[JavaVersion]:
        """
        Search common installation paths and detect all Java installations.

        Scans:
          - PATH java
          - Common OS directories
          - JAVA_HOME
          - Downloaded JDKs in self.java_dir
          - Cloud environment paths (Colab / IDX)

        Returns:
            List of JavaVersion objects with version, path, architecture
        """
        found: List[JavaVersion] = []
        seen_paths: set = set()

        def _add(jv: JavaVersion) -> None:
            normalized = os.path.normpath(os.path.abspath(jv.path))
            if normalized not in seen_paths:
                seen_paths.add(normalized)
                found.append(jv)
                logger.info(
                    "Detected Java %d (%s, %s) at %s",
                    jv.version, jv.vendor, jv.full_version, jv.path,
                )

        # 1. PATH java
        system_java = self.get_system_java()
        if system_java:
            _add(system_java)

        # 2. JAVA_HOME
        java_home = os.environ.get("JAVA_HOME", "")
        if java_home and os.path.isdir(java_home):
            ver, full = self._get_java_version_full(
                self._java_bin_for_dir(java_home)
            )
            if ver:
                _add(JavaVersion(
                    version=ver, path=java_home, vendor="JAVA_HOME",
                    architecture=self._arch_id, full_version=full,
                    source="detected",
                ))

        # 3. Common OS directories
        for search_dir in self._common_java_dirs():
            if not os.path.isdir(search_dir):
                continue
            try:
                entries = os.listdir(search_dir)
            except PermissionError:
                continue
            for entry in sorted(entries):
                full_path = os.path.join(search_dir, entry)
                if not os.path.isdir(full_path):
                    continue
                binary = self._java_bin_for_dir(full_path)
                if os.path.isfile(binary):
                    ver, full = self._get_java_version_full(binary)
                    if ver:
                        vendor = self._guess_vendor(full_path, full)
                        _add(JavaVersion(
                            version=ver, path=full_path, vendor=vendor,
                            architecture=self._arch_id, full_version=full,
                            source="detected",
                        ))

        # 4. Downloaded JDKs in self.java_dir
        if self.java_dir.exists():
            for child in self.java_dir.iterdir():
                if child.is_dir():
                    # Could be java-17/ or jdk-17.0.9+8/
                    jdk_root = self._find_jdk_root(child)
                    binary = self._java_bin_for_dir(str(jdk_root))
                    if os.path.isfile(binary):
                        ver, full = self._get_java_version_full(binary)
                        if ver:
                            _add(JavaVersion(
                                version=ver, path=str(jdk_root), vendor="adoptium",
                                architecture=self._arch_id, full_version=full,
                                source="downloaded",
                            ))

        # 5. macOS: /usr/libexec/java_home
        if self._system == "Darwin":
            mac_installs = self._detect_macos_java_home()
            for jv in mac_installs:
                _add(jv)

        # Merge with existing installations (keep manual entries)
        for inst in found:
            norm = os.path.normpath(os.path.abspath(inst.path))
            if not any(
                os.path.normpath(os.path.abspath(i.path)) == norm
                for i in self.installations
            ):
                self.installations.append(inst)

        # Update existing entries with fresh info
        for inst in self.installations:
            norm = os.path.normpath(os.path.abspath(inst.path))
            for f in found:
                if os.path.normpath(os.path.abspath(f.path)) == norm:
                    inst.full_version = f.full_version or inst.full_version
                    inst.architecture = f.architecture or inst.architecture
                    break

        self._save_state()
        logger.info("Total detected: %d Java installations", len(found))
        return found

    # Backward-compat alias
    detect_system_java = get_installed_java_versions

    def get_system_java(self) -> Optional[JavaVersion]:
        """
        Check PATH for the java executable.

        Returns:
            JavaVersion if found, None otherwise
        """
        java_in_path = shutil.which("java")
        if not java_in_path:
            return None

        ver, full = self._get_java_version_full(java_in_path)
        if not ver:
            return None

        # Resolve to JDK root (java binary → bin/ → JDK root)
        install_path = str(Path(java_in_path).resolve().parent.parent)
        vendor = self._guess_vendor(install_path, full)

        return JavaVersion(
            version=ver,
            path=install_path,
            vendor=vendor,
            architecture=self._arch_id,
            full_version=full,
            source="detected",
        )

    def validate_java_installation(self, java_path: str) -> bool:
        """
        Validate a Java installation at the given path.

        Runs ``java -version`` and verifies the output contains a version.

        Args:
            java_path: Path to the JDK root directory or java binary
        """
        binary = java_path
        if os.path.isdir(java_path):
            binary = self._java_bin_for_dir(java_path)

        if not os.path.isfile(binary):
            logger.warning("Java binary not found: %s", binary)
            return False

        ver, _ = self._get_java_version_full(binary)
        if ver:
            logger.info("Valid Java %d at %s", ver, binary)
            return True

        logger.warning("Invalid Java at %s", binary)
        return False

    def get_java_version_from_path(self, java_path: str) -> Optional[int]:
        """
        Run ``java -version`` on the given path and extract the major version.

        Args:
            java_path: Path to java binary or JDK root

        Returns:
            Major version (8, 11, 17, 21) or None
        """
        binary = java_path
        if os.path.isdir(java_path):
            binary = self._java_bin_for_dir(java_path)

        ver, _ = self._get_java_version_full(binary)
        return ver

    # ================================================================
    #  VERSION MAPPING
    # ================================================================

    @staticmethod
    def get_required_java(minecraft_version: str) -> int:
        """
        Return the minimum Java version required for a Minecraft version.

        Mapping:
            MC 1.21+      → Java 21
            MC 1.20.5+    → Java 21
            MC 1.17-1.20.4→ Java 17
            MC 1.12-1.16  → Java 11
            MC < 1.12     → Java 8
        """
        try:
            parts = minecraft_version.split(".")
            major = int(parts[1]) if len(parts) >= 2 else 0
            minor = int(parts[2]) if len(parts) >= 3 else 0

            if major >= 21:
                return 21
            if major == 20 and minor >= 5:
                return 21
            if major >= 17:
                return 17
            if major >= 12:
                return 11
            return 8
        except (ValueError, IndexError):
            return 17  # Safe default

    # Backward-compat alias used by server_manager.py
    def get_required_version(self, mc_version: str) -> int:
        """Alias for get_required_java (backward compat)."""
        return self.get_required_java(mc_version)

    @staticmethod
    def get_recommended_java(minecraft_version: str) -> int:
        """
        Return the recommended Java version for a Minecraft version.

        Usually same as required, but prefers LTS releases.
        """
        required = JavaManager.get_required_java(minecraft_version)
        # Recommend the closest LTS: 8, 11, 17, 21
        lts = [8, 11, 17, 21]
        for v in lts:
            if v >= required:
                return v
        return lts[-1]

    @staticmethod
    def get_max_java(minecraft_version: str) -> int:
        """
        Return the newest Java version known to work with this MC version.

        Args:
            minecraft_version: e.g. "1.20.4"
        """
        try:
            parts = minecraft_version.split(".")
            prefix = f"{parts[0]}.{parts[1]}" if len(parts) >= 2 else "1.20"
            return _MC_JAVA_MAX.get(prefix, 21)
        except (ValueError, IndexError):
            return 21

    @staticmethod
    def is_java_compatible(java_version: int, minecraft_version: str) -> bool:
        """
        Check if a Java version is compatible with a Minecraft version.

        Args:
            java_version:      Major Java version (e.g. 17)
            minecraft_version: e.g. "1.20.4"
        """
        required = JavaManager.get_required_java(minecraft_version)
        max_ver = JavaManager.get_max_java(minecraft_version)
        return required <= java_version <= max_ver

    # ================================================================
    #  JAVA INSTALLATION (DOWNLOAD)
    # ================================================================

    def install_java(self, version: int) -> Result:
        """
        Synchronous wrapper around download_java for CLI usage.

        Detects OS & arch, downloads, extracts, and verifies.

        Args:
            version: Major Java version (8, 11, 17, 21)
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.warning("Event loop already running; use download_java() directly")
                return Result.fail(
                    "Cannot run sync install inside async context",
                    error="Use download_java() with await instead",
                )
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _run():
            async with aiohttp.ClientSession() as session:
                return await self.download_java(version, session)

        try:
            result = loop.run_until_complete(_run())
            if result:
                return Result.ok(
                    f"Java {version} installed successfully",
                    version=version,
                    path=result.path,
                )
            else:
                return Result.fail(f"Failed to install Java {version}")
        except Exception as exc:
            logger.error("Install failed: %s", exc)
            return Result.fail(f"Install failed: {exc}", error=str(exc))

    def get_java_download_url(
        self, version: int, os_name: Optional[str] = None, arch: Optional[str] = None
    ) -> str:
        """
        Build the Adoptium API URL for downloading a JDK.

        Args:
            version: Major Java version (8, 11, 17, 21)
            os_name: Override OS (linux, windows, mac). Auto-detected if None.
            arch:    Override arch (x64, aarch64). Auto-detected if None.
        """
        os_name = os_name or self._os_id
        arch = arch or self._arch_id

        return (
            f"{ADOPTIUM_API}/assets/latest/{version}/hotspot"
            f"?os={os_name}&architecture={arch}&image_type=jdk"
        )

    async def download_java(
        self,
        version: int,
        session: aiohttp.ClientSession,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[JavaVersion]:
        """
        Download and install a specific Java version from Eclipse Adoptium.

        Args:
            version:           Major Java version (8, 11, 17, 21)
            session:           aiohttp session for HTTP requests
            progress_callback: Optional async callable(downloaded, total) for progress

        Returns:
            JavaVersion on success, None on failure
        """
        os_name = self._os_id
        arch = self._arch_id

        if not os_name or not arch:
            logger.error(
                "Unsupported platform: %s %s", self._system, self._machine
            )
            return None

        # Fetch available releases from Adoptium
        api_url = self.get_java_download_url(version, os_name, arch)
        logger.info("Querying Adoptium API: %s", api_url)

        try:
            async with session.get(api_url) as resp:
                if resp.status != 200:
                    logger.error(
                        "Adoptium API returned %d for Java %d", resp.status, version
                    )
                    return None
                releases = await resp.json()

            if not releases:
                logger.error(
                    "No releases found for Java %d on %s/%s", version, os_name, arch
                )
                return None

            release = releases[0]
            binary_info = release.get("binary", {})
            package = binary_info.get("package", {})
            download_url = package.get("link")
            filename = package.get("name", f"java-{version}.tar.gz")
            total_size = package.get("size", 0)

            # Extract full version string
            version_data = release.get("version", {})
            full_version = version_data.get("semver", "")

            if not download_url:
                logger.error("No download URL in Adoptium response")
                return None

            logger.info(
                "Downloading Java %d (%s): %s (%s)",
                version, full_version, download_url, filename,
            )

            # ── Download the archive ──
            dest_file = self.java_dir / filename
            downloaded = 0
            start_time = time.time()

            async with session.get(download_url) as resp:
                if resp.status != 200:
                    logger.error("Download failed: HTTP %d", resp.status)
                    return None

                with open(dest_file, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(8192):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            await progress_callback(downloaded, total_size)

            elapsed = time.time() - start_time
            speed = (downloaded / (1024 * 1024)) / max(elapsed, 0.1)
            logger.info(
                "Download complete: %s (%.1f MB, %.1f MB/s)",
                filename, downloaded / (1024 * 1024), speed,
            )

            # ── Extract the archive ──
            install_path = self._extract_java(str(dest_file), version)

            # Clean up the archive
            dest_file.unlink(missing_ok=True)

            # ── Verify installation ──
            if not self.verify_java_installation(install_path):
                logger.error("Verification failed for Java %d at %s", version, install_path)
                return None

            # ── Create JavaVersion entry ──
            jv = JavaVersion(
                version=version,
                path=install_path,
                vendor="adoptium",
                architecture=arch,
                full_version=full_version,
                installed_at=datetime.now(tz=timezone.utc).isoformat(),
                source="downloaded",
            )

            # Register (replace existing of same version)
            self.installations = [i for i in self.installations if i.version != version]
            self.installations.append(jv)
            self._save_state()

            logger.info("Java %d installed at %s", version, install_path)
            return jv

        except Exception as exc:
            logger.error("Failed to download Java %d: %s", version, exc)
            return None

    def _extract_java(self, archive_path: str, version: int) -> str:
        """
        Extract the JDK archive and move to the appropriate location.

        Args:
            archive_path: Path to the downloaded archive
            version:      Major Java version

        Returns:
            Path to the extracted JDK root
        """
        extract_dir = self.java_dir / f"java-{version}"

        # Remove old extraction if exists
        if extract_dir.exists():
            shutil.rmtree(extract_dir, ignore_errors=True)

        logger.info("Extracting %s → %s", archive_path, extract_dir)
        self._extract_archive(Path(archive_path), extract_dir)

        # Find the actual JDK root inside the extraction
        jdk_root = self._find_jdk_root(extract_dir)
        return str(jdk_root)

    def verify_java_installation(self, java_path: str) -> bool:
        """
        Verify a Java installation works correctly.

        Runs:
          1. java -version                  (basic check)
          2. java -Xmx512M -version        (memory allocation test)

        Args:
            java_path: Path to JDK root directory
        """
        binary = self._java_bin_for_dir(java_path)

        if not os.path.isfile(binary):
            logger.error("Java binary not found: %s", binary)
            return False

        # Test 1: basic version check
        ver, full = self._get_java_version_full(binary)
        if not ver:
            logger.error("Failed to parse version from %s", binary)
            return False
        logger.info("Verify: Java %d (%s) at %s", ver, full, binary)

        # Test 2: memory allocation test
        try:
            result = subprocess.run(
                [binary, "-Xmx512M", "-version"],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode != 0:
                logger.warning("Memory test failed (exit code %d)", result.returncode)
                return False
            logger.info("Verify: memory allocation test passed")
        except (subprocess.TimeoutExpired, FileNotFoundError, PermissionError) as exc:
            logger.warning("Memory test failed: %s", exc)
            return False

        return True

    def uninstall_java(self, version: int) -> Result:
        """
        Safely remove a downloaded Java installation.

        Does NOT remove system-installed Java.

        Args:
            version: Major Java version to remove
        """
        inst = next((i for i in self.installations if i.version == version), None)
        if not inst:
            return Result.fail(
                f"Java {version} not found",
                error="Not installed or already removed",
            )

        # Safety: don't remove system installs
        if inst.source == "detected" and inst.vendor in ("system", "JAVA_HOME"):
            return Result.fail(
                f"Cannot remove system Java {version}",
                error="System Java can only be removed via your OS package manager",
                vendor=inst.vendor,
                path=inst.path,
            )

        # Remove files
        install_path = Path(inst.path)
        if install_path.exists():
            try:
                shutil.rmtree(install_path, ignore_errors=True)
                logger.info("Removed Java %d files at %s", version, install_path)
            except Exception as exc:
                logger.error("Failed to remove files: %s", exc)
                return Result.fail(
                    f"Failed to remove Java {version} files",
                    error=str(exc),
                )

        # Also clean parent java-NN directory if empty
        parent = install_path.parent
        if parent.exists() and parent != self.java_dir:
            try:
                if not list(parent.iterdir()):
                    parent.rmdir()
            except Exception:
                pass

        # Update state
        self.installations = [i for i in self.installations if i.version != version]
        if self.active and self.active.version == version:
            self.active = None
            logger.info("Active Java cleared (was %d)", version)
        self._save_state()

        return Result.ok(
            f"Java {version} uninstalled",
            version=version,
            path=str(install_path),
        )

    # Backward-compat alias
    def remove(self, version: int) -> bool:
        """Remove a Java version (backward-compat wrapper)."""
        result = self.uninstall_java(version)
        return result.success

    # ================================================================
    #  ACTIVE VERSION MANAGEMENT
    # ================================================================

    def set_active(self, version: int) -> bool:
        """
        Set the active Java version.

        Args:
            version: Major version to activate

        Returns:
            True on success
        """
        for inst in self.installations:
            if inst.version == version and inst.is_valid():
                # Deactivate previous
                for i in self.installations:
                    i.is_default = False
                inst.is_default = True
                self.active = inst
                self._save_state()
                logger.info("Active Java set to %d (%s)", version, inst.path)
                return True

        logger.warning("Java %d not found or invalid", version)
        return False

    def get_active(self) -> Optional[JavaVersion]:
        """Return the currently active Java installation, or None."""
        return self.active

    def get_java_binary(self) -> Optional[str]:
        """Return the path to the active ``java`` binary, or None."""
        if self.active and self.active.is_valid():
            return self.active.java_binary
        # Fallback: system java
        return shutil.which("java")

    def list_installed(self) -> List[JavaVersion]:
        """Return all known installations."""
        return list(self.installations)

    # ================================================================
    #  DEFAULT JAVA MANAGEMENT
    # ================================================================

    def set_default_java(self, version: int) -> Result:
        """
        Mark which Java to use by default.

        On Linux/macOS: suggests setting JAVA_HOME.
        On all platforms: persists to config.
        """
        success = self.set_active(version)
        if not success:
            return Result.fail(
                f"Java {version} not installed or invalid",
                error="Install it first, then set as default",
            )

        inst = self.active

        # Platform-specific hints
        hints = []
        if self._system in ("Linux", "Darwin"):
            hints.append(f'export JAVA_HOME="{inst.path}"')
            hints.append(f'export PATH="$JAVA_HOME/bin:$PATH"')
        elif self._system == "Windows":
            hints.append(f'Set JAVA_HOME to: {inst.path}')
            hints.append(f'Add %JAVA_HOME%\\bin to PATH')

        return Result.ok(
            f"Java {version} set as default",
            version=version,
            path=inst.path,
            java_home_hint=hints,
        )

    def get_default_java(self) -> Optional[JavaVersion]:
        """
        Return the currently set default Java.

        Falls back to the active installation, then system Java.
        """
        if self.active:
            return self.active

        # Try to find one marked as default
        for inst in self.installations:
            if inst.is_default:
                self.active = inst
                return inst

        # Fallback: system Java
        sys_java = self.get_system_java()
        return sys_java

    # ================================================================
    #  PERSISTENCE (java_versions.json)
    # ================================================================

    def save_java_versions(self, versions_list: Optional[List[JavaVersion]] = None) -> None:
        """
        Save Java versions to java_versions.json.

        Args:
            versions_list: Optional override list. Uses self.installations if None.
        """
        if versions_list is not None:
            self.installations = versions_list
        self._save_state()

    def load_java_versions(self) -> List[JavaVersion]:
        """Load Java versions from java_versions.json."""
        self._load_state()
        return list(self.installations)

    def _load_state(self) -> None:
        """Load installations and active version from java_versions.json."""
        if not self.java_versions_path.exists():
            return
        try:
            with open(self.java_versions_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.installations = [
                JavaVersion.from_dict(d) for d in data.get("installed", [])
            ]
            active_version = data.get("active")
            if active_version is not None:
                self.active = next(
                    (i for i in self.installations if i.version == active_version),
                    None,
                )
            logger.debug("Loaded %d Java installations", len(self.installations))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load java_versions.json: %s", exc)

    def _save_state(self) -> None:
        """Persist current state to java_versions.json."""
        data = {
            "installed": [i.to_dict() for i in self.installations],
            "active": self.active.version if self.active else None,
            "platform": {
                "system": self._system,
                "machine": self._machine,
                "os_id": self._os_id,
                "arch_id": self._arch_id,
            },
            "supported_matrix": self._supported_matrix(),
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
        }
        try:
            with open(self.java_versions_path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
        except OSError as exc:
            logger.error("Could not save java_versions.json: %s", exc)

    @staticmethod
    def _supported_matrix() -> Dict[str, Any]:
        """Return the supported Java-to-MC version mapping."""
        return {
            "8":  {"min_mc": "1.0",   "max_mc": "1.16.5", "status": "legacy"},
            "11": {"min_mc": "1.12",  "max_mc": "1.16.5", "status": "legacy"},
            "16": {"min_mc": "1.17",  "max_mc": "1.17.1", "status": "deprecated"},
            "17": {"min_mc": "1.17",  "max_mc": "1.20.4", "status": "LTS"},
            "21": {"min_mc": "1.20.5","max_mc": "latest",  "status": "LTS (recommended)"},
        }

    # ================================================================
    #  PLATFORM-SPECIFIC DETECTION
    # ================================================================

    def _common_java_dirs(self) -> List[str]:
        """Return common Java installation directories for the current OS."""
        dirs: List[str] = []

        if self._system == "Linux":
            dirs.extend([
                "/usr/lib/jvm",
                "/usr/java",
                "/opt/java",
                os.path.expanduser("~/.sdkman/candidates/java"),
                os.path.expanduser("~/.jdks"),
            ])
            # Colab / IDX specific
            if self._is_colab or self._is_idx:
                dirs.append("/usr/lib/jvm")

        elif self._system == "Darwin":
            dirs.extend([
                "/Library/Java/JavaVirtualMachines",
                os.path.expanduser("~/.sdkman/candidates/java"),
                os.path.expanduser("~/.jdks"),
            ])
            # Homebrew locations
            brew_prefix = "/opt/homebrew" if self._machine == "arm64" else "/usr/local"
            dirs.append(os.path.join(brew_prefix, "opt"))

        elif self._system == "Windows":
            program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
            program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            dirs.extend([
                os.path.join(program_files, "Java"),
                os.path.join(program_files, "Eclipse Adoptium"),
                os.path.join(program_files, "Eclipse Foundation"),
                os.path.join(program_files, "AdoptOpenJDK"),
                os.path.join(program_files, "Microsoft"),
                os.path.join(program_files, "Zulu"),
                os.path.join(program_files, "BellSoft"),
                os.path.join(program_files_x86, "Java"),
                r"C:\Java",
            ])

        # Also add our managed directory
        dirs.append(str(self.java_dir))

        return dirs

    def _detect_macos_java_home(self) -> List[JavaVersion]:
        """Use macOS /usr/libexec/java_home to list all JVMs."""
        found: List[JavaVersion] = []
        try:
            result = subprocess.run(
                ["/usr/libexec/java_home", "-V"],
                capture_output=True, text=True, timeout=10,
            )
            # Output goes to stderr on macOS
            output = result.stderr or result.stdout
            for line in output.splitlines():
                # Example: "    17.0.9 (x86_64) "Adoptium" - "OpenJDK..." /path/to/jdk"
                # We want the path at the end
                line = line.strip()
                if not line or "Matching" in line:
                    continue
                # Try to extract path (last space-separated item starting with /)
                parts = line.rsplit(None, 1)
                if parts and parts[-1].startswith("/"):
                    path = parts[-1]
                    ver, full = self._get_java_version_full(
                        self._java_bin_for_dir(path)
                    )
                    if ver:
                        vendor = self._guess_vendor(path, full)
                        found.append(JavaVersion(
                            version=ver, path=path, vendor=vendor,
                            architecture=self._arch_id, full_version=full,
                            source="detected",
                        ))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return found

    @staticmethod
    def _detect_colab() -> bool:
        """Detect if running in Google Colab."""
        if os.path.exists("/content") and "COLAB_RELEASE_TAG" in os.environ:
            return True
        try:
            import google.colab  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _detect_idx() -> bool:
        """Detect if running in Google IDX."""
        return "IDX_CHANNEL" in os.environ or os.path.exists("/home/user/.idx")

    # ================================================================
    #  UTILITY METHODS
    # ================================================================

    def _java_bin_for_dir(self, java_dir: str) -> str:
        """Return the path to the java binary for a JDK directory."""
        binary = "java.exe" if self._system == "Windows" else "java"
        # Standard layout
        standard = os.path.join(java_dir, "bin", binary)
        if os.path.isfile(standard):
            return standard
        # macOS Adoptium: Contents/Home/bin/java
        mac_path = os.path.join(java_dir, "Contents", "Home", "bin", binary)
        if os.path.isfile(mac_path):
            return mac_path
        return standard  # return standard even if it doesn't exist

    @staticmethod
    def _get_java_version_full(binary_path: str) -> Tuple[Optional[int], str]:
        """
        Run ``java -version`` and parse both major version and full version string.

        Returns:
            (major_version_int, full_version_str) or (None, "")
        """
        try:
            result = subprocess.run(
                [binary_path, "-version"],
                capture_output=True, text=True, timeout=15,
            )
            output = result.stderr or result.stdout
            full_version = ""

            for line in output.splitlines():
                if "version" in line.lower():
                    # Parse version string: "17.0.9" or "1.8.0_392"
                    match = re.search(r'"([^"]+)"', line)
                    if match:
                        full_version = match.group(1)
                    else:
                        # Fallback: last word on the line
                        full_version = line.split()[-1].strip('"')

                    parts = full_version.split(".")
                    try:
                        major = int(parts[0])
                        if major == 1 and len(parts) >= 2:
                            # Handle 1.8 → 8
                            return int(parts[1]), full_version
                        return major, full_version
                    except (ValueError, IndexError):
                        pass

        except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired) as exc:
            logger.debug("java -version failed for %s: %s", binary_path, exc)

        return None, ""

    # Backward compat: old code used _get_java_version returning just int
    @staticmethod
    def _get_java_version(binary_path: str) -> Optional[int]:
        """Legacy wrapper: returns just the major version int."""
        ver, _ = JavaManager._get_java_version_full(binary_path)
        return ver

    @staticmethod
    def _guess_vendor(path: str, full_version: str) -> str:
        """Guess the JDK vendor from path or version string."""
        path_lower = path.lower()
        fv_lower = full_version.lower()

        if "adoptium" in path_lower or "temurin" in fv_lower:
            return "adoptium"
        if "adoptopen" in path_lower:
            return "adoptopenjdk"
        if "zulu" in path_lower or "azul" in fv_lower:
            return "azul-zulu"
        if "corretto" in path_lower or "corretto" in fv_lower:
            return "amazon-corretto"
        if "graalvm" in path_lower or "graal" in fv_lower:
            return "graalvm"
        if "microsoft" in path_lower:
            return "microsoft"
        if "bellsoft" in path_lower or "liberica" in fv_lower:
            return "bellsoft-liberica"
        if "oracle" in path_lower:
            return "oracle"
        if "openjdk" in path_lower:
            return "openjdk"
        if "homebrew" in path_lower or "/opt/homebrew" in path_lower:
            return "homebrew"
        if ".sdkman" in path_lower:
            return "sdkman"
        return "system"

    @staticmethod
    def _extract_archive(archive_path: Path, dest_dir: Path) -> None:
        """Extract a .tar.gz or .zip archive into dest_dir."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        name = archive_path.name.lower()

        if name.endswith(".tar.gz") or name.endswith(".tgz"):
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extractall(dest_dir, filter="data")
        elif name.endswith(".zip"):
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(dest_dir)
        else:
            raise ValueError(f"Unsupported archive format: {archive_path.name}")

    @staticmethod
    def _find_jdk_root(extract_dir: Path) -> Path:
        """
        Find the actual JDK root inside the extracted directory.
        Adoptium typically extracts to a subdirectory like ``jdk-17.0.2+8``.
        """
        for child in extract_dir.iterdir():
            if child.is_dir():
                # Check for bin/ directly
                if (child / "bin").exists():
                    return child
                # macOS: Contents/Home/bin
                if (child / "Contents" / "Home" / "bin").exists():
                    return child
        # If no subdirectory found, the extract_dir itself might be the root
        return extract_dir
