"""
projectdavid_platform/tunnel.py

Project David — Sovereign Forge SSH Tunnel Manager

Manages one or more persistent SSH reverse tunnels from the local HEAD node
to remote GPU worker nodes. Handles automatic reconnection, keepalive
monitoring, port verification, and live status feedback.

USAGE:
    pdavid tunnel connect --host root@157.157.221.29 --port 19938
    pdavid tunnel connect --host root@157.157.221.29 --port 19938 --name runpod-1 --background
    pdavid tunnel status
    pdavid tunnel stop --name runpod-1
    pdavid tunnel stop --all

ARCHITECTURE:
    - Each tunnel is a named connection stored in ~/.pdavid/tunnels.json
    - SSH is run as a managed subprocess (wraps system OpenSSH — no deps)
    - A watchdog thread monitors port reachability every 30s
    - Reconnects automatically with exponential backoff on failure
    - Reads DATABASE_URL and REDIS_URL from .env to extract ports automatically
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import socket
import subprocess  # nosec B404
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import typer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TUNNEL_STATE_FILE = Path.home() / ".pdavid" / "tunnels.json"
PID_DIR = Path.home() / ".pdavid" / "pids"
LOG_DIR = Path.home() / ".pdavid" / "logs"

SSH_KEEPALIVE_INTERVAL = 15
SSH_KEEPALIVE_COUNT = 3
WATCHDOG_INTERVAL = 30
RECONNECT_BACKOFF = [5, 10, 20, 40, 80, 120]

DEFAULT_FORWARDS = [
    (10001, "localhost", 10001, "Ray client server"),
    (6379, "localhost", 6379, "Redis"),
    (
        3308,
        "localhost",
        3307,
        "MySQL",
    ),  # remote 3308 → local 3307 (avoids port conflict)
]

ENV_FILE = ".env"

# ---------------------------------------------------------------------------
# Colours and symbols
# ---------------------------------------------------------------------------


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    DIM = "\033[2m"
    BLUE = "\033[94m"


def _supports_colour() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def c(text: str, colour: str) -> str:
    if not _supports_colour():
        return text
    return f"{colour}{text}{C.RESET}"


def print_header() -> None:
    typer.echo("")
    typer.echo(
        c("  ╔══════════════════════════════════════════════════════════╗", C.CYAN)
    )
    typer.echo(
        c("  ║  Project David — Sovereign Forge Tunnel                  ║", C.CYAN)
    )
    typer.echo(
        c("  ╚══════════════════════════════════════════════════════════╝", C.CYAN)
    )
    typer.echo("")


def print_event(symbol: str, colour: str, message: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    typer.echo(f"  {c(symbol, colour)} {c(ts, C.DIM)}  {message}")


def ok(msg: str) -> None:
    print_event("✅", C.GREEN, msg)


def warn(msg: str) -> None:
    print_event("⚠", C.YELLOW, msg)


def err(msg: str) -> None:
    print_event("✗", C.RED, msg)


def info(msg: str) -> None:
    print_event("⟳", C.CYAN, msg)


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------


def _load_env(env_path: str = ENV_FILE) -> Dict[str, str]:
    result: Dict[str, str] = {}
    p = Path(env_path)
    if not p.exists():
        return result
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def _extract_ports_from_env(env: Dict[str, str]) -> List[Tuple[int, str, int, str]]:
    """
    Reads DATABASE_URL and REDIS_URL from .env and builds the -R forward list.
    Falls back to DEFAULT_FORWARDS if env vars are absent or unparseable.

    MySQL remote port is always 3308 to avoid conflicts with the well-known
    3306 port on RunPod worker nodes. Local port maps to the Docker host port
    (typically 3307). The worker's DATABASE_URL must use localhost:3308.
    """
    forwards = []

    # Redis
    redis_url = env.get("REDIS_URL", "")
    if redis_url:
        try:
            parsed = urlparse(redis_url)
            port = parsed.port or 6379
            forwards.append((port, "localhost", port, "Redis"))
        except Exception:
            forwards.append((6379, "localhost", 6379, "Redis"))
    else:
        forwards.append((6379, "localhost", 6379, "Redis"))

    # MySQL — extract host port from DATABASE_URL
    # Remote port is always 3308 to avoid conflicts on the worker side.
    # Local port maps to the Docker host port (typically 3307).
    db_url = env.get("DATABASE_URL", "")
    db_port = 3307
    if db_url:
        m = re.search(r":(\d+)/", db_url)
        if m:
            db_port = int(m.group(1))
    forwards.append((3308, "localhost", db_port, "MySQL"))

    # Ray client server — always 10001
    forwards.insert(0, (10001, "localhost", 10001, "Ray client server"))

    return forwards


# ---------------------------------------------------------------------------
# Port reachability
# ---------------------------------------------------------------------------


def _port_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            return s.connect_ex((host, port)) == 0
    except Exception:
        return False


def _verify_forwards(
    forwards: List[Tuple[int, str, int, str]],
    print_results: bool = True,
) -> bool:
    all_ok = True
    for remote_port, local_host, local_port, label in forwards:
        reachable = _port_open("127.0.0.1", local_port)
        if print_results:
            if reachable:
                ok(f"Port {local_port} reachable  ({label})")
            else:
                warn(f"Port {local_port} not yet reachable  ({label})")
        if not reachable:
            all_ok = False
    return all_ok


# ---------------------------------------------------------------------------
# SSH command builder
# ---------------------------------------------------------------------------


def _build_ssh_cmd(
    host: str,
    port: int,
    key: str,
    forwards: List[Tuple[int, str, int, str]],
) -> List[str]:
    cmd = [
        "ssh",
        "-N",
        "-i",
        key,
        "-o",
        f"ServerAliveInterval={SSH_KEEPALIVE_INTERVAL}",
        "-o",
        f"ServerAliveCountMax={SSH_KEEPALIVE_COUNT}",
        "-o",
        "TCPKeepAlive=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        "ExitOnForwardFailure=yes",
        "-p",
        str(port),
    ]
    for remote_port, local_host, local_port, _ in forwards:
        cmd += ["-R", f"{remote_port}:{local_host}:{local_port}"]
    cmd.append(host)
    return cmd


# ---------------------------------------------------------------------------
# Tunnel state persistence
# ---------------------------------------------------------------------------


def _load_state() -> Dict:
    TUNNEL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not TUNNEL_STATE_FILE.exists():
        return {}
    try:
        return json.loads(TUNNEL_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: Dict) -> None:
    TUNNEL_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TUNNEL_STATE_FILE.write_text(json.dumps(state, indent=2))


def _register_tunnel(
    name: str,
    host: str,
    port: int,
    key: str,
    forwards: List[Tuple[int, str, int, str]],
    pid: Optional[int] = None,
) -> None:
    state = _load_state()
    state[name] = {
        "host": host,
        "port": port,
        "key": key,
        "forwards": [[r, lh, lp, lbl] for r, lh, lp, lbl in forwards],
        "pid": pid,
        "status": "connecting",
        "connected_at": None,
        "reconnects": 0,
    }
    _save_state(state)


def _update_tunnel(name: str, **kwargs) -> None:
    state = _load_state()
    if name in state:
        state[name].update(kwargs)
        _save_state(state)


def _remove_tunnel(name: str) -> None:
    state = _load_state()
    state.pop(name, None)
    _save_state(state)


# ---------------------------------------------------------------------------
# Core tunnel runner
# ---------------------------------------------------------------------------


class TunnelRunner:
    """
    Manages a single SSH tunnel subprocess with automatic reconnection
    and live status feedback.
    """

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        key: str,
        forwards: List[Tuple[int, str, int, str]],
        background: bool = False,
    ):
        self.name = name
        self.host = host
        self.port = port
        self.key = key
        self.forwards = forwards
        self.background = background

        self._proc: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._status = "connecting"
        self._connected_at: Optional[float] = None
        self._reconnects = 0
        self._last_status_line = ""

    def _uptime(self) -> str:
        if self._connected_at is None:
            return "--:--:--"
        elapsed = int(time.time() - self._connected_at)
        h, rem = divmod(elapsed, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _print_status(self) -> None:
        if self.background:
            return
        status_map = {
            "connected": c("● CONNECTED", C.GREEN),
            "connecting": c("⟳ CONNECTING", C.CYAN),
            "reconnecting": c("↺ RECONNECTING", C.YELLOW),
            "disconnected": c("✗ DISCONNECTED", C.RED),
        }
        symbol = status_map.get(self._status, self._status)
        line = f"\r  {symbol}  |  uptime {self._uptime()}  |  Ctrl+C to disconnect  "
        sys.stdout.write(line)
        sys.stdout.flush()
        self._last_status_line = line

    def _clear_status(self) -> None:
        if self.background:
            return
        sys.stdout.write("\r" + " " * len(self._last_status_line) + "\r")
        sys.stdout.flush()

    def _spawn(self) -> bool:
        cmd = _build_ssh_cmd(self.host, self.port, self.key, self.forwards)
        try:
            self._proc = subprocess.Popen(  # nosec B603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True
        except FileNotFoundError:
            err("ssh not found in PATH — install OpenSSH")
            return False
        except Exception as e:
            err(f"Failed to spawn SSH: {e}")
            return False

    def _wait_for_connection(self, timeout: float = 15.0) -> bool:
        """Wait until at least the Ray port is reachable."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc and self._proc.poll() is not None:
                return False  # Process died
            if _port_open("127.0.0.1", self.forwards[0][2], timeout=1.0):
                return True
            time.sleep(0.5)
        return False

    def _watchdog(self) -> None:
        """Background thread — monitors tunnel health and triggers reconnect."""
        miss_count = 0
        while not self._stop_event.is_set():
            time.sleep(WATCHDOG_INTERVAL)
            if self._stop_event.is_set():
                break

            # Check primary port
            if _port_open("127.0.0.1", self.forwards[0][2], timeout=3.0):
                miss_count = 0
                continue

            miss_count += 1
            self._clear_status()
            warn(f"Keepalive missed ({miss_count}/{SSH_KEEPALIVE_COUNT})")

            if miss_count >= SSH_KEEPALIVE_COUNT:
                self._clear_status()
                err("Tunnel lost — initiating reconnect")
                self._status = "reconnecting"
                miss_count = 0
                self._reconnect()

    def _reconnect(self) -> None:
        """Kill existing process and reconnect with exponential backoff."""
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:  # nosec B110
                pass

        for attempt, backoff in enumerate(RECONNECT_BACKOFF, 1):
            if self._stop_event.is_set():
                return

            info(f"Reconnecting (attempt {attempt}, backoff {backoff}s)...")
            time.sleep(backoff)

            if not self._spawn():
                continue

            t0 = time.time()
            if self._wait_for_connection(timeout=20.0):
                elapsed = time.time() - t0
                self._connected_at = time.time()
                self._reconnects += 1
                self._status = "connected"
                self._clear_status()
                ok(
                    f"Tunnel re-established — {elapsed:.1f}s  (reconnect #{self._reconnects})"
                )
                _update_tunnel(
                    self.name,
                    status="connected",
                    reconnects=self._reconnects,
                    pid=self._proc.pid if self._proc else None,
                )
                return

            err(f"Attempt {attempt} failed")

        err("Could not re-establish tunnel after maximum attempts")
        self._status = "disconnected"
        _update_tunnel(self.name, status="disconnected")

    def run(self) -> None:
        """Main entry point — connect and block until stopped."""
        typer.echo(f"  {c('Host', C.DIM)}        : {self.host}:{self.port}")
        longest = max(len(lbl) for _, _, _, lbl in self.forwards)
        for i, (remote_port, local_host, local_port, label) in enumerate(self.forwards):
            prefix = f"  {c('Forwards', C.DIM)}    :" if i == 0 else "              "
            pad = " " * (longest - len(label))
            typer.echo(
                f"{prefix} {local_port} → {local_host}:{remote_port}  {c(f'({label}){pad}', C.DIM)}"
            )
        typer.echo(f"  {c('Key', C.DIM)}         : {self.key}")
        typer.echo(
            f"  {c('Mode', C.DIM)}        : {'background' if self.background else 'foreground'}"
        )
        typer.echo("")

        info("Connecting...")

        if not self._spawn():
            raise SystemExit(1)

        t0 = time.time()
        connected = self._wait_for_connection(timeout=20.0)
        elapsed = time.time() - t0

        if not connected or (self._proc and self._proc.poll() is not None):
            stderr_out = ""
            if self._proc:
                try:
                    stderr_out = (
                        self._proc.stderr.read(500) if self._proc.stderr else ""
                    )
                except Exception:  # nosec B110
                    pass
            err(f"Connection failed after {elapsed:.1f}s")
            if stderr_out:
                typer.echo(f"\n  SSH error: {stderr_out.strip()}\n", err=True)
            raise SystemExit(1)

        self._connected_at = time.time()
        self._status = "connected"
        ok(f"Tunnel established — {elapsed:.1f}s")

        # Verify all ports
        time.sleep(1.0)
        for remote_port, local_host, local_port, label in self.forwards:
            reachable = _port_open("127.0.0.1", local_port, timeout=2.0)
            if reachable:
                ok(f"Port {local_port} reachable  ({label})")
            else:
                warn(f"Port {local_port} not yet reachable  ({label})")

        typer.echo("")

        # Persist state
        _register_tunnel(
            self.name,
            self.host,
            self.port,
            self.key,
            self.forwards,
            pid=self._proc.pid if self._proc else None,
        )
        _update_tunnel(self.name, status="connected", connected_at=time.time())

        if self.background:
            ok(
                f"Tunnel '{self.name}' running in background (PID {self._proc.pid if self._proc else '?'})"
            )
            typer.echo("  Check status : pdavid tunnel status")
            typer.echo(f"  Stop         : pdavid tunnel stop --name {self.name}")
            typer.echo("")
            self._start_watchdog()
            return

        # Foreground — start watchdog and block with live status
        self._start_watchdog()

        try:
            while not self._stop_event.is_set():
                self._print_status()
                time.sleep(1.0)

                # Check if SSH process died unexpectedly
                if self._proc and self._proc.poll() is not None:
                    self._clear_status()
                    err("SSH process exited unexpectedly — reconnecting")
                    self._status = "reconnecting"
                    self._reconnect()

        except KeyboardInterrupt:
            self._clear_status()
            typer.echo("")
            info("Disconnecting...")
            self.stop()
            ok("Tunnel closed")
            typer.echo("")

    def _start_watchdog(self) -> None:
        self._watchdog_thread = threading.Thread(
            target=self._watchdog, daemon=True, name=f"watchdog-{self.name}"
        )
        self._watchdog_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:  # nosec B110
                    pass
        _remove_tunnel(self.name)


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="tunnel",
    help="Manage SSH tunnels to Sovereign Forge worker nodes.",
    add_completion=False,
)


def _resolve_key(key: Optional[str]) -> str:
    if key:
        return str(Path(key).expanduser())
    candidates = [
        Path.home() / ".ssh" / "id_ed25519",
        Path.home() / ".ssh" / "id_rsa",
        Path.home() / ".ssh" / "id_ecdsa",
    ]
    for c_ in candidates:
        if c_.exists():
            return str(c_)
    typer.echo("[error] No SSH key found. Specify with --key.", err=True)
    raise SystemExit(1)


def _resolve_forwards(
    forwards_override: Optional[List[str]],
    env_file: str,
) -> List[Tuple[int, str, int, str]]:
    """
    Build forward list from:
      1. Explicit --forward flags if provided
      2. .env DATABASE_URL / REDIS_URL if present
      3. DEFAULT_FORWARDS fallback
    """
    if forwards_override:
        result = []
        for f in forwards_override:
            parts = f.split(":")
            if len(parts) < 3:
                typer.echo(
                    f"[error] Invalid forward spec '{f}'. Use remote:local_host:local_port[:label]",
                    err=True,
                )
                raise SystemExit(1)
            result.append(
                (
                    int(parts[0]),
                    parts[1],
                    int(parts[2]),
                    parts[3] if len(parts) > 3 else f"port {parts[2]}",
                )
            )
        return result

    env = _load_env(env_file)
    if env:
        return _extract_ports_from_env(env)

    return DEFAULT_FORWARDS


@app.command(name="connect")
def connect(
    host: str = typer.Option(
        ..., "--host", "-h", help="SSH target, e.g. root@157.157.221.29"
    ),
    port: int = typer.Option(..., "--port", "-p", help="SSH port on the remote host"),
    name: str = typer.Option(
        "default", "--name", "-n", help="Name for this tunnel connection"
    ),
    key: Optional[str] = typer.Option(
        None, "--key", "-k", help="Path to SSH private key (auto-detected if omitted)"
    ),
    background: bool = typer.Option(
        False, "--background", "-b", help="Run tunnel in background"
    ),
    forward: Optional[List[str]] = typer.Option(
        None,
        "--forward",
        "-f",
        help="Port forward spec: remote:local_host:local_port[:label]",
    ),
    env_file: str = typer.Option(
        ".env", "--env-file", help="Path to .env file for auto port detection"
    ),
) -> None:
    """
    Connect to a remote worker node via SSH tunnel.

    The tunnel forwards Ray, Redis, and MySQL ports from the remote machine
    back to your local HEAD node. Port configuration is read automatically
    from your .env file.

    Examples:\n
      pdavid tunnel connect --host root@157.157.221.29 --port 19938\n
      pdavid tunnel connect --host root@157.157.221.29 --port 19938 --name runpod-1 --background\n
    """
    if not shutil.which("ssh"):
        typer.echo("[error] ssh not found in PATH. Install OpenSSH.", err=True)
        raise SystemExit(1)

    state = _load_state()
    if name in state and state[name].get("status") in ("connected", "connecting"):
        typer.echo(
            f"[error] Tunnel '{name}' is already running. Use a different --name or stop it first.",
            err=True,
        )
        raise SystemExit(1)

    resolved_key = _resolve_key(key)
    forwards = _resolve_forwards(forward, env_file)

    print_header()

    runner = TunnelRunner(
        name=name,
        host=host,
        port=port,
        key=resolved_key,
        forwards=forwards,
        background=background,
    )
    runner.run()


@app.command(name="status")
def status() -> None:
    """Show status of all active tunnel connections."""
    state = _load_state()

    print_header()

    if not state:
        typer.echo("  No active tunnels.\n")
        return

    for name, info_ in state.items():
        status_val = info_.get("status", "unknown")
        colour_map = {
            "connected": C.GREEN,
            "connecting": C.CYAN,
            "reconnecting": C.YELLOW,
            "disconnected": C.RED,
        }
        col = colour_map.get(status_val, C.DIM)

        connected_at = info_.get("connected_at")
        if connected_at:
            elapsed = int(time.time() - connected_at)
            h, rem = divmod(elapsed, 3600)
            m, s = divmod(rem, 60)
            uptime = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            uptime = "--:--:--"

        typer.echo(f"  {c('●', col)} {c(name, C.BOLD)}")
        typer.echo(f"    Status      : {c(status_val.upper(), col)}")
        typer.echo(f"    Host        : {info_.get('host')}:{info_.get('port')}")
        typer.echo(f"    Uptime      : {uptime}")
        typer.echo(f"    Reconnects  : {info_.get('reconnects', 0)}")
        typer.echo(f"    PID         : {info_.get('pid', '?')}")
        forwards = info_.get("forwards", [])
        for i, fwd in enumerate(forwards):
            prefix = "    Forwards    :" if i == 0 else "               "
            typer.echo(
                f"{prefix} {fwd[2]} → {fwd[1]}:{fwd[0]}  {c(f'({fwd[3]})', C.DIM)}"
            )
        typer.echo("")


@app.command(name="stop")
def stop(
    name: str = typer.Option(None, "--name", "-n", help="Name of the tunnel to stop"),
    all_tunnels: bool = typer.Option(
        False, "--all", "-a", help="Stop all active tunnels"
    ),
) -> None:
    """Stop one or all tunnel connections."""
    state = _load_state()

    if not state:
        typer.echo("  No active tunnels to stop.")
        return

    if all_tunnels:
        targets = list(state.keys())
    elif name:
        if name not in state:
            typer.echo(f"[error] No tunnel named '{name}'.", err=True)
            raise SystemExit(1)
        targets = [name]
    else:
        typer.echo("[error] Specify --name or --all.", err=True)
        raise SystemExit(1)

    for target in targets:
        info_ = state[target]
        pid = info_.get("pid")

        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                ok(f"Stopped tunnel '{target}' (PID {pid})")
            except ProcessLookupError:
                warn(f"Tunnel '{target}' process not found (already stopped?)")
            except Exception as e:
                err(f"Could not stop '{target}': {e}")
        else:
            warn(f"No PID recorded for '{target}'")

        _remove_tunnel(target)

    typer.echo("")


@app.command(name="logs")
def logs(
    name: str = typer.Option(
        "default", "--name", "-n", help="Tunnel name to show logs for"
    ),
    lines: int = typer.Option(50, "--lines", "-l", help="Number of log lines to show"),
) -> None:
    """Show recent log output for a tunnel connection."""
    log_file = LOG_DIR / f"{name}.log"
    if not log_file.exists():
        typer.echo(f"  No logs found for tunnel '{name}'.")
        return

    all_lines = log_file.read_text().splitlines()
    for line in all_lines[-lines:]:
        typer.echo(f"  {line}")
