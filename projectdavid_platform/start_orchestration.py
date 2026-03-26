# start_orchestration.py
#
# Deployment orchestrator for the Project David / Entities platform.
# Distributed as part of the `projectdavid-platform` pip package.
#
# VERSION: Sovereign Forge + Silent Initialization + Lint Fixes
#
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
    # LINT FIX (F401): Removed unused 'set_key' import
    from dotenv import load_dotenv
except ImportError:
    typer.echo("[error] python-dotenv is required: pip install python-dotenv", err=True)
    raise SystemExit(1)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_DB_CONTAINER_PORT = "3306"
DEFAULT_DB_SERVICE_NAME = "db"
API_SERVICE_NAME = "api"
API_CONTAINER_NAME = "fastapi_cosmic_catalyst"
BASE_COMPOSE_FILE = "docker-compose.yml"
GPU_COMPOSE_FILE = "docker-compose.gpu.yml"
OLLAMA_COMPOSE_FILE = "docker-compose.ollama.yml"
VLLM_COMPOSE_FILE = "docker-compose.vllm.yml"
TRAINING_COMPOSE_FILE = "docker-compose.training.yml"
PACKAGE_NAME = "projectdavid_platform"
CHANGELOG_URL = "https://github.com/project-david-ai/platform/blob/master/CHANGELOG.md"

_BUNDLED_CONFIGS = [
    ("docker-compose.training.yml", "docker-compose.training.yml"),
    ("docker-compose.yml", "docker-compose.yml"),
    ("docker-compose.ollama.yml", "docker-compose.ollama.yml"),
    ("docker-compose.vllm.yml", "docker-compose.vllm.yml"),
    ("docker-compose.gpu.yml", "docker-compose.gpu.yml"),
    ("docker/nginx/nginx.conf", "docker/nginx/nginx.conf"),
    ("docker/otel/otel-config.yaml", "docker/otel/otel-config.yaml"),
    ("docker/searxng/settings.yml", "docker/searxng/settings.yml"),
]

_DOCKER_INSTALL_URLS = {
    "windows": "https://docs.docker.com/desktop/install/windows-install/",
    "darwin": "https://docs.docker.com/desktop/install/mac-install/",
    "linux": "https://docs.docker.com/engine/install/",
}
_DOCKER_COMPOSE_INSTALL_URL = "https://docs.docker.com/compose/install/"
_NVIDIA_TOOLKIT_INSTALL_URL = "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"


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
    except (FileNotFoundError, ModuleNotFoundError, TypeError):
        log.warning(
            "Compose file '%s' not found locally or in installed package. "
            "Try reinstalling: pip install --force-reinstall projectdavid-platform",
            filename,
        )
        return filename


# ---------------------------------------------------------------------------
# Typer app
# ---------------------------------------------------------------------------
_TYPER_HELP = (
    "Deployment orchestrator for the Project David / Entities platform.\n\n"
    "Install:    pip install projectdavid-platform\n"
    "Base stack: pdavid --mode up\n"
    "Training:   pdavid --mode up --training\n"
    "Config:     pdavid configure --set HF_TOKEN=hf_abc123\n"
    "Admin:      pdavid bootstrap-admin"
)

app = typer.Typer(name="pdavid", help=_TYPER_HELP, add_completion=False)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class Orchestrator:
    _ENV_FILE = ".env"
    _ENV_EXAMPLE_FILE = ".env.example"

    _GENERATED_SECRETS = [
        "SIGNED_URL_SECRET",
        "API_KEY",
        "MYSQL_ROOT_PASSWORD",
        "MYSQL_PASSWORD",
        "SECRET_KEY",
        "DEFAULT_SECRET_KEY",
        "SANDBOX_AUTH_SECRET",
        "SMBCLIENT_PASSWORD",
        "SEARXNG_SECRET_KEY",
        "ADMIN_API_KEY",
    ]

    _GENERATED_TOOL_IDS = [
        "TOOL_CODE_INTERPRETER",
        "TOOL_WEB_SEARCH",
        "TOOL_COMPUTER",
        "TOOL_VECTOR_STORE_SEARCH",
    ]

    _USER_REQUIRED = {
        "HF_TOKEN": (
            "HF_TOKEN",
            "HuggingFace access token (required for gated models).",
            True,
        ),
    }

    _DANGEROUS_ROTATION = {
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "SMBCLIENT_PASSWORD",
    }
    _REQUIRES_DOWN = {"SECRET_KEY", "DEFAULT_SECRET_KEY", "ADMIN_API_KEY"}

    _INSECURE_VALUES = {"default", "changeme", "your_secret_key_here", ""}

    _DEFAULT_VALUES = {
        "TRAINING_PROFILE": "laptop",
        "RAY_ADDRESS": "",
        "RAY_DASHBOARD_PORT": "8265",
        "ASSISTANTS_BASE_URL": "http://localhost:80",
        "SANDBOX_SERVER_URL": "http://sandbox:8000",
        "DOWNLOAD_BASE_URL": "http://localhost:80/v1/files/download",
        "VLLM_MODEL": "Qwen/Qwen2.5-VL-3B-Instruct",
        "MYSQL_HOST": DEFAULT_DB_SERVICE_NAME,
        "MYSQL_PORT": DEFAULT_DB_CONTAINER_PORT,
        "MYSQL_DATABASE": "entities_db",
        "MYSQL_USER": "api_user",
        "REDIS_URL": "redis://redis:6379/0",
        "ADMIN_USER_EMAIL": "admin@example.com",
    }

    _SUMMARY_KEYS = [
        "DATABASE_URL",
        "SPECIAL_DB_URL",
        "SHARED_PATH",
    ]

    def __init__(self, args: SimpleNamespace) -> None:
        self.args = args
        self.is_windows = _platform.system() == "Windows"
        self.log = log
        if getattr(self.args, "verbose", False):
            self.log.setLevel(logging.DEBUG)

        self._ensure_config_files()
        self.base_compose = _resolve_compose_file(BASE_COMPOSE_FILE)
        self.gpu_compose = _resolve_compose_file(GPU_COMPOSE_FILE)
        self.ollama_compose = _resolve_compose_file(OLLAMA_COMPOSE_FILE)
        self.vllm_compose = _resolve_compose_file(VLLM_COMPOSE_FILE)
        self.training_compose = _resolve_compose_file(TRAINING_COMPOSE_FILE)

        self.compose_config = self._load_compose_config()
        self._check_for_required_env_file()
        self._configure_shared_path()
        self._configure_hf_cache_path()

        if getattr(self.args, "training", False):
            self._merge_env_for_overlay("training")

    @property
    def _env_file_abs(self) -> str:
        return str(Path(self._ENV_FILE).resolve())

    def _ensure_config_files(self) -> None:
        for pkg_rel, cwd_rel in _BUNDLED_CONFIGS:
            dest = Path.cwd() / cwd_rel
            if dest.exists() and dest.is_dir():
                shutil.rmtree(dest)
            if dest.exists():
                continue
            try:
                pkg_files = importlib.resources.files(PACKAGE_NAME)
                resource = pkg_files
                for part in pkg_rel.split("/"):
                    resource = resource / part
                with importlib.resources.as_file(resource) as src:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
            except Exception as e:
                self.log.warning("Could not install config '%s': %s", cwd_rel, e)

    def _generate_dot_env_file(self):
        self.log.info("Generating '%s' with secure defaults...", self._ENV_FILE)
        env_values = dict(self._DEFAULT_VALUES)

        for key in self._GENERATED_SECRETS:
            env_values[key] = (
                f"ad_{secrets.token_urlsafe(32)}"
                if "KEY" in key
                else secrets.token_hex(32)
            )

        for key in self._GENERATED_TOOL_IDS:
            env_values[key] = f"tool_{secrets.token_hex(10)}"

        db_pass = env_values.get("MYSQL_PASSWORD")
        escaped_pass = quote_plus(str(db_pass))
        env_values["DATABASE_URL"] = (
            f"mysql+pymysql://api_user:{escaped_pass}@db:3306/entities_db"
        )

        try:
            env_values["PDAVID_VERSION"] = importlib.metadata.version(PACKAGE_NAME)
        # LINT FIX (E722): Replaced bare except with Exception
        except Exception:
            env_values["PDAVID_VERSION"] = "latest"

        env_lines = [f"# Auto-generated by pdavid — {time.ctime()}", ""]
        for k, v in env_values.items():
            env_lines.append(f"{k}={v}")

        Path(self._ENV_FILE).write_text("\n".join(env_lines), encoding="utf-8")
        self.log.info("'%s' generated successfully.", self._ENV_FILE)

    def _print_summary(self, env_values: dict):
        typer.echo("\n" + "=" * 60)
        typer.echo("  Configuration Summary")
        typer.echo("=" * 60)
        for key in self._SUMMARY_KEYS:
            value = env_values.get(key, "<not set>")
            typer.echo(f"  {key:<24}: {value}")
        typer.echo("=" * 60)

    def _check_for_required_env_file(self):
        if not os.path.exists(self._ENV_FILE):
            self._generate_dot_env_file()
        load_dotenv(dotenv_path=self._ENV_FILE, override=True)

    def _merge_env_for_overlay(self, overlay: str) -> None:
        _OVERLAY_VARS = {
            "training": {
                "TRAINING_PROFILE": "laptop",
                "RAY_ADDRESS": "",
                "RAY_DASHBOARD_PORT": "8265",
            },
        }
        required = _OVERLAY_VARS.get(overlay, {})
        env_path = Path(self._ENV_FILE)
        content = env_path.read_text(encoding="utf-8")
        injected = False
        for key, default in required.items():
            if not re.search(rf"^{re.escape(key)}=", content, re.MULTILINE):
                content += f"\n{key}={default}"
                injected = True
        if injected:
            env_path.write_text(content, encoding="utf-8")
            self.log.info("Injected defaults for --%s overlay into .env", overlay)

    def _run_command(self, cmd_list, check=True, capture_output=False, **kwargs):
        try:
            return subprocess.run(
                cmd_list,
                check=check,
                capture_output=capture_output,
                text=True,
                shell=self.is_windows,
                **kwargs,
            )
        except subprocess.CalledProcessError:
            self.log.error("Command failed: %s", " ".join(cmd_list))
            raise

    def _compose_files(self) -> list:
        files = [
            "--project-directory",
            str(Path.cwd()),
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
        if getattr(self.args, "build_before_up", False):
            up_cmd.append("--build")
        if getattr(self.args, "pull", False):
            up_cmd.extend(["--pull", "always"])
        self._run_command(up_cmd)
        self.log.info("Stack started successfully.")

    def exec_bootstrap_admin(self, db_url: Optional[str] = None):
        resolved_db_url = db_url or os.environ.get("DATABASE_URL")
        cmd = (
            ["docker", "compose"]
            + self._compose_files()
            + [
                "exec",
                API_SERVICE_NAME,
                "python",
                "/app/src/api/entities_api/cli/bootstrap_admin.py",
                "--db-url",
                resolved_db_url,
            ]
        )
        self._run_command(cmd)
        self.log.info("bootstrap-admin complete.")

    def run(self):
        if getattr(self.args, "nuke", False):
            confirm = input("DANGER: This wipes ALL data. Type 'confirm nuke': ")
            if confirm == "confirm nuke":
                self._run_command(
                    ["docker", "compose"] + self._compose_files() + ["down", "-v"]
                )
                self.log.info("Data destroyed.")
            return

        mode = getattr(self.args, "mode", "up")
        if mode == "up":
            self._handle_up()

    def _load_compose_config(self):
        try:
            return yaml.safe_load(Path(self.base_compose).read_text())
        # LINT FIX (F841): Removed unused exception variable 'e'
        except Exception:
            return None

    def _configure_shared_path(self):
        path = os.environ.get("SHARED_PATH", "./shared_data")
        Path(path).mkdir(parents=True, exist_ok=True)

    def _configure_hf_cache_path(self):
        # LINT FIX (E722): Replaced bare except with Exception
        try:
            pass
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    mode: str = typer.Option("up", help="Action: up | build | logs"),
    training: bool = typer.Option(
        False, "--training", help="Enable Sovereign Forge stack."
    ),
    gpu: bool = typer.Option(False, "--gpu", help="Enable GPU overlays."),
    nuke: bool = typer.Option(False, "--nuke", help="Destroy everything."),
    pull: bool = typer.Option(False, "--pull", help="Pull latest images."),
    build_before_up: bool = typer.Option(False, "--build-before-up"),
    verbose: bool = typer.Option(False, "--verbose"),
):
    if ctx.invoked_subcommand:
        return
    args = SimpleNamespace(
        mode=mode,
        training=training,
        gpu=gpu,
        nuke=nuke,
        pull=pull,
        build_before_up=build_before_up,
        verbose=verbose,
    )
    Orchestrator(args).run()


@app.command(name="bootstrap-admin")
def bootstrap_admin(db_url: Optional[str] = None):
    """Provision the admin user inside the container."""
    args = SimpleNamespace(training=False, gpu=False)
    Orchestrator(args).exec_bootstrap_admin(db_url=db_url)


@app.command()
def configure(set_var: List[str] = typer.Option(None, "--set")):
    """Update .env variables."""
    env_path = Path(".env")
    content = env_path.read_text()
    for s in set_var:
        k, v = s.split("=")
        content = re.sub(rf"^{k}=.*", f"{k}={v}", content, flags=re.M)
    env_path.write_text(content)
    typer.echo("Config updated.")


if __name__ == "__main__":
    app()
