"""
server_manager.py
=================
Core Minecraft server lifecycle management.

Responsibilities:
  - Check prerequisites (Java, server JAR, EULA, disk space)
  - Start / stop / restart the server process via subprocess
  - Monitor server status (CPU, RAM, players, TPS)
  - Configuration management (config.json + server.properties)
  - Logging: tail, clear, export
  - Java compatibility checking and version selection
  - JVM flag management with per-profile recommendations
  - Create and restore world backups
  - Auto-detect runtime environment (Google Colab, IDX, local)
  - Generate server.properties from config
  - Cross-platform support (Windows, macOS, Linux)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp
import psutil

from server_types import ServerType, get_server_type, SERVER_TYPES
from java_manager import JavaManager
from eula_manager import EulaManager
from file_editor import FileEditor

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  Environment Detection
# ──────────────────────────────────────────────

class Environment:
    """Runtime environment constants."""

    LOCAL = "local"
    COLAB = "colab"
    IDX = "idx"

    @staticmethod
    def detect() -> str:
        """Auto-detect the runtime environment."""
        # Google Colab
        if os.path.exists("/content") and "COLAB_RELEASE_TAG" in os.environ:
            return Environment.COLAB
        try:
            import google.colab  # noqa: F401
            return Environment.COLAB
        except ImportError:
            pass

        # Google IDX
        if "IDX_CHANNEL" in os.environ or os.path.exists("/home/user/.idx"):
            return Environment.IDX

        return Environment.LOCAL


# ──────────────────────────────────────────────
#  Result Object
# ──────────────────────────────────────────────

@dataclass
class Result:
    """Unified result object for all ServerManager operations."""

    success: bool
    message: str
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, message: str, **details: Any) -> "Result":
        """Create a successful result."""
        return cls(success=True, message=message, details=details)

    @classmethod
    def fail(cls, message: str, error: Optional[str] = None, **details: Any) -> "Result":
        """Create a failed result."""
        return cls(success=False, message=message, error=error, details=details)


# ──────────────────────────────────────────────
#  Server Status
# ──────────────────────────────────────────────

@dataclass
class ServerStatus:
    """Snapshot of current server state."""

    running: bool = False
    pid: Optional[int] = None
    uptime_seconds: float = 0.0
    cpu_percent: float = 0.0
    ram_used_mb: float = 0.0
    ram_allocated_mb: int = 0
    players_online: int = 0
    max_players: int = 0
    player_names: List[str] = field(default_factory=list)
    version: str = ""
    server_type: str = ""
    tps: float = 20.0
    motd: str = ""
    world_name: str = ""
    port: int = 25565

    def to_dict(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "pid": self.pid,
            "uptime_seconds": round(self.uptime_seconds, 1),
            "cpu_percent": round(self.cpu_percent, 1),
            "ram_used_mb": round(self.ram_used_mb, 1),
            "ram_allocated_mb": self.ram_allocated_mb,
            "players_online": self.players_online,
            "max_players": self.max_players,
            "player_names": self.player_names,
            "version": self.version,
            "server_type": self.server_type,
            "tps": round(self.tps, 1),
            "motd": self.motd,
            "world_name": self.world_name,
            "port": self.port,
        }


# ──────────────────────────────────────────────
#  Server Manager
# ──────────────────────────────────────────────

class ServerManager:
    """
    Manages the full Minecraft server lifecycle.

    Args:
        config_path: Path to config.json
        server_dir:  Path to the server directory (override config)
    """

    # ── Minimum disk space required to start (in MB) ──
    MIN_DISK_SPACE_MB = 500

    # ── Graceful stop timeout (seconds) ──
    STOP_TIMEOUT = 30

    # ── Log colour tags used internally ──
    LOG_LEVELS = {
        "INFO":    "info",
        "WARN":    "warning",
        "WARNING": "warning",
        "ERROR":   "error",
        "FATAL":   "error",
        "SEVERE":  "error",
    }

    # ================================================================
    #  INITIALIZATION
    # ================================================================

    def __init__(
        self,
        config_path: str | Path = "config.json",
        server_dir: Optional[str | Path] = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self._load_config()

        # Paths (can be overridden via constructor or config)
        if server_dir is not None:
            self.server_dir = Path(server_dir)
        else:
            self.server_dir = Path(
                self.config.get("paths", {}).get("server_dir", "./server")
            )
        self.plugins_dir = self.server_dir / "plugins"
        self.backup_dir = Path(
            self.config.get("paths", {}).get("backup_dir", "./backups")
        )
        self.logs_dir = self.server_dir / "logs"
        java_dir = Path(
            self.config.get("paths", {}).get("java_dir", "./java")
        )

        # Sub-managers
        self.java_manager = JavaManager(java_dir, "java_versions.json")
        self.eula_manager = EulaManager(self.server_dir, self.config_path)
        self.file_editor = FileEditor(str(self.server_dir))

        # Process state
        self._process: Optional[subprocess.Popen] = None
        self._start_time: Optional[float] = None
        self._log_buffer: deque[str] = deque(maxlen=5000)
        self._log_file_handle = None

        # Environment
        self.environment = Environment.detect()
        logger.info("Environment detected: %s", self.environment)

        # System info
        self._system = platform.system()  # Windows | Linux | Darwin

        # Ensure directories
        for d in (self.server_dir, self.plugins_dir, self.backup_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

        logger.info(
            "ServerManager initialised.  server_dir=%s  config=%s",
            self.server_dir,
            self.config_path,
        )

    # ================================================================
    #  CONFIGURATION
    # ================================================================

    def _load_config(self) -> None:
        """Load config.json into self.config."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as fh:
                    self.config = json.load(fh)
                logger.debug("Config loaded from %s", self.config_path)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("Failed to load config: %s", exc)
                self.config = {}
        else:
            logger.info("Config file not found, using defaults")
            self.config = {}

    def save_config(self) -> None:
        """Persist self.config back to config.json."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as fh:
                json.dump(self.config, fh, indent=2)
            logger.debug("Config saved to %s", self.config_path)
        except OSError as exc:
            logger.error("Failed to save config: %s", exc)

    def get_config(self) -> Dict[str, Any]:
        """Return the full configuration dictionary."""
        return dict(self.config)

    def update_config(self, key: str, value: Any) -> Result:
        """
        Update a single top-level config key and persist.

        Supports dot-notation, e.g. "server.ram" → config["server"]["ram"]
        """
        try:
            parts = key.split(".")
            target = self.config
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            target[parts[-1]] = value
            self.save_config()
            logger.info("Config updated: %s = %s", key, value)
            return Result.ok(f"Config updated: {key} = {value}")
        except Exception as exc:
            logger.error("Config update failed: %s", exc)
            return Result.fail(f"Config update failed", error=str(exc))

    def get_server_config(self) -> Dict[str, Any]:
        """Return the 'server' section of config."""
        return self.config.get("server", {})

    def update_server_config(self, **kwargs: Any) -> None:
        """Update server config values and save."""
        self.config.setdefault("server", {}).update(kwargs)
        self.save_config()

    # ── server.properties Management ────────────

    def get_server_properties(self) -> Dict[str, str]:
        """
        Parse server.properties into a dictionary.

        Returns:
            Dict of key-value pairs from server.properties
        """
        props = {}
        props_path = self.server_dir / "server.properties"

        if not props_path.exists():
            logger.warning("server.properties not found")
            return props

        try:
            content = props_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    props[key.strip()] = value.strip()
            logger.debug("Parsed %d properties", len(props))
        except OSError as exc:
            logger.error("Failed to read server.properties: %s", exc)

        return props

    def update_server_properties(self, key: str, value: str) -> Result:
        """
        Update a single key in server.properties.

        Creates a backup before writing.

        Args:
            key:   Property key (e.g. "server-port")
            value: New value (e.g. "25565")
        """
        props_path = self.server_dir / "server.properties"

        if not props_path.exists():
            return Result.fail(
                "server.properties not found",
                error=f"File does not exist: {props_path}",
            )

        try:
            # Validate the key is a known server property
            valid_keys = self._known_property_keys()
            if valid_keys and key not in valid_keys:
                logger.warning("Property '%s' is not a recognised key", key)

            # Read current content
            content = props_path.read_text(encoding="utf-8")
            lines = content.splitlines()

            # Backup
            self.file_editor.create_backup(str(props_path))

            # Find and replace or append
            found = False
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("#") or not stripped:
                    continue
                if "=" in stripped:
                    k, _, _ = stripped.partition("=")
                    if k.strip() == key:
                        lines[i] = f"{key}={value}"
                        found = True
                        break

            if not found:
                lines.append(f"{key}={value}")

            props_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logger.info("Updated server.properties: %s=%s", key, value)
            return Result.ok(
                f"Updated {key}={value}",
                key=key,
                value=value,
                file=str(props_path),
            )

        except OSError as exc:
            logger.error("Failed to update server.properties: %s", exc)
            return Result.fail("Failed to update property", error=str(exc))

    @staticmethod
    def _known_property_keys() -> List[str]:
        """Return commonly known server.properties keys."""
        return [
            "server-port", "gamemode", "difficulty", "max-players", "pvp",
            "online-mode", "level-name", "motd", "view-distance",
            "simulation-distance", "spawn-protection", "enable-command-block",
            "allow-flight", "white-list", "max-world-size", "hardcore",
            "level-seed", "level-type", "server-ip", "enable-rcon",
            "rcon.password", "rcon.port", "enable-query", "query.port",
            "enforce-whitelist", "max-tick-time", "network-compression-threshold",
            "op-permission-level", "player-idle-timeout",
            "prevent-proxy-connections", "rate-limit", "resource-pack",
            "spawn-animals", "spawn-monsters", "spawn-npcs",
        ]

    # ================================================================
    #  PREREQUISITES CHECK
    # ================================================================

    def check_prerequisites(self) -> Result:
        """
        Run all prerequisite checks before starting the server.

        Checks:
          1. Java installed & compatible
          2. Server JAR exists
          3. EULA accepted
          4. Sufficient disk space

        Returns:
            Result with details: {"checks": {name: {ok, message}}}
        """
        checks: Dict[str, Dict[str, Any]] = {}
        all_ok = True

        # 1. Java
        java_bin = self.java_manager.get_java_binary()
        if java_bin and Path(java_bin).exists():
            checks["java"] = {"ok": True, "message": f"Java found: {java_bin}"}
        else:
            checks["java"] = {
                "ok": False,
                "message": "Java not found. Install Java first.",
            }
            all_ok = False

        # 2. Server JAR
        jar = self.get_server_jar()
        if jar and jar.exists():
            size_mb = jar.stat().st_size / (1024 * 1024)
            checks["server_jar"] = {
                "ok": True,
                "message": f"Server JAR: {jar.name} ({size_mb:.1f} MB)",
            }
        else:
            checks["server_jar"] = {
                "ok": False,
                "message": "Server JAR not found. Download a server first.",
            }
            all_ok = False

        # 3. EULA
        if self.eula_manager.is_accepted():
            checks["eula"] = {"ok": True, "message": "EULA accepted ✅"}
        else:
            checks["eula"] = {
                "ok": False,
                "message": "EULA not accepted. Accept the EULA first.",
            }
            all_ok = False

        # 4. Disk space
        try:
            if self._system == "Windows":
                disk = psutil.disk_usage(str(self.server_dir.resolve().drive + "\\"))
            else:
                disk = psutil.disk_usage(str(self.server_dir.resolve()))
            free_mb = disk.free / (1024 * 1024)
            if free_mb >= self.MIN_DISK_SPACE_MB:
                checks["disk_space"] = {
                    "ok": True,
                    "message": f"Free disk: {free_mb:.0f} MB",
                }
            else:
                checks["disk_space"] = {
                    "ok": False,
                    "message": f"Low disk space: {free_mb:.0f} MB (need {self.MIN_DISK_SPACE_MB} MB)",
                }
                all_ok = False
        except Exception as exc:
            checks["disk_space"] = {
                "ok": False,
                "message": f"Could not check disk space: {exc}",
            }
            all_ok = False

        # 5. Java compatibility (advisory, does not block start)
        compat = self.check_java_compatibility()
        checks["java_compat"] = {
            "ok": compat.success,
            "message": compat.message,
        }

        if all_ok:
            return Result.ok("All prerequisites met ✅", checks=checks)
        else:
            failed = [n for n, c in checks.items() if not c["ok"]]
            return Result.fail(
                f"Prerequisites not met: {', '.join(failed)}",
                error="Fix the above issues before starting",
                checks=checks,
            )

    # ================================================================
    #  SERVER JAR
    # ================================================================

    async def download_server(
        self,
        session: aiohttp.ClientSession,
        progress_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Download the server JAR based on the current config.

        Returns True on success.
        """
        srv_cfg = self.get_server_config()
        type_name = srv_cfg.get("type", "paper")
        version = srv_cfg.get("version", "1.20.4")

        server_type = get_server_type(type_name)
        if not server_type:
            logger.error("Unknown server type: %s", type_name)
            return False

        logger.info("Downloading %s %s …", server_type.name, version)
        url = await server_type.get_download_url(version, session)
        if not url:
            logger.error("Could not resolve download URL for %s %s", type_name, version)
            return False

        jar_name = f"{type_name}-{version}.jar"
        jar_path = self.server_dir / jar_name

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.error("Download HTTP %d", resp.status)
                    return False
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(jar_path, "wb") as fh:
                    async for chunk in resp.content.iter_chunked(8192):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            await progress_callback(downloaded, total)

            logger.info("Downloaded %s (%d bytes)", jar_path, jar_path.stat().st_size)
            return True

        except Exception as exc:
            logger.error("Download failed: %s", exc)
            return False

    def get_server_jar(self) -> Optional[Path]:
        """Find the server JAR in the server directory."""
        srv_cfg = self.get_server_config()
        type_name = srv_cfg.get("type", "paper")
        version = srv_cfg.get("version", "1.20.4")

        expected = self.server_dir / f"{type_name}-{version}.jar"
        if expected.exists():
            return expected

        # Fallback: find any .jar
        jars = list(self.server_dir.glob("*.jar"))
        return jars[0] if jars else None

    # ================================================================
    #  SERVER LIFECYCLE
    # ================================================================

    def start_server(self) -> Result:
        """
        Start the Minecraft server process.

        1. Verify all prerequisites
        2. Build Java command with JVM flags
        3. Start process via subprocess.Popen
        4. Capture stdout/stderr
        5. Return success/failure
        """
        if self.is_running():
            return Result.fail(
                "Server is already running",
                error=f"PID {self._process.pid}",
                pid=self._process.pid,
            )

        # ── Check prerequisites ──
        prereqs = self.check_prerequisites()
        if not prereqs.success:
            return Result.fail(
                "Prerequisites not met",
                error=prereqs.error,
                checks=prereqs.details.get("checks", {}),
            )

        # ── Build command ──
        jar = self.get_server_jar()
        java_bin = self.java_manager.get_java_binary()

        srv_cfg = self.get_server_config()
        ram = srv_cfg.get("ram", 2048)
        jvm_flags_str = self.get_jvm_flags()

        cmd = [
            java_bin,
            f"-Xmx{ram}M",
            f"-Xms{ram}M",
        ]

        # Add JVM flags if any
        if jvm_flags_str.strip():
            cmd.extend(jvm_flags_str.split())

        cmd.extend(["-jar", str(jar), "--nogui"])

        logger.info("Starting server: %s", " ".join(cmd))

        # ── Start process ──
        try:
            log_path = self.logs_dir / "latest.log"
            self._log_file_handle = open(log_path, "a", encoding="utf-8")

            creation_flags = 0
            if self._system == "Windows":
                creation_flags = subprocess.CREATE_NO_WINDOW

            self._process = subprocess.Popen(
                cmd,
                cwd=str(self.server_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE,
                creationflags=creation_flags if self._system == "Windows" else 0,
                bufsize=1,
            )
            self._start_time = time.time()
            self._log_buffer.clear()

            # Start async log reader
            self._start_log_reader()

            logger.info("Server started (PID %d)", self._process.pid)
            return Result.ok(
                f"Server started (PID {self._process.pid})",
                pid=self._process.pid,
                command=" ".join(cmd),
                ram_mb=ram,
            )

        except FileNotFoundError as exc:
            logger.error("Java binary not found: %s", exc)
            return Result.fail(
                "Failed to start: Java binary not found",
                error=str(exc),
            )
        except PermissionError as exc:
            logger.error("Permission denied: %s", exc)
            return Result.fail(
                "Failed to start: Permission denied",
                error=str(exc),
            )
        except Exception as exc:
            logger.error("Failed to start server: %s", exc)
            return Result.fail("Failed to start server", error=str(exc))

    def _start_log_reader(self) -> None:
        """Start a background thread to read server stdout."""
        import threading

        def _reader():
            try:
                if self._process and self._process.stdout:
                    for raw_line in iter(self._process.stdout.readline, b""):
                        try:
                            line = raw_line.decode("utf-8", errors="replace").rstrip()
                        except Exception:
                            line = str(raw_line)

                        self._log_buffer.append(line)

                        # Also write to log file
                        if self._log_file_handle and not self._log_file_handle.closed:
                            try:
                                self._log_file_handle.write(line + "\n")
                                self._log_file_handle.flush()
                            except Exception:
                                pass
            except Exception as exc:
                logger.debug("Log reader thread ended: %s", exc)

        thread = threading.Thread(target=_reader, daemon=True, name="server-log-reader")
        thread.start()

    def stop_server(self) -> Result:
        """
        Gracefully stop the Minecraft server.

        1. Send 'stop' command via stdin
        2. Wait up to STOP_TIMEOUT seconds for graceful shutdown
        3. Force kill if process doesn't stop
        4. Clean up process handles
        """
        if not self.is_running():
            return Result.fail("Server is not running")

        pid = self._process.pid if self._process else None
        logger.info("Stopping server (PID %s) …", pid)

        try:
            # Step 1: Send 'stop' command
            if self._process and self._process.stdin:
                try:
                    self._process.stdin.write(b"stop\n")
                    self._process.stdin.flush()
                    logger.info("Sent 'stop' command to server")
                except (BrokenPipeError, OSError) as exc:
                    logger.warning("Could not send stop command: %s", exc)

            # Step 2: Wait for graceful shutdown
            if self._process:
                try:
                    self._process.wait(timeout=self.STOP_TIMEOUT)
                    logger.info("Server stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Graceful stop timed out after %ds, force-killing",
                        self.STOP_TIMEOUT,
                    )
                    # Step 3: Force kill
                    self._force_kill()

            # Step 4: Clean up
            uptime = self._get_uptime()
            self._cleanup_process()

            return Result.ok(
                "Server stopped",
                pid=pid,
                uptime_seconds=uptime,
            )

        except Exception as exc:
            logger.error("Stop failed: %s", exc)
            # Attempt force kill as last resort
            self._force_kill()
            self._cleanup_process()
            return Result.fail("Stop failed (process force-killed)", error=str(exc))

    def _force_kill(self) -> None:
        """Force-kill the server process and all children."""
        if not self._process:
            return
        try:
            parent = psutil.Process(self._process.pid)
            children = parent.children(recursive=True)
            for child in children:
                child.kill()
            parent.kill()
            psutil.wait_procs([parent] + children, timeout=5)
            logger.info("Process tree killed")
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            pass
        except Exception as exc:
            logger.error("Force kill error: %s", exc)

    def _cleanup_process(self) -> None:
        """Reset internal process state."""
        if self._log_file_handle and not self._log_file_handle.closed:
            try:
                self._log_file_handle.close()
            except Exception:
                pass
        self._process = None
        self._start_time = None
        self._log_file_handle = None

    def restart_server(self) -> Result:
        """
        Restart the Minecraft server.

        Stops the server (if running), waits 2 seconds, then starts.
        """
        logger.info("Restarting server …")

        if self.is_running():
            stop_result = self.stop_server()
            if not stop_result.success:
                return Result.fail(
                    f"Restart failed during stop: {stop_result.message}",
                    error=stop_result.error,
                )
            # Give OS time to release ports / file handles
            time.sleep(2)

        start_result = self.start_server()
        if start_result.success:
            return Result.ok(
                "Server restarted",
                pid=start_result.details.get("pid"),
            )
        else:
            return Result.fail(
                f"Restart failed during start: {start_result.message}",
                error=start_result.error,
            )

    def send_command(self, command: str) -> Result:
        """
        Send a console command to the running server.

        Args:
            command: The Minecraft console command (e.g. "say Hello")
        """
        if not self.is_running():
            return Result.fail("Server is not running")

        if not self._process or not self._process.stdin:
            return Result.fail("No stdin handle – cannot send command")

        try:
            self._process.stdin.write(f"{command}\n".encode("utf-8"))
            self._process.stdin.flush()
            logger.info("Command sent: %s", command)
            return Result.ok(f"Command sent: {command}")
        except (BrokenPipeError, OSError) as exc:
            logger.error("Failed to send command: %s", exc)
            return Result.fail("Failed to send command", error=str(exc))

    def is_running(self) -> bool:
        """Check if the server process is alive."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def _get_uptime(self) -> float:
        """Return server uptime in seconds."""
        if self._start_time:
            return time.time() - self._start_time
        return 0.0

    # ================================================================
    #  STATUS MONITORING
    # ================================================================

    def get_server_status(self) -> ServerStatus:
        """
        Get comprehensive server status.

        Populates: running, PID, uptime, CPU, RAM, players, TPS, config info.
        Player count & TPS are parsed from recent log lines.
        """
        status = ServerStatus()
        srv_cfg = self.get_server_config()

        # Config-based fields
        status.version = srv_cfg.get("version", "")
        status.server_type = srv_cfg.get("type", "")
        status.ram_allocated_mb = srv_cfg.get("ram", 2048)
        status.max_players = srv_cfg.get("max_players", 20)
        status.motd = srv_cfg.get("motd", "A Minecraft Server")
        status.world_name = srv_cfg.get("world_name", "world")
        status.port = srv_cfg.get("port", 25565)

        if self.is_running() and self._process:
            status.running = True
            status.pid = self._process.pid
            status.uptime_seconds = self._get_uptime()

            # System resource usage via psutil
            try:
                proc = psutil.Process(self._process.pid)
                status.cpu_percent = proc.cpu_percent(interval=0.5)
                mem = proc.memory_info()
                status.ram_used_mb = mem.rss / (1024 * 1024)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

            # Parse logs for player info and TPS
            self._parse_status_from_logs(status)

        return status

    def _parse_status_from_logs(self, status: ServerStatus) -> None:
        """Parse recent log lines for player count, TPS, and player names."""
        recent = list(self._log_buffer)[-200:]

        # ── Player join/leave tracking ──
        # [HH:MM:SS INFO]: PlayerName joined the game
        # [HH:MM:SS INFO]: PlayerName left the game
        players_online: set = set()
        join_pat = re.compile(r"(\w+) joined the game")
        leave_pat = re.compile(r"(\w+) left the game")

        for line in recent:
            m = join_pat.search(line)
            if m:
                players_online.add(m.group(1))
            m = leave_pat.search(line)
            if m:
                players_online.discard(m.group(1))

        status.players_online = len(players_online)
        status.player_names = sorted(players_online)

        # ── TPS ──
        # Paper/Spigot: TPS from last 1m, 5m, 15m: 20.0, 20.0, 20.0
        tps_pat = re.compile(r"TPS from last.*?:\s*([\d.]+)")
        for line in reversed(recent):
            m = tps_pat.search(line)
            if m:
                try:
                    status.tps = float(m.group(1))
                except ValueError:
                    pass
                break

    # ================================================================
    #  LOGGING
    # ================================================================

    def get_recent_logs(self, lines: int = 100) -> List[str]:
        """
        Return the last N lines from the server log.

        Uses in-memory buffer first, falls back to file.
        """
        if self._log_buffer:
            buf_lines = list(self._log_buffer)
            return buf_lines[-lines:]

        # Fallback: read from file
        return self._read_log_file(lines)

    def _read_log_file(self, lines: int = 100) -> List[str]:
        """Read last N lines from the log file on disk."""
        log_path = self.logs_dir / "latest.log"
        if not log_path.exists():
            return []
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
            all_lines = content.splitlines()
            return all_lines[-lines:]
        except OSError:
            return []

    def clear_logs(self) -> Result:
        """
        Clear the server log file (keeps a backup).
        """
        log_path = self.logs_dir / "latest.log"
        if not log_path.exists():
            return Result.ok("No log file to clear")

        try:
            # Backup current log
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            backup_name = f"latest_{timestamp}.log"
            backup_path = self.logs_dir / backup_name
            shutil.copy2(log_path, backup_path)

            # Clear the file
            log_path.write_text("", encoding="utf-8")
            self._log_buffer.clear()

            logger.info("Logs cleared (backup: %s)", backup_name)
            return Result.ok(
                f"Logs cleared",
                backup=str(backup_path),
            )
        except OSError as exc:
            logger.error("Failed to clear logs: %s", exc)
            return Result.fail("Failed to clear logs", error=str(exc))

    def export_logs(self, output_path: str) -> Result:
        """
        Export server logs to a file.

        Args:
            output_path: Destination file path
        """
        try:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)

            # Combine in-memory buffer and on-disk log
            all_lines: List[str] = []
            log_path = self.logs_dir / "latest.log"

            if log_path.exists():
                all_lines = log_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()

            # Append any buffer lines not yet on disk
            if self._log_buffer:
                all_lines.extend(list(self._log_buffer))

            output.write_text("\n".join(all_lines), encoding="utf-8")
            logger.info("Logs exported to %s (%d lines)", output, len(all_lines))
            return Result.ok(
                f"Exported {len(all_lines)} lines to {output}",
                path=str(output),
                line_count=len(all_lines),
            )
        except OSError as exc:
            logger.error("Log export failed: %s", exc)
            return Result.fail("Log export failed", error=str(exc))

    # ================================================================
    #  JAVA INTEGRATION
    # ================================================================

    def check_java_compatibility(self) -> Result:
        """
        Check if the active Java version is compatible with the configured MC version.

        Returns:
            Result with compatibility details
        """
        srv_cfg = self.get_server_config()
        mc_version = srv_cfg.get("version", "1.20.4")

        required = self.java_manager.get_required_version(mc_version)
        active = self.java_manager.get_active()

        if active is None:
            return Result.fail(
                "No active Java installation",
                error="Install and activate a Java version first",
                required=required,
            )

        active_ver = active.version

        if active_ver >= required:
            return Result.ok(
                f"Java {active_ver} is compatible with MC {mc_version} (requires {required}+)",
                java_version=active_ver,
                mc_version=mc_version,
                required=required,
            )
        else:
            return Result.fail(
                f"Java {active_ver} is too old for MC {mc_version}",
                error=f"Requires Java {required}+, found Java {active_ver}",
                java_version=active_ver,
                mc_version=mc_version,
                required=required,
                suggestion=f"Install Java {required} or newer",
            )

    def set_java_version(self, version: int) -> Result:
        """
        Set which Java version to use for the server.

        Args:
            version: Major Java version (e.g. 17, 21)
        """
        success = self.java_manager.set_active(version)
        if success:
            self.update_config("java.active_version", version)
            logger.info("Active Java set to %d", version)
            return Result.ok(
                f"Java {version} activated",
                version=version,
            )
        else:
            return Result.fail(
                f"Java {version} not installed",
                error="Install it first, then activate",
            )

    # ================================================================
    #  JVM FLAGS
    # ================================================================

    # Pre-defined JVM flag profiles
    _JVM_PROFILES: Dict[str, str] = {
        "default": "",
        "aikar": (
            "-XX:+UseG1GC "
            "-XX:+ParallelRefProcEnabled "
            "-XX:MaxGCPauseMillis=200 "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:+DisableExplicitGC "
            "-XX:+AlwaysPreTouch "
            "-XX:G1NewSizePercent=30 "
            "-XX:G1MaxNewSizePercent=40 "
            "-XX:G1HeapRegionSize=8M "
            "-XX:G1ReservePercent=20 "
            "-XX:G1HeapWastePercent=5 "
            "-XX:G1MixedGCCountTarget=4 "
            "-XX:InitiatingHeapOccupancyPercent=15 "
            "-XX:G1MixedGCLiveThresholdPercent=90 "
            "-XX:G1RSetUpdatingPauseTimePercent=5 "
            "-XX:SurvivorRatio=32 "
            "-XX:+PerfDisableSharedMem "
            "-XX:MaxTenuringThreshold=1 "
            "-Dusing.aikars.flags=https://mcflags.emc.gs "
            "-Daikars.new.flags=true"
        ),
        "graalvm": (
            "-XX:+UseG1GC "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:+UnlockDiagnosticVMOptions "
            "-XX:+AlwaysActAsServerClassMachine "
            "-XX:+AlwaysPreTouch "
            "-XX:+DisableExplicitGC "
            "-XX:+UseNUMA "
            "-XX:AllocatePrefetchStyle=3 "
            "-XX:NmethodSweepActivity=1 "
            "-XX:ReservedCodeCacheSize=400M "
            "-XX:NonNMethodCodeHeapSize=12M "
            "-XX:ProfiledCodeHeapSize=194M "
            "-XX:NonProfiledCodeHeapSize=194M "
            "-XX:-DontCompileHugeMethods "
            "-XX:+PerfDisableSharedMem "
            "-XX:+UseFastUnorderedTimeStamps "
            "-XX:+UseCriticalJavaThreadPriority"
        ),
        "zgc": (
            "-XX:+UseZGC "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:+AlwaysPreTouch "
            "-XX:+DisableExplicitGC "
            "-XX:-ZUncommit "
            "-XX:+PerfDisableSharedMem"
        ),
        "low_memory": (
            "-XX:+UseSerialGC "
            "-XX:-UseCompressedOops "
            "-XX:+UnlockExperimentalVMOptions "
            "-XX:+DisableExplicitGC "
            "-XX:+AlwaysPreTouch"
        ),
    }

    def get_jvm_flags(self) -> str:
        """
        Return the currently configured JVM flags string.
        """
        srv_cfg = self.get_server_config()
        profile_name = srv_cfg.get("jvm_profile", "default")

        # Check for custom flags first
        custom = self.config.get("jvm_flags", {}).get("custom", "")
        if custom:
            return custom

        # Use profile
        return self._JVM_PROFILES.get(profile_name, "")

    def set_jvm_flags(self, flags: str) -> Result:
        """
        Set custom JVM flags.

        Args:
            flags: Full JVM flags string (e.g. "-XX:+UseG1GC -XX:MaxGCPauseMillis=200")

        Validates flags begin with '-' tokens.
        """
        # Basic validation: each token should start with '-'
        tokens = flags.split()
        invalid = [t for t in tokens if t and not t.startswith("-") and "=" not in t]
        if invalid:
            return Result.fail(
                f"Invalid JVM flag tokens: {invalid}",
                error="Each flag should start with '-'",
            )

        self.config.setdefault("jvm_flags", {})["custom"] = flags
        self.save_config()
        logger.info("JVM flags set: %s", flags)
        return Result.ok("JVM flags updated", flags=flags)

    def set_jvm_profile(self, profile_name: str) -> Result:
        """
        Set JVM flags to a predefined profile.

        Available profiles: default, aikar, graalvm, zgc, low_memory
        """
        if profile_name not in self._JVM_PROFILES:
            available = ", ".join(self._JVM_PROFILES.keys())
            return Result.fail(
                f"Unknown profile: {profile_name}",
                error=f"Available: {available}",
            )

        # Clear custom flags when using a profile
        if "jvm_flags" in self.config:
            self.config["jvm_flags"].pop("custom", None)

        self.update_config("server.jvm_profile", profile_name)
        logger.info("JVM profile set: %s", profile_name)
        return Result.ok(
            f"JVM profile set to '{profile_name}'",
            profile=profile_name,
            flags=self._JVM_PROFILES[profile_name],
        )

    def get_recommended_flags(self) -> str:
        """
        Return recommended JVM flags based on current environment.

        Considers:
          - Java version (G1GC vs ZGC)
          - Available RAM (low_memory vs aikar)
          - Server software type
        """
        srv_cfg = self.get_server_config()
        ram = srv_cfg.get("ram", 2048)
        active_java = self.java_manager.get_active()
        java_ver = active_java.version if active_java else 17

        # Low memory environments
        if ram <= 1024:
            logger.info("Recommending low_memory flags (RAM ≤ 1 GB)")
            return self._JVM_PROFILES["low_memory"]

        # Java 17+ with enough RAM → ZGC is great
        if java_ver >= 17 and ram >= 8192:
            logger.info("Recommending ZGC flags (Java %d, RAM %d MB)", java_ver, ram)
            return self._JVM_PROFILES["zgc"]

        # Default: Aikar's flags (battle-tested for Minecraft)
        logger.info("Recommending Aikar flags")
        return self._JVM_PROFILES["aikar"]

    def list_jvm_profiles(self) -> Dict[str, str]:
        """Return all available JVM flag profiles."""
        return dict(self._JVM_PROFILES)

    # ================================================================
    #  BACKUP MANAGEMENT
    # ================================================================

    def create_backup(self, name: Optional[str] = None) -> Result:
        """Create a backup of the server world and configs."""
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_name = name or f"backup_{timestamp}"
        backup_path = self.backup_dir / backup_name

        try:
            world_name = self.get_server_config().get("world_name", "world")
            world_dir = self.server_dir / world_name

            if not world_dir.exists():
                return Result.fail(
                    f"World directory not found: {world_dir}",
                    error=f"Expected world at {world_dir}",
                )

            shutil.make_archive(str(backup_path), "zip", self.server_dir, world_name)
            archive = f"{backup_path}.zip"
            size_mb = Path(archive).stat().st_size / (1024 * 1024)
            logger.info("Backup created: %s (%.1f MB)", archive, size_mb)
            return Result.ok(
                f"Backup created: {backup_name}.zip ({size_mb:.1f} MB)",
                path=archive,
                size_mb=round(size_mb, 1),
            )

        except Exception as exc:
            logger.error("Backup failed: %s", exc)
            return Result.fail("Backup failed", error=str(exc))

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups."""
        backups = []
        if self.backup_dir.exists():
            for f in sorted(self.backup_dir.glob("*.zip"), reverse=True):
                backups.append({
                    "name": f.stem,
                    "path": str(f),
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                    "created": datetime.fromtimestamp(
                        f.stat().st_ctime, tz=timezone.utc
                    ).isoformat(),
                })
        return backups

    # ================================================================
    #  server.properties GENERATION
    # ================================================================

    def generate_server_properties(self) -> bool:
        """Generate server.properties from the current config."""
        srv_cfg = self.get_server_config()
        props = {
            "server-port": srv_cfg.get("port", 25565),
            "gamemode": srv_cfg.get("gamemode", "survival"),
            "difficulty": srv_cfg.get("difficulty", "normal"),
            "max-players": srv_cfg.get("max_players", 20),
            "pvp": str(srv_cfg.get("pvp", True)).lower(),
            "online-mode": str(srv_cfg.get("online_mode", True)).lower(),
            "level-name": srv_cfg.get("world_name", "world"),
            "motd": srv_cfg.get("motd", "A Minecraft Server"),
            "view-distance": srv_cfg.get("view_distance", 10),
            "simulation-distance": srv_cfg.get("simulation_distance", 10),
            "spawn-protection": srv_cfg.get("spawn_protection", 16),
            "enable-command-block": str(srv_cfg.get("enable_command_block", False)).lower(),
            "allow-flight": str(srv_cfg.get("allow_flight", False)).lower(),
            "white-list": str(srv_cfg.get("whitelist", False)).lower(),
        }

        props_path = self.server_dir / "server.properties"
        try:
            lines = [
                "# Minecraft Server Properties",
                "# Generated by Minecraft Server Manager",
                f"# {datetime.now(tz=timezone.utc).isoformat()}",
                "",
            ]
            for k, v in props.items():
                lines.append(f"{k}={v}")
            props_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            logger.info("Generated server.properties")
            return True
        except OSError as exc:
            logger.error("Failed to write server.properties: %s", exc)
            return False

    # ================================================================
    #  SYSTEM RESOURCES
    # ================================================================

    def get_system_resources(self) -> Dict[str, Any]:
        """Get current system resource usage."""
        try:
            vm = psutil.virtual_memory()
            if self._system == "Windows":
                disk = psutil.disk_usage(str(self.server_dir.resolve().drive + "\\"))
            else:
                disk = psutil.disk_usage("/")

            return {
                "cpu_percent": psutil.cpu_percent(interval=0.5),
                "cpu_count": psutil.cpu_count(),
                "ram_total_mb": round(vm.total / (1024 ** 2)),
                "ram_used_mb": round(vm.used / (1024 ** 2)),
                "ram_available_mb": round(vm.available / (1024 ** 2)),
                "ram_percent": vm.percent,
                "disk_total_gb": round(disk.total / (1024 ** 3), 1),
                "disk_used_gb": round(disk.used / (1024 ** 3), 1),
                "disk_free_gb": round(disk.free / (1024 ** 3), 1),
                "disk_percent": disk.percent,
                "platform": self._system,
                "python_version": platform.python_version(),
            }
        except Exception as exc:
            logger.error("Failed to get resources: %s", exc)
            return {"error": str(exc)}

    def get_log_tail(self, lines: int = 50) -> List[str]:
        """Return the last N lines from the server log (alias)."""
        return self.get_recent_logs(lines)
