# start_orchestration.py
#
# Deployment orchestrator for the Project David / Entities platform.

from __future__ import annotations

import importlib.metadata
import importlib.resources
import logging
import os
import platform as _platform
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional
from urllib.parse import quote_plus

import typer

# ---------------------------------------------------------------------------
# Container guard
# ---------------------------------------------------------------------------


def _running_in_docker() -> bool:
    return os.getenv("RUNNING_IN_DOCKER") == "1" or Path("/.dockerenv").exists()


if _running_in_docker():
    print(
        "[error] start_orchestration.py cannot be run inside a container.\n"
        "This script manages the Docker Compose stack from the HOST machine only."
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Optional third-party imports
# ---------------------------------------------------------------------------
try:
    import yaml
except ImportError:
    typer.echo("[error] PyYAML is required: pip install PyYAML", err=True)
    raise SystemExit(1)

try:
    from dotenv import load_dotenv
except ImportError:
    typer.echo("[error] python-dotenv is required: pip install python-dotenv", err=True)
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_DB_CONTAINER_PORT = "3306"
DEFAULT_DB_SERVICE_NAME = "db"
API_SERVICE_NAME = "api"
BASE_COMPOSE_FILE = "docker-compose.yml"
GPU_COMPOSE_FILE = "docker-compose.gpu.yml"
TRAINING_COMPOSE_FILE = "docker-compose.training.yml"
PACKAGE_NAME = "projectdavid_platform"

_BUNDLED_CONFIGS = [
    ("docker-compose.training.yml", "docker-compose.training.yml"),
    ("docker-compose.yml", "docker-compose.yml"),
    ("docker-compose.gpu.yml", "docker-compose.gpu.yml"),
]

# ---------------------------------------------------------------------------
# Compose file path resolution
# ---------------------------------------------------------------------------


def _resolve_compose_file(filename: str) -> str:
    local = Path.cwd() / filename
    if local.exists():
        log.debug("Using local compose file: %s", local)
        return str(local)
    try:
        pkg_files = importlib.resources.files(PACKAGE_NAME)
        resource = pkg_files / filename
        with importlib.resources.as_file(resource) as p:
            resolved = str(p)
        log.debug("Using bundled compose file: %s", resolved)
        return resolved
    except (FileNotFoundError, ModuleNotFoundError, TypeError) as e:
        log.warning("Compose file '%s' not found: %s", filename, e)
        return filename


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------

app = typer.Typer(name="pdavid", add_completion=False)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    _ENV_FILE = ".env"

    def __init__(self, args: SimpleNamespace) -> None:
        self.args = args
        self.is_windows = _platform.system() == "Windows"
        self.log = log

        if getattr(self.args, "verbose", False):
            self.log.setLevel(logging.DEBUG)

        self._ensure_config_files()

        self.base_compose = _resolve_compose_file(BASE_COMPOSE_FILE)
        self.gpu_compose = _resolve_compose_file(GPU_COMPOSE_FILE)
        self.training_compose = _resolve_compose_file(TRAINING_COMPOSE_FILE)

        self.compose_config = self._load_compose_config()

        self._check_for_required_env_file()

    @property
    def _env_file_abs(self) -> str:
        return str(Path(self._ENV_FILE).resolve())

    def _ensure_config_files(self) -> None:
        for pkg_rel, cwd_rel in _BUNDLED_CONFIGS:
            dest = Path.cwd() / cwd_rel
            if dest.exists():
                continue
            try:
                pkg_files = importlib.resources.files(PACKAGE_NAME)
                resource = pkg_files / pkg_rel
                with importlib.resources.as_file(resource) as src:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
            except Exception as e:
                self.log.warning("Could not install config '%s': %s", cwd_rel, e)

    def _generate_dot_env_file(self):
        env_values = {
            "MYSQL_PASSWORD": secrets.token_hex(32),
        }

        db_pass = env_values["MYSQL_PASSWORD"]
        escaped_pass = quote_plus(db_pass)

        env_values["DATABASE_URL"] = f"mysql+pymysql://api_user:{escaped_pass}@db:3306/entities_db"

        try:
            env_values["PDAVID_VERSION"] = importlib.metadata.version(PACKAGE_NAME)
        except Exception as e:
            self.log.debug("Version lookup failed: %s", e)
            env_values["PDAVID_VERSION"] = "latest"

        lines = [f"{k}={v}" for k, v in env_values.items()]
        Path(self._ENV_FILE).write_text("\n".join(lines))

    def _check_for_required_env_file(self):
        if not os.path.exists(self._ENV_FILE):
            self._generate_dot_env_file()
        load_dotenv(dotenv_path=self._ENV_FILE, override=True)

    def _run_command(self, cmd_list):
        try:
            subprocess.run(
                cmd_list,
                check=True,
                shell=self.is_windows,
            )
        except subprocess.CalledProcessError as e:
            self.log.error("Command failed (%s): %s", e.returncode, " ".join(cmd_list))
            raise

    def _compose_files(self) -> list:
        files = [
            "--env-file",
            self._env_file_abs,
            "-f",
            self.base_compose,
        ]

        if getattr(self.args, "gpu", False):
            files += ["-f", self.gpu_compose]

        if getattr(self.args, "training", False):
            files += ["-f", self.training_compose]

        return files

    def _handle_up(self):
        up_cmd = ["docker", "compose"] + self._compose_files() + ["up", "-d"]
        self._run_command(up_cmd)
        self.log.info("Stack started successfully.")

    def run(self):
        if getattr(self.args, "nuke", False):
            confirm = input("DANGER: Type 'confirm nuke': ")
            if confirm == "confirm nuke":
                self._run_command(["docker", "compose"] + self._compose_files() + ["down", "-v"])
            return

        mode = getattr(self.args, "mode", "up")

        if mode == "up":
            self._handle_up()

    def _load_compose_config(self):
        try:
            return yaml.safe_load(Path(self.base_compose).read_text())
        except Exception as e:
            self.log.debug("Compose config load failed: %s", e)
            return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    mode: str = typer.Option("up"),
    training: bool = typer.Option(False),
    gpu: bool = typer.Option(False),
    nuke: bool = typer.Option(False),
    verbose: bool = typer.Option(False),
):
    if ctx.invoked_subcommand:
        return

    args = SimpleNamespace(
        mode=mode,
        training=training,
        gpu=gpu,
        nuke=nuke,
        verbose=verbose,
    )

    Orchestrator(args).run()


if __name__ == "__main__":
    app()
