"""
remote_controller.py – SSH remote server management via Paramiko.
"""
from __future__ import annotations
import logging, os, stat, time
from pathlib import Path
from typing import Optional, Callable

try:
    import paramiko
    HAS_PARAMIKO = True
except ImportError:
    HAS_PARAMIKO = False

logger = logging.getLogger(__name__)


class RemoteController:
    def __init__(self, host: str, port: int = 22, username: str = "",
                 password: Optional[str] = None, key_path: Optional[str] = None):
        if not HAS_PARAMIKO:
            raise ImportError("paramiko required: pip install paramiko")
        self.host, self.port, self.username = host, port, username
        self.password, self.key_path = password, key_path
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None

    def connect(self, timeout: int = 10) -> bool:
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            kw = {"hostname": self.host, "port": self.port,
                  "username": self.username, "timeout": timeout}
            if self.key_path and os.path.isfile(self.key_path):
                kw["key_filename"] = self.key_path
            elif self.password:
                kw["password"] = self.password
            else:
                return False
            self._client.connect(**kw)
            self._sftp = self._client.open_sftp()
            return True
        except Exception as e:
            logger.error("SSH connect failed: %s", e)
            return False

    def disconnect(self):
        for c in (self._sftp, self._client):
            if c:
                try: c.close()
                except: pass
        self._sftp = self._client = None

    @property
    def is_connected(self) -> bool:
        if not self._client: return False
        t = self._client.get_transport()
        return t is not None and t.is_active()

    def execute(self, command: str, timeout: int = 30) -> tuple[int, str, str]:
        if not self.is_connected: return -1, "", "Not connected"
        try:
            _, stdout, stderr = self._client.exec_command(command, timeout=timeout)
            code = stdout.channel.recv_exit_status()
            return code, stdout.read().decode("utf-8", errors="replace"), stderr.read().decode("utf-8", errors="replace")
        except Exception as e:
            return -1, "", str(e)

    def execute_background(self, command: str) -> bool:
        if not self.is_connected: return False
        try:
            self._client.exec_command(f"nohup {command} > /dev/null 2>&1 &")
            return True
        except: return False

    def start_server(self, java_binary: str, jar_path: str, ram_mb: int,
                     jvm_flags: str = "", working_dir: str = ".") -> bool:
        cmd = f"cd {working_dir} && {java_binary} -Xmx{ram_mb}M -Xms{ram_mb}M {jvm_flags} -jar {jar_path} --nogui"
        return self.execute_background(cmd)

    def stop_server(self, pid: Optional[int] = None) -> bool:
        if not pid:
            pid = self.get_server_pid()
        if pid:
            self.execute(f"kill -15 {pid}")
            time.sleep(3)
            c, _, _ = self.execute(f"kill -0 {pid} 2>/dev/null")
            if c != 0: return True
            self.execute(f"kill -9 {pid}")
            return True
        return False

    def get_server_pid(self) -> Optional[int]:
        c, o, _ = self.execute("pgrep -f 'java.*-jar.*\\.jar'")
        if c == 0 and o.strip():
            try: return int(o.strip().splitlines()[0])
            except: pass
        return None

    def upload_file(self, local: str | Path, remote: str, cb=None) -> bool:
        if not self._sftp: return False
        try:
            self._sftp.put(str(local), remote, callback=cb)
            return True
        except: return False

    def download_file(self, remote: str, local: str | Path, cb=None) -> bool:
        if not self._sftp: return False
        try:
            Path(local).parent.mkdir(parents=True, exist_ok=True)
            self._sftp.get(remote, str(local), callback=cb)
            return True
        except: return False

    def get_system_info(self) -> dict:
        info = {}
        c, o, _ = self.execute("nproc")
        if c == 0: info["cpu_cores"] = int(o.strip())
        c, o, _ = self.execute("free -m | awk '/Mem:/ {print $2, $3, $7}'")
        if c == 0:
            p = o.strip().split()
            if len(p) >= 3:
                info["ram_total_mb"], info["ram_used_mb"], info["ram_available_mb"] = int(p[0]), int(p[1]), int(p[2])
        return info

    def __enter__(self): self.connect(); return self
    def __exit__(self, *a): self.disconnect()
