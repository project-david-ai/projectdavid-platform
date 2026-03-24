# start_orchestration.py
#
# Deployment orchestrator for the Project David / Entities platform.
#
# VERSION: 1.23.4-Full-Fix-with-Entrypoint
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
# start_orchestration.py
#
# Deployment orchestrator for the Project David / Entities platform.
# Distributed as part of the `projectdavid-platform` pip package.
#
# After `pip install projectdavid-platform`:
#
#   BASE STACK
#   pdavid --mode up                        # Core platform only
#   pdavid --mode up --pull                 # Pull latest images before starting
#   pdavid --mode up --exclude samba        # Start without a specific service
#   pdavid --mode up --services api db      # Start specific services only
#   pdavid --mode logs --follow             # Tail logs
#   pdavid --mode down_only                 # Stop the stack
#
#   GPU INFERENCE (opt-in, requires NVIDIA GPU + nvidia-container-toolkit)
#   pdavid --mode up --ollama               # Ollama only
#   pdavid --mode up --vllm                 # vLLM only (static server)
#   pdavid --mode up --gpu                  # Both Ollama + vLLM
#
#   SOVEREIGN FORGE — Training + Inference Mesh (opt-in, requires NVIDIA GPU)
#   pdavid --mode up --training             # Training pipeline + Ray cluster
#   pdavid --mode up --training --vllm      # + static vLLM inference server
#   pdavid --mode up --gpu --training       # Full sovereign stack
#
#   CONFIGURATION
#   pdavid configure --set HF_TOKEN=hf_abc123
#   pdavid configure --set TRAINING_PROFILE=standard
#   pdavid configure --set RAY_ADDRESS=ray://192.168.1.10:10001
#   pdavid configure --interactive
#   pdavid bootstrap-admin
#
# SCALE-OUT (adding a second GPU node to the Ray cluster):
#   On the remote machine, set RAY_ADDRESS=ray://<head_ip>:10001 in .env
#   then: docker compose -f docker-compose.yml -f docker-compose.training.yml up -d training-worker
#   Ray discovers the node automatically — no code changes required.





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
    from dotenv import load_dotenv, set_key
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
_NVIDIA_TOOLKIT_INSTALL_URL = (
    "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
)

_OWNED_SERVICES = {
    "api": API_CONTAINER_NAME,
    "sandbox": "sandbox_api",
}

_OWNED_IMAGES = {
    "api": "thanosprime/projectdavid-core-api",
    "sandbox": "thanosprime/projectdavid-core-sandbox",
}

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
    "Install:    pip install projectdavid-platform\n\n"
    "Base stack: pdavid --mode up\n"
    "Update:     pdavid --mode up --pull\n\n"
    "GPU inference (opt-in):\n"
    "  Ollama:   pdavid --mode up --ollama\n"
    "  vLLM:     pdavid --mode up --vllm\n"
    "  Both:     pdavid --mode up --gpu\n\n"
    "Sovereign Forge — training + inference mesh (opt-in):\n"
    "  Training: pdavid --mode up --training\n"
    "  Full:     pdavid --mode up --gpu --training\n\n"
    "Config:     pdavid configure --set HF_TOKEN=hf_abc123\n"
    "Admin:      pdavid bootstrap-admin"
)

app = typer.Typer(
    name="pdavid",
    help=_TYPER_HELP,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class Orchestrator:

    _ENV_FILE = ".env"
    _ENV_EXAMPLE_FILE = ".env.example"

    # ADMIN_API_KEY is intentionally excluded here.
    # It is generated and written only when `bootstrap-admin` is explicitly called.
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
            (
                "HuggingFace personal access token.\n"
                "  Required only for downloading gated models via vLLM.\n"
                "  Get one at: https://huggingface.co/settings/tokens"
            ),
            True,
        ),
    }

    _DANGEROUS_ROTATION = {
        "MYSQL_PASSWORD",
        "MYSQL_ROOT_PASSWORD",
        "SMBCLIENT_PASSWORD",
    }

    _REQUIRES_DOWN = {
        "SECRET_KEY",
        "DEFAULT_SECRET_KEY",
        "SIGNED_URL_SECRET",
        "SANDBOX_AUTH_SECRET",
        "SEARXNG_SECRET_KEY",
        "ADMIN_API_KEY",
    }

    _INSECURE_VALUES = {
        "default",
        "your_secret_key_here",
        "changeme",
        "changeme_use_a_real_secret",
        "change_me_root",
        "change_me_password",
        "change_me_secret_key",
        "",
    }

    _DEFAULT_VALUES = {
        "TRAINING_PROFILE": "laptop",
        # Ray: blank = this node starts as Ray head.
        # Set to ray://<head_ip>:10001 to join an existing cluster.
        "RAY_ADDRESS": "",
        "RAY_DASHBOARD_PORT": "8265",
        "VLLM_EXTRA_FLAGS": "",
        "ASSISTANTS_BASE_URL": "http://localhost:80",
        "SANDBOX_SERVER_URL": "http://sandbox:8000",
        "DOWNLOAD_BASE_URL": "http://localhost:80/v1/files/download",
        "HF_TOKEN": "",
        "HF_CACHE_PATH": "",
        "VLLM_MODEL": "Qwen/Qwen2.5-VL-3B-Instruct",
        "BASE_URL_HEALTH": "http://localhost:80/v1/health",
        "SHELL_SERVER_URL": "ws://sandbox:8000/ws/computer",
        "SHELL_SERVER_EXTERNAL_URL": "ws://localhost:8000/ws/computer",
        "CODE_EXECUTION_URL": "ws://sandbox:8000/ws/execute",
        "DISABLE_FIREJAIL": "true",
        "SHARED_PATH": "./shared_data",
        "AUTO_MIGRATE": "1",
        "MYSQL_HOST": DEFAULT_DB_SERVICE_NAME,
        "MYSQL_PORT": DEFAULT_DB_CONTAINER_PORT,
        "MYSQL_DATABASE": "entities_db",
        "MYSQL_USER": "api_user",
        "REDIS_URL": "redis://redis:6379/0",
        "ADMIN_USER_EMAIL": "admin@example.com",
        "ADMIN_USER_ID": "",
        "ADMIN_KEY_PREFIX": "",
        "SMBCLIENT_SERVER": "samba_server",
        "SMBCLIENT_SHARE": "cosmic_share",
        "SMBCLIENT_USERNAME": "samba_user",
        "SMBCLIENT_PORT": "445",
        "SAMBA_USERID": "1000",
        "SAMBA_GROUPID": "1000",
        "LOG_LEVEL": "INFO",
        "PYTHONUNBUFFERED": "1",
        # Inference provider base URLs — required for hosted model routing.
        # Add your API keys via: pdavid configure --set HYPERBOLIC_API_KEY=...
        "HYPERBOLIC_BASE_URL": "https://api.hyperbolic.xyz/v1",
        "TOGETHER_BASE_URL": "https://api.together.xyz/v1",
    }

    _ENV_STRUCTURE = {
        "Base URLs": [
            "ASSISTANTS_BASE_URL",
            "SANDBOX_SERVER_URL",
            "DOWNLOAD_BASE_URL",
        ],
        "AI Model Configuration": [
            "HF_TOKEN",
            "HF_CACHE_PATH",
            "VLLM_MODEL",
        ],
        "Inference Providers": [
            "HYPERBOLIC_BASE_URL",
            "TOGETHER_BASE_URL",
        ],
        "Database Configuration": [
            "DATABASE_URL",
            "SPECIAL_DB_URL",
            "MYSQL_ROOT_PASSWORD",
            "MYSQL_DATABASE",
            "MYSQL_USER",
            "MYSQL_PASSWORD",
            "MYSQL_HOST",
            "MYSQL_PORT",
            "REDIS_URL",
        ],
        "API Keys & Secrets": [
            "API_KEY",
            "ADMIN_API_KEY",
            "SIGNED_URL_SECRET",
            "SANDBOX_AUTH_SECRET",
            "SECRET_KEY",
            "DEFAULT_SECRET_KEY",
            "SEARXNG_SECRET_KEY",
        ],
        "Platform Settings": [
            "BASE_URL_HEALTH",
            "SHELL_SERVER_URL",
            "SHELL_SERVER_EXTERNAL_URL",
            "CODE_EXECUTION_URL",
            "DISABLE_FIREJAIL",
            "SHARED_PATH",
            "AUTO_MIGRATE",
        ],
        "Admin Configuration": [
            "ADMIN_USER_EMAIL",
            "ADMIN_USER_ID",
            "ADMIN_KEY_PREFIX",
        ],
        "SMB Client Configuration": [
            "SMBCLIENT_SERVER",
            "SMBCLIENT_SHARE",
            "SMBCLIENT_USERNAME",
            "SMBCLIENT_PASSWORD",
            "SMBCLIENT_PORT",
        ],
        "Samba Server Configuration": [
            "SAMBA_USERID",
            "SAMBA_GROUPID",
        ],
        "Training Stack": [
            "TRAINING_PROFILE",
            "RAY_ADDRESS",
            "RAY_DASHBOARD_PORT",
        ],
        "Tool Identifiers": [
            "TOOL_CODE_INTERPRETER",
            "TOOL_WEB_SEARCH",
            "TOOL_COMPUTER",
            "TOOL_VECTOR_STORE_SEARCH",
        ],
        "Other": [
            "PDAVID_VERSION",
            "LOG_LEVEL",
            "PYTHONUNBUFFERED",
        ],
    }

    _SUMMARY_KEYS = [
        "API_KEY",
        "ADMIN_API_KEY",
        "DATABASE_URL",
        "SPECIAL_DB_URL",
        "SHARED_PATH",
    ]

    # ------------------------------------------------------------------
    def __init__(self, args: SimpleNamespace) -> None:
        self.args = args
        self.is_windows = _platform.system() == "Windows"
        self.log = log
        if getattr(self.args, "verbose", False):
            self.log.setLevel(logging.DEBUG)

        # Must run first — installs bundled configs and wins Docker race condition.
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
        # ----------------------------------------
        # Inject any missing overlay-specific env vars into .env
        # This runs before _handle_up() so the vars are live in the environment
        # before docker compose reads them.
        # -----------------------------------------
        if getattr(self.args, "training", False):
            self._merge_env_for_overlay("training")

        self._ensure_dockerignore()

    # ------------------------------------------------------------------
    # .env path helpers
    # ------------------------------------------------------------------

    @property
    def _env_file_abs(self) -> str:
        return str(Path(self._ENV_FILE).resolve())

    # ------------------------------------------------------------------
    # Version upgrade notice
    # ------------------------------------------------------------------

    def _check_version_upgrade(self) -> None:
        """
        Compare the installed package version against PDAVID_VERSION in .env.

        If they differ the user has upgraded via pip since the last run.
        Prints a notice with a changelog link and updates PDAVID_VERSION in
        .env so the notice only fires once per upgrade.

        Never pulls images automatically — the user decides when to apply
        the update via: pdavid --mode up --pull

        The compose file always uses :latest so no image tag coupling exists.
        PDAVID_VERSION in .env is used solely for this notice.
        """
        try:
            installed = importlib.metadata.version("projectdavid-platform")
        except importlib.metadata.PackageNotFoundError:
            return

        env_version = os.environ.get("PDAVID_VERSION", "").strip()

        if not env_version:
            # First run — write the version silently, no notice needed.
            self._write_pdavid_version(installed)
            return

        if env_version == installed:
            return

        # Version mismatch — user has upgraded via pip.
        typer.echo("\n" + "=" * 60)
        typer.echo("  Platform update detected")
        typer.echo("=" * 60)
        typer.echo(f"  Installed : {installed}")
        typer.echo(f"  Running   : {env_version}")
        typer.echo(
            "\n  New features and fixes are available.\n"
            f"  What's new: {CHANGELOG_URL}\n\n"
            "  To apply the update and pull the latest container images:\n\n"
            "    pdavid --mode up --pull\n\n"
            "  Your data and secrets are not affected.\n"
        )
        typer.echo("=" * 60 + "\n")

        # Update .env so the notice doesn't repeat on every run.
        self._write_pdavid_version(installed)

    def _write_pdavid_version(self, version: str) -> None:
        """Write or update PDAVID_VERSION in .env in-place."""
        try:
            env_path = Path(self._ENV_FILE)
            if not env_path.exists():
                return
            set_key(str(env_path), "PDAVID_VERSION", version)
            os.environ["PDAVID_VERSION"] = version
        except Exception as e:
            self.log.debug("Could not update PDAVID_VERSION in .env: %s", e)

    # ------------------------------------------------------------------
    # Config file bootstrap
    # ------------------------------------------------------------------

    def _ensure_config_files(self) -> None:
        """
        Copy bundled files into the user's CWD before Docker Compose starts.
        Detects and replaces directories created by Docker's race condition.
        Never overwrites existing files — local customisations are preserved.
        """
        copied = []

        for pkg_rel, cwd_rel in _BUNDLED_CONFIGS:
            dest = Path.cwd() / cwd_rel

            if dest.exists() and dest.is_dir():
                self.log.warning(
                    "Found a directory at '%s' — Docker created it before the config "
                    "file could be installed. Replacing with the correct bundled file.",
                    cwd_rel,
                )
                try:
                    shutil.rmtree(dest)
                except Exception as e:
                    self.log.warning(
                        "Could not remove spurious directory '%s': %s. "
                        "Please delete it manually and re-run pdavid.",
                        cwd_rel,
                        e,
                    )
                    continue

            if dest.exists():
                self.log.debug("Config file already present — skipping: %s", cwd_rel)
                continue

            try:
                pkg_files = importlib.resources.files(PACKAGE_NAME)
                resource = pkg_files
                for part in pkg_rel.split("/"):
                    resource = resource / part

                with importlib.resources.as_file(resource) as src:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    copied.append(cwd_rel)
                    self.log.info("Installed config: %s", cwd_rel)

            except Exception as e:
                self.log.warning(
                    "Could not install bundled config '%s': %s. "
                    "Reinstall with: pip install --force-reinstall projectdavid-platform",
                    cwd_rel,
                    e,
                )

        if copied:
            typer.echo(
                f"\n  Installed {len(copied)} file(s) to CWD:\n"
                + "\n".join(f"    {f}" for f in copied)
                + "\n  Edit them freely — pdavid will never overwrite local copies.\n"
            )

    # ------------------------------------------------------------------
    # Preflight
    # ------------------------------------------------------------------

    def _has_docker(self) -> bool:
        if shutil.which("docker"):
            return True
        system = _platform.system().lower()
        install_url = _DOCKER_INSTALL_URLS.get(system, "https://docs.docker.com/get-docker/")
        typer.echo(
            "\nDocker is not installed or not found in PATH.\n"
            f"Install Docker for your platform: {install_url}\n"
            "Once installed, re-run: pdavid --mode up\n",
            err=True,
        )
        return False

    def _has_docker_compose(self) -> bool:
        try:
            self._run_command(
                ["docker", "compose", "version"],
                check=True,
                capture_output=True,
                suppress_logs=True,
            )
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            typer.echo(
                "\nThe Docker Compose plugin is not available.\n"
                f"Install it: {_DOCKER_COMPOSE_INSTALL_URL}\n"
                "Once installed, re-run: pdavid --mode up\n",
                err=True,
            )
            return False

    def _has_nvidia_support(self) -> bool:
        cmd = shutil.which("nvidia-smi")
        if not cmd:
            return False
        try:
            self._run_command([cmd], check=True, capture_output=True, suppress_logs=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _validate_gpu_prereqs(self, flag: str) -> bool:
        """Validate NVIDIA prereqs before starting any GPU service."""
        if self._has_nvidia_support():
            self.log.info("NVIDIA GPU support confirmed.")
            return True
        typer.echo(
            f"\nGPU service requested ({flag}) but NVIDIA drivers / nvidia-smi not found.\n"
            "Requirements:\n"
            "  1. NVIDIA GPU with drivers installed\n"
            f"  2. NVIDIA Container Toolkit: {_NVIDIA_TOOLKIT_INSTALL_URL}\n"
            "\nTo start without GPU services, omit the GPU flags:\n"
            "  pdavid --mode up\n",
            err=True,
        )
        return False

    def _preflight(self) -> bool:
        self.log.debug("Running preflight dependency checks...")
        if not self._has_docker():
            return False
        if not self._has_docker_compose():
            return False

        training = getattr(self.args, "training", False)
        if training and not self._validate_gpu_prereqs("--training"):
            return False
        # -------------------------------------------------------------------
        # Port conflict check for --training overlay
        # Format: {port: (description, "error"|"warn")}
        # "error" = hard stop, "warn" = logged but not blocking
        # (worker handles vLLM port eviction itself so 8001 is warn-only)
        # ---------------------------------------------------------------------
        if training and not self._check_port_conflicts(
            {
                9001: ("training-api", "error"),
                8265: ("Ray dashboard", "error"),
                10001: ("Ray client", "error"),
                8001: ("vLLM spawn port", "warn"),
            }
        ):
            return False

        gpu = getattr(self.args, "gpu", False)
        ollama = getattr(self.args, "ollama", False)
        vllm = getattr(self.args, "vllm", False)

        if gpu and not self._validate_gpu_prereqs("--gpu"):
            return False
        if ollama and not gpu and not self._validate_gpu_prereqs("--ollama"):
            return False
        if vllm and not gpu and not self._validate_gpu_prereqs("--vllm"):
            return False

        self.log.debug("Preflight checks passed.")
        return True

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------
    def _compose_files(self) -> list:
        """
        Builds the compose file flag list for docker compose commands.

        Flag behaviour:
          --gpu      → base + gpu overlay (both ollama + vllm)
          --ollama   → base + ollama overlay only
          --vllm     → base + vllm overlay only
          --training → base + training overlay (training-api + training-worker + Ray)
          Flags are additive — any combination is valid.
        """
        files = [
            "--project-directory",
            str(Path.cwd()),
            "--env-file",
            self._env_file_abs,
            "-f",
            self.base_compose,
        ]

        gpu = getattr(self.args, "gpu", False)
        ollama = getattr(self.args, "ollama", False)
        vllm = getattr(self.args, "vllm", False)
        training = getattr(self.args, "training", False)

        if gpu:
            files += ["-f", self.gpu_compose]
        else:
            if ollama:
                files += ["-f", self.ollama_compose]
            if vllm:
                files += ["-f", self.vllm_compose]

        # Training is independent of GPU inference overlays — always additive
        if training:
            files += ["-f", self.training_compose]

        return files

    def _get_all_services(self) -> List[str]:
        if not self.compose_config:
            return []
        return list(self.compose_config.get("services", {}).keys())

    def _run_command(
        self, cmd_list, check=True, capture_output=False, text=True, suppress_logs=False, **kwargs
    ):
        if not suppress_logs:
            self.log.info("Running: %s", " ".join(cmd_list))
        try:
            result = subprocess.run(
                cmd_list,
                check=check,
                capture_output=capture_output,
                text=text,
                shell=self.is_windows,
                **kwargs,
            )
            return result
        except subprocess.CalledProcessError as e:
            self.log.error("Command failed (code %s): %s", e.returncode, " ".join(cmd_list))
            if e.stdout:
                self.log.error("STDOUT:\n%s", e.stdout.strip())
            if e.stderr:
                self.log.error("STDERR:\n%s", e.stderr.strip())
            if check:
                raise
            return e
        except Exception as e:
            self.log.error("Error running %s: %s", " ".join(cmd_list), e)
            raise

    def _ensure_dockerignore(self):
        di = Path(".dockerignore")
        if not di.exists():
            di.write_text(
                "__pycache__/\n.venv/\nnode_modules/\n*.log\n*.pyc\n.git/\n"
                ".env*\n.env\n*.sqlite\ndist/\nbuild/\ncoverage/\ntmp/\n*.egg-info/\n"
            )

    def _load_compose_config(self):
        p = Path(self.base_compose)
        if not p.is_file():
            return None
        try:
            return yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            self.log.error("Error parsing %s: %s", self.base_compose, e)
            return None

    def _get_host_port_from_compose_service(self, service_name, container_port):
        if not self.compose_config:
            return None
        try:
            ports = self.compose_config.get("services", {}).get(service_name, {}).get("ports", [])
            container_port_base = str(container_port).split("/")[0]
            for mapping in ports:
                parts = str(mapping).split(":")
                if len(parts) == 2:
                    host_p, cont_p = parts
                elif len(parts) == 3:
                    host_p, cont_p = parts[1], parts[2]
                else:
                    continue
                if cont_p.split("/")[0] == container_port_base:
                    return host_p.strip()
        except Exception as e:
            self.log.error("Error parsing ports for %s: %s", service_name, e)
        return None

    # ------------------------------------------------------------------
    # .env generation
    # ------------------------------------------------------------------

    def _prompt_user_required(self, env_values: dict, generation_log: dict):
        inherited = {}
        needs_prompt = {}
        for key, meta in self._USER_REQUIRED.items():
            shell_value = os.environ.get(key, "").strip()
            if shell_value:
                inherited[key] = shell_value
                env_values[key] = shell_value
                generation_log[key] = "Inherited from shell environment"
                self.log.info("'%s' already set in environment — skipping prompt.", key)
            else:
                needs_prompt[key] = meta

        if inherited:
            typer.echo(f"\n  Inherited from environment: {', '.join(inherited.keys())}")

        if not needs_prompt:
            return

        if not sys.stdin.isatty():
            self.log.warning(
                "Non-interactive environment. User-required variables left blank: %s. "
                "Set them with: pdavid configure --set KEY=VALUE",
                ", ".join(needs_prompt.keys()),
            )
            return

        typer.echo("\n" + "=" * 60)
        typer.echo("  Optional: User-Supplied Configuration")
        typer.echo("=" * 60)
        typer.echo(
            "  The following values cannot be auto-generated.\n"
            "  Press Enter to skip — the stack will start fine without\n"
            "  them, but related features will be unavailable until set.\n"
            "\n"
            "  Set them any time later with:\n"
            "    pdavid configure --interactive\n"
            "    pdavid configure --set KEY=value\n"
        )
        for key, (label, help_text, hide) in needs_prompt.items():
            typer.echo(f"  {help_text}\n")
            value = typer.prompt(
                f"  {label} (press Enter to skip)",
                default="",
                show_default=False,
                hide_input=hide,
            )
            if value.strip():
                env_values[key] = value.strip()
                generation_log[key] = "Provided interactively by user"
                typer.echo(f"  {key} saved.\n")
            else:
                self.log.warning("'%s' skipped. Run: pdavid configure --set %s=<value>", key, key)
        typer.echo("=" * 60 + "\n")

    def _generate_dot_env_file(self):
        self.log.info("Generating '%s'...", self._ENV_FILE)
        env_values = dict(self._DEFAULT_VALUES)
        generation_log = {k: "Default value" for k in env_values}

        for key in self._GENERATED_SECRETS:
            if key == "API_KEY":
                env_values[key] = f"ea_{secrets.token_urlsafe(16)}"
            else:
                env_values[key] = secrets.token_hex(32)
            generation_log[key] = "Generated new secret (forced)"

        for key in self._GENERATED_TOOL_IDS:
            env_values[key] = f"tool_{secrets.token_hex(10)}"
            generation_log[key] = "Generated new tool ID"

        db_user = env_values.get("MYSQL_USER")
        db_pass = env_values.get("MYSQL_PASSWORD")
        db_host = env_values.get("MYSQL_HOST", DEFAULT_DB_SERVICE_NAME)
        db_port = env_values.get("MYSQL_PORT", DEFAULT_DB_CONTAINER_PORT)
        db_name = env_values.get("MYSQL_DATABASE")
        if all([db_user, db_pass, db_host, db_port, db_name]):
            escaped = quote_plus(str(db_pass))
            env_values["DATABASE_URL"] = (
                f"mysql+pymysql://{db_user}:{escaped}@{db_host}:{db_port}/{db_name}"
            )
            generation_log["DATABASE_URL"] = "Constructed from DB components (internal)"
            host_port = self._get_host_port_from_compose_service(
                DEFAULT_DB_SERVICE_NAME, DEFAULT_DB_CONTAINER_PORT
            )
            if host_port:
                env_values["SPECIAL_DB_URL"] = (
                    f"mysql+pymysql://{db_user}:{escaped}@localhost:{host_port}/{db_name}"
                )
                generation_log["SPECIAL_DB_URL"] = f"Constructed using host port ({host_port})"

        if not env_values.get("HF_CACHE_PATH"):
            env_values["HF_CACHE_PATH"] = os.path.join(
                os.path.expanduser("~"), ".cache", "huggingface"
            )
            generation_log["HF_CACHE_PATH"] = f"Auto-resolved for {_platform.system()}"

        # PDAVID_VERSION is stored in .env solely to power the upgrade notice.
        # It is NOT used to pin image tags — the compose file always uses :latest.
        try:
            env_values["PDAVID_VERSION"] = importlib.metadata.version("projectdavid-platform")
            generation_log["PDAVID_VERSION"] = "Auto-resolved from installed package"
        except importlib.metadata.PackageNotFoundError:
            env_values["PDAVID_VERSION"] = "latest"
            generation_log["PDAVID_VERSION"] = "Package not found — defaulting to latest"

        self._prompt_user_required(env_values, generation_log)

        env_lines = [
            f"# Auto-generated by projectdavid-platform — {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            "# Update optional values any time with:",
            "#   pdavid configure --set HF_TOKEN=<token>",
            "#   pdavid configure --interactive",
            "",
        ]
        processed: set = set()
        for section, keys in self._ENV_STRUCTURE.items():
            env_lines += [
                "#############################",
                f"# {section}",
                "#############################",
            ]
            found = False
            for key in keys:
                if key in env_values:
                    value = str(env_values[key])
                    if any(c in value for c in [" ", "#", "="]):
                        esc = value.replace("\\", "\\\\").replace('"', '\\"')
                        env_lines.append(f'{key}="{esc}"')
                    else:
                        env_lines.append(f"{key}={value}")
                    processed.add(key)
                    found = True
            if not found:
                env_lines.append("# (No variables configured for this section)")
            env_lines.append("")

        remaining = sorted(set(env_values.keys()) - processed)
        if remaining:
            env_lines += [
                "#############################",
                "# Other (Uncategorized)",
                "#############################",
            ]
            for key in remaining:
                value = str(env_values[key])
                if any(c in value for c in [" ", "#", "="]):
                    esc = value.replace("\\", "\\\\").replace('"', '\\"')
                    env_lines.append(f'{key}="{esc}"')
                else:
                    env_lines.append(f"{key}={value}")
            env_lines.append("")

        Path(self._ENV_FILE).write_text("\n".join(env_lines), encoding="utf-8")
        self.log.info("'%s' generated successfully.", self._ENV_FILE)
        self._print_summary(env_values)

    def _print_summary(self, env_values: dict):
        typer.echo("\n" + "=" * 60)
        typer.echo("  Key Configuration Summary")
        typer.echo("  (Do not share this output — it contains live secrets)")
        typer.echo("=" * 60)
        for key in self._SUMMARY_KEYS:
            value = env_values.get(key, "<not set>")
            typer.echo(f"  {key:<24}: {value}")
        typer.echo("=" * 60)
        typer.echo(
            "\n  Use ADMIN_API_KEY to bootstrap the admin user:\n" "    pdavid bootstrap-admin\n"
        )

    def _check_for_required_env_file(self):
        if not os.path.exists(self._ENV_FILE):
            self.log.warning("'%s' not found — generating...", self._ENV_FILE)
            self._generate_dot_env_file()
        else:
            self.log.info("'%s' exists — loading.", self._ENV_FILE)
            load_dotenv(dotenv_path=self._ENV_FILE, override=True)

    def _configure_shared_path(self):
        system = _platform.system().lower()
        shared_path = os.environ.get("SHARED_PATH")
        if not shared_path:
            base = os.path.expanduser("~")
            shared_path = {
                "windows": os.path.join(base, "entities_share"),
                "linux": os.path.join(base, ".local", "share", "entities_share"),
                "darwin": os.path.join(base, "Library", "Application Support", "entities_share"),
            }.get(system, os.path.abspath("./entities_share"))
            os.environ["SHARED_PATH"] = shared_path
            self.log.info("Defaulting SHARED_PATH to: %s", shared_path)
        try:
            Path(shared_path).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.log.error("Failed to create shared directory %s: %s", shared_path, e)

    def _configure_hf_cache_path(self):
        hf_path = os.environ.get("HF_CACHE_PATH", "").strip()
        if not hf_path:
            hf_path = os.path.join(os.path.expanduser("~"), ".cache", "huggingface")
            os.environ["HF_CACHE_PATH"] = hf_path
            self.log.info("Defaulting HF_CACHE_PATH to: %s", hf_path)

    def _merge_env_for_overlay(self, overlay: str) -> None:
        """
        Safely injects variables required by a new overlay into an existing .env
        without touching any values that are already set.

        Called when --training (or future overlays) are added to a running stack.
        Never regenerates secrets. Never overwrites existing values.
        Logs every variable it adds so the user knows exactly what changed.

        overlay: one of "training", "ollama", "vllm", "gpu"
        """
        # Variables required per overlay — only injected if absent from .env
        _OVERLAY_VARS = {
            "training": {
                "TRAINING_PROFILE": "laptop",
                "RAY_ADDRESS": "",
                "RAY_DASHBOARD_PORT": "8265",
            },
            # Future overlays can declare their own required vars here
            "ollama": {},
            "vllm": {},
            "gpu": {},
        }

        required = _OVERLAY_VARS.get(overlay, {})
        if not required:
            return

        env_path = Path(self._ENV_FILE)
        if not env_path.exists():
            self.log.debug(
                "_merge_env_for_overlay: .env not found — skipping merge for '%s'", overlay
            )
            return

        content = env_path.read_text(encoding="utf-8")
        injected = []

        for key, default in required.items():
            # Check both the file content and the live environment
            if re.search(rf"^{re.escape(key)}=", content, re.MULTILINE):
                self.log.debug("_merge_env_for_overlay: '%s' already in .env — skipping.", key)
                continue
            if os.environ.get(key, "").strip():
                self.log.debug(
                    "_merge_env_for_overlay: '%s' already in environment — skipping.", key
                )
                continue

            # Inject at end of file with a section comment on first injection
            if not injected:
                content += f"\n# Added by pdavid --training overlay\n"
            content += f"{key}={default}\n"
            os.environ[key] = default
            injected.append(key)
            self.log.info("_merge_env_for_overlay: injected '%s=%s' into .env", key, default)

        if injected:
            env_path.write_text(content, encoding="utf-8")
            typer.echo(
                f"\n  ✚ Added {len(injected)} variable(s) to .env for --{overlay} overlay:\n"
                + "\n".join(f"    {k}" for k in injected)
                + "\n  Edit them any time: pdavid configure --set KEY=VALUE\n"
            )
        else:
            self.log.debug(
                "_merge_env_for_overlay: all required vars for '%s' already present.", overlay
            )

    def _check_port_conflicts(self, ports: dict) -> bool:
        """
        Checks whether required host ports are already bound before starting
        an overlay. Gives the user a clear actionable error instead of a
        cryptic Docker compose failure.

        Args:
            ports: dict of {port_number: service_description}
                    e.g. {9001: "training-api", 8265: "Ray dashboard"}

        Returns:
            True  — all ports are free, safe to proceed
            False — one or more ports are already in use, startup blocked
        """
        import socket as _socket

        blocked = []
        warned = []

        for port, description in ports.items():
            severity = ports[port] if isinstance(ports[port], tuple) else (ports[port], "error")
            if isinstance(severity, tuple):
                label, level = severity
            else:
                label, level = severity, "error"

            try:
                with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    result = sock.connect_ex(("127.0.0.1", port))
                    in_use = result == 0
            except Exception:
                in_use = False

            if in_use:
                if level == "warn":
                    warned.append((port, label))
                else:
                    blocked.append((port, label))

        if warned:
            for port, label in warned:
                self.log.warning(
                    "Port %s (%s) appears to be in use. "
                    "The worker will attempt to evict the existing container automatically.",
                    port,
                    label,
                )

        if blocked:
            typer.echo("\n" + "=" * 60, err=True)
            typer.echo("  Port conflict — startup blocked", err=True)
            typer.echo("=" * 60, err=True)
            for port, label in blocked:
                typer.echo(f"  ✗  Port {port} ({label}) is already in use.", err=True)
            typer.echo(
                "\n  Free the ports above and re-run, or stop the conflicting service:\n"
                "    pdavid --mode down\n"
                "  Then:\n"
                "    pdavid --mode up --training\n",
                err=True,
            )
            typer.echo("=" * 60 + "\n", err=True)
            return False

        return True

    # ------------------------------------------------------------------
    # Secret validation
    # ------------------------------------------------------------------

    def _validate_secrets(self):
        failed = False
        for key in self._GENERATED_SECRETS:
            if os.environ.get(key, "") in self._INSECURE_VALUES:
                self.log.error(
                    "Insecure value for '%s'. Delete .env and re-run to regenerate.", key
                )
                failed = True
        if failed:
            raise SystemExit(1)
        for key in self._USER_REQUIRED:
            if not os.environ.get(key, "").strip():
                self.log.warning(
                    "'%s' not set — vLLM/HuggingFace features unavailable. "
                    "Set with: pdavid configure --set %s=<value>",
                    key,
                    key,
                )

    # ------------------------------------------------------------------
    # Container checks
    # ------------------------------------------------------------------

    def _is_container_running(self, container_name: str) -> bool:
        try:
            result = self._run_command(
                ["docker", "ps", "--filter", f"name=^{container_name}$", "--format", "{{.Names}}"],
                capture_output=True,
                check=False,
                suppress_logs=True,
            )
            return result.stdout.strip() == container_name
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Admin key management — called only from bootstrap_admin()
    # ------------------------------------------------------------------

    def _provision_admin_api_key(self) -> str:
        """
        Generate a fresh ADMIN_API_KEY, persist it to .env, reload the
        environment, and return the plaintext key so the caller can
        display it once to the operator.

        If ADMIN_API_KEY is already present and non-empty in .env the
        existing value is returned unchanged (idempotent re-runs).
        """
        env_path = Path(self._ENV_FILE)
        content = env_path.read_text(encoding="utf-8")

        existing = os.environ.get("ADMIN_API_KEY", "").strip()
        if existing and existing not in self._INSECURE_VALUES:
            self.log.info("ADMIN_API_KEY already present in .env — reusing.")
            return existing

        new_key = f"ad_{secrets.token_urlsafe(32)}"

        # Replace in-place if the placeholder line exists, otherwise append.
        if re.search(r"^ADMIN_API_KEY=", content, re.MULTILINE):
            content = re.sub(
                r"^ADMIN_API_KEY=.*",
                f"ADMIN_API_KEY={new_key}",
                content,
                flags=re.MULTILINE,
            )
        else:
            content += f"\nADMIN_API_KEY={new_key}\n"

        env_path.write_text(content, encoding="utf-8")
        os.environ["ADMIN_API_KEY"] = new_key
        self.log.info("ADMIN_API_KEY written to .env.")
        return new_key

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _handle_up(self):
        load_dotenv(dotenv_path=self._ENV_FILE, override=True)
        self._validate_secrets()
        self._check_version_upgrade()

        up_cmd = ["docker", "compose"] + self._compose_files() + ["up"]
        if not getattr(self.args, "attached", False):
            up_cmd.append("-d")
        if getattr(self.args, "build_before_up", False):
            up_cmd.append("--build")
        if getattr(self.args, "force_recreate", False):
            up_cmd.append("--force-recreate")
        if getattr(self.args, "pull", False):
            up_cmd.extend(["--pull", "always"])

        exclude = set(getattr(self.args, "exclude", None) or [])
        target = list(getattr(self.args, "services", None) or [])

        if exclude:
            all_svcs = self._get_all_services()
            unknown = exclude - set(all_svcs)
            if unknown:
                self.log.warning(
                    "Excluded service(s) not found in compose file (typo?): %s",
                    ", ".join(sorted(unknown)),
                )
            if target:
                target = [s for s in target if s not in exclude]
            else:
                target = [s for s in all_svcs if s not in exclude]
            self.log.info(
                "Starting services (excluding %s): %s",
                ", ".join(sorted(exclude)),
                ", ".join(target),
            )

        if target:
            up_cmd.extend(target)

        try:
            self._run_command(up_cmd, check=True)
            self.log.info("Stack started successfully.")
            if not getattr(self.args, "attached", False):
                logs_hint = (
                    ["docker", "compose"] + self._compose_files() + ["logs", "-f", "--tail=50"]
                )
                if target:
                    logs_hint.extend(target)
                self.log.info("View logs: %s", " ".join(logs_hint))
        except subprocess.CalledProcessError:
            raise SystemExit(1)

    def _handle_down(self):
        target_services = getattr(self.args, "services", None) or []
        down_cmd = ["docker", "compose"] + self._compose_files() + ["down", "--remove-orphans"]
        if getattr(self.args, "clear_volumes", False):
            down_cmd.append("--volumes")
        if target_services:
            down_cmd.extend(target_services)
        self._run_command(down_cmd, check=False)

    def _handle_build(self):
        target_services = getattr(self.args, "services", None) or []
        build_cmd = ["docker", "compose"] + self._compose_files() + ["build"]
        if getattr(self.args, "no_cache", False):
            build_cmd.append("--no-cache")
        if getattr(self.args, "parallel", False):
            build_cmd.append("--parallel")
        if target_services:
            build_cmd.extend(target_services)
        try:
            self._run_command(build_cmd, check=True)
        except subprocess.CalledProcessError:
            raise SystemExit(1)

    def _handle_logs(self):
        target_services = getattr(self.args, "services", None) or []
        logs_cmd = ["docker", "compose"] + self._compose_files() + ["logs"]
        if getattr(self.args, "follow", False):
            logs_cmd.append("-f")
        if getattr(self.args, "tail", None):
            logs_cmd.extend(["--tail", str(self.args.tail)])
        if getattr(self.args, "timestamps", False):
            logs_cmd.append("-t")
        if getattr(self.args, "no_log_prefix", False):
            logs_cmd.append("--no-log-prefix")
        if target_services:
            logs_cmd.extend(target_services)
        try:
            self._run_command(logs_cmd, check=False)
        except KeyboardInterrupt:
            pass

    def _handle_nuke(self):
        self.log.warning("NUKE MODE — this will destroy all stack data system-wide.")
        try:
            confirm = input("Type 'confirm nuke' to proceed: ")
        except EOFError:
            raise SystemExit(1)
        if confirm.strip() != "confirm nuke":
            raise SystemExit(0)
        self._run_command(
            ["docker", "compose"]
            + self._compose_files()
            + ["down", "--volumes", "--remove-orphans"],
            check=False,
        )
        self._run_command(["docker", "system", "prune", "-a", "--volumes", "--force"], check=True)
        self.log.info("Nuke complete.")

    # ------------------------------------------------------------------
    # Exec helpers
    # ------------------------------------------------------------------

    def _ensure_api_running(self, action: str):
        if not self._is_container_running(API_CONTAINER_NAME):
            self.log.error(
                "Container '%s' is not running. Start the stack first:\n  pdavid --mode up",
                API_CONTAINER_NAME,
            )
            raise SystemExit(1)

    def exec_bootstrap_admin(self, db_url: Optional[str] = None):
        self._ensure_api_running("bootstrap-admin")
        resolved_db_url = db_url or os.environ.get("DATABASE_URL")
        if not resolved_db_url:
            self.log.error(
                "No database URL available. "
                "Ensure DATABASE_URL is set in .env or pass --db-url explicitly."
            )
            raise SystemExit(1)
        cmd = [
            "docker",
            "compose",
            "--project-directory",
            str(Path.cwd()),
            "--env-file",
            self._env_file_abs,
            "-f",
            self.base_compose,
            "exec",
            API_SERVICE_NAME,
            "python",
            "/app/src/api/entities_api/cli/bootstrap_admin.py",
            "--db-url",
            resolved_db_url,
        ]
        try:
            self._run_command(cmd, check=True, suppress_logs=True)
            self.log.info(
                "bootstrap-admin finished. "
                "Copy any printed ADMIN_API_KEY — it is required for API-level user provisioning."
            )
        except subprocess.CalledProcessError:
            raise SystemExit(1)

    # ------------------------------------------------------------------
    # Main dispatch
    # ------------------------------------------------------------------
    def run(self):
        gpu = getattr(self.args, "gpu", False)
        ollama = getattr(self.args, "ollama", False)
        vllm = getattr(self.args, "vllm", False)
        training = getattr(self.args, "training", False)
        mode = getattr(self.args, "mode", "up")

        suffix = ""
        if gpu:
            suffix = " + GPU (Ollama + vLLM)"
        elif ollama and vllm:
            suffix = " + Ollama + vLLM"
        elif ollama:
            suffix = " + Ollama"
        elif vllm:
            suffix = " + vLLM"
        if training:
            suffix += " + Sovereign Forge"

        self.log.info("Mode: %s%s", mode, suffix)

        if getattr(self.args, "nuke", False):
            if not self._preflight():
                raise SystemExit(1)
            self._handle_nuke()
            return

        if not self._preflight():
            raise SystemExit(1)

        if mode == "logs":
            self._handle_logs()
            return

        if mode == "down_only" or getattr(self.args, "down", False):
            self._handle_down()
            if mode == "down_only":
                return

        if mode == "build":
            self._handle_build()
            return

        if mode in ("up", "both"):
            if mode == "both":
                self._handle_build()
            self._handle_up()


# ---------------------------------------------------------------------------
# CLI entry-points
# ---------------------------------------------------------------------------


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    mode: str = typer.Option(
        "up",
        "--mode",
        help="Stack action: up | build | both | down_only | logs",
        show_default=True,
    ),
    # --- GPU service flags — independent opt-in ---
    training: bool = typer.Option(
        False,
        "--training",
        help="Start Sovereign Forge training stack. Requires NVIDIA GPU and nvidia-container-toolkit.",
    ),
    gpu: bool = typer.Option(
        False,
        "--gpu",
        help="Start both Ollama and vLLM (convenience shorthand for --ollama --vllm).",
    ),
    ollama: bool = typer.Option(
        False,
        "--ollama",
        help="Start Ollama only. Requires NVIDIA GPU and nvidia-container-toolkit.",
    ),
    vllm: bool = typer.Option(
        False,
        "--vllm",
        help="Start vLLM only. Requires NVIDIA GPU and nvidia-container-toolkit.",
    ),
    # --- Targeting ---
    services: Optional[List[str]] = typer.Option(
        None,
        "--services",
        help="Target specific service(s). Repeat for multiple: --services api --services db",
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        "-x",
        help="Exclude service(s) from 'up'. Repeat for multiple: --exclude samba",
    ),
    # --- Up ---
    down: bool = typer.Option(False, "--down", help="Run 'down' before starting."),
    clear_volumes: bool = typer.Option(
        False, "--clear-volumes", "-v", help="Remove volumes on down."
    ),
    force_recreate: bool = typer.Option(
        False, "--force-recreate", help="Force-recreate containers."
    ),
    pull: bool = typer.Option(
        False,
        "--pull",
        help="Pull the latest container images before starting. Use after upgrading the package.",
    ),
    attached: bool = typer.Option(False, "--attached", "-a", help="Run up in foreground."),
    build_before_up: bool = typer.Option(False, "--build-before-up", help="Build before up."),
    # --- Build ---
    no_cache: bool = typer.Option(False, "--no-cache", help="Build without cache."),
    parallel: bool = typer.Option(False, "--parallel", help="Build images in parallel."),
    # --- Nuke ---
    nuke: bool = typer.Option(
        False,
        "--nuke",
        help="DANGER: destroy all stack data. Requires confirmation.",
    ),
    # --- Logs ---
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output."),
    tail: Optional[int] = typer.Option(None, "--tail", help="Number of log lines to show."),
    timestamps: bool = typer.Option(
        False, "--timestamps", "-t", help="Show timestamps in log output."
    ),
    no_log_prefix: bool = typer.Option(
        False, "--no-log-prefix", help="Omit service name prefix in logs."
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging."),
) -> None:
    """
    Manage the Project David / Entities platform stack.

    BASE STACK:\n
      pdavid --mode up\n
      pdavid --mode up --pull\n
      pdavid --mode up --exclude samba\n
      pdavid --mode up --services api db qdrant\n
      pdavid --mode up --down --clear-volumes\n
      pdavid --mode logs --follow --timestamps\n
      pdavid --mode logs --services api --tail 100\n

    GPU INFERENCE (opt-in):\n
      pdavid --mode up --ollama\n
      pdavid --mode up --vllm\n
      pdavid --mode up --gpu\n

    SOVEREIGN FORGE — training + inference mesh (opt-in):\n
      pdavid --mode up --training\n
      pdavid --mode up --training --vllm\n
      pdavid --mode up --gpu --training\n

    CONFIGURATION:\n
      pdavid configure --set HF_TOKEN=hf_abc123\n
      pdavid configure --set TRAINING_PROFILE=standard\n
      pdavid configure --set RAY_ADDRESS=ray://192.168.1.10:10001\n
      pdavid configure --interactive\n
      pdavid bootstrap-admin\n
    """

    if ctx.invoked_subcommand is not None:
        return

    valid_modes = {"up", "build", "both", "down_only", "logs"}
    if mode not in valid_modes:
        typer.echo(
            f"[error] Invalid --mode '{mode}'. " f"Choose from: {', '.join(sorted(valid_modes))}",
            err=True,
        )
        raise SystemExit(1)

    if exclude and mode not in ("up", "both"):
        typer.echo(
            f"[error] --exclude is only valid with --mode=up or --mode=both (got '{mode}').",
            err=True,
        )
        raise SystemExit(1)

    if pull and mode not in ("up", "both"):
        typer.echo(
            f"[error] --pull is only valid with --mode=up or --mode=both (got '{mode}').",
            err=True,
        )
        raise SystemExit(1)

    if clear_volumes:
        down = True

    args = SimpleNamespace(
        training=training,
        mode=mode,
        gpu=gpu,
        ollama=ollama,
        vllm=vllm,
        services=services or [],
        exclude=exclude or [],
        down=down,
        clear_volumes=clear_volumes,
        force_recreate=force_recreate,
        pull=pull,
        attached=attached,
        build_before_up=build_before_up,
        no_cache=no_cache,
        parallel=parallel,
        nuke=nuke,
        follow=follow,
        tail=tail,
        timestamps=timestamps,
        no_log_prefix=no_log_prefix,
        verbose=verbose,
    )

    try:
        orchestrator = Orchestrator(args)
        orchestrator.run()
    except KeyboardInterrupt:
        typer.echo("\nCancelled.")
        raise SystemExit(130)
    except SystemExit:
        raise
    except Exception as exc:
        typer.echo(f"[error] {exc}", err=True)
        raise SystemExit(1)


@app.command()
def configure(
    set_var: Optional[List[str]] = typer.Option(
        None, "--set", "-s", help="Set KEY=VALUE in .env.", metavar="KEY=VALUE"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Interactively prompt for user-required variables."
    ),
) -> None:
    """
    Update variables in an existing .env without regenerating secrets.

    Examples:\n
      pdavid configure --set HF_TOKEN=hf_abc123\n
      pdavid configure --set VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct\n
      pdavid configure --interactive\n
    """
    env_path = Path(Orchestrator._ENV_FILE)
    if not env_path.exists():
        typer.echo(
            f"[error] '{Orchestrator._ENV_FILE}' not found. " "Run 'pdavid --mode up' first.",
            err=True,
        )
        raise SystemExit(1)

    load_dotenv(dotenv_path=env_path, override=True)
    updates: dict = {}

    if set_var:
        for item in set_var:
            if "=" not in item:
                typer.echo(f"[error] Invalid format '{item}'. Use KEY=VALUE.", err=True)
                raise SystemExit(1)
            key, _, value = item.partition("=")
            updates[key.strip()] = value.strip()

    if interactive:
        typer.echo("\n" + "=" * 60)
        typer.echo("  Interactive Configuration")
        typer.echo("=" * 60)
        typer.echo("  Press Enter to skip and leave current value unchanged.\n")
        for key, (label, help_text, hide) in Orchestrator._USER_REQUIRED.items():
            current = os.environ.get(key, "")
            status = "(currently set)" if current else "(currently blank — press Enter to skip)"
            typer.echo(f"  {help_text}\n")
            value = typer.prompt(
                f"  {label} {status}", default="", show_default=False, hide_input=hide
            )
            if value.strip():
                updates[key] = value.strip()
                typer.echo(f"  {key} will be updated.\n")
            else:
                typer.echo(f"  {key} unchanged.\n")
        typer.echo("=" * 60 + "\n")

    if not updates:
        typer.echo(
            "Nothing to update. Use --set KEY=VALUE or --interactive.\n"
            "Example: pdavid configure --set HF_TOKEN=hf_abc123"
        )
        raise SystemExit(0)

    content = env_path.read_text(encoding="utf-8")
    for key, value in updates.items():
        if any(c in value for c in [" ", "#", "="]):
            esc = value.replace("\\", "\\\\").replace('"', '\\"')
            new_line = f'{key}="{esc}"'
        else:
            new_line = f"{key}={value}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(content):
            content = pattern.sub(new_line, content)
        else:
            content += f"\n# Added by pdavid configure\n{new_line}\n"

    env_path.write_text(content, encoding="utf-8")
    typer.echo(f"Updated {len(updates)} variable(s): {', '.join(updates.keys())}")

    dangerous = [k for k in updates if k in Orchestrator._DANGEROUS_ROTATION]
    requires_down = [k for k in updates if k in Orchestrator._REQUIRES_DOWN]

    if dangerous:
        typer.echo(
            f"\nWARNING: {', '.join(dangerous)} cannot be safely rotated on a live stack.\n"
            "  Back up your data, then:\n"
            "    pdavid --down --clear-volumes\n"
            "    pdavid --mode up"
        )
    elif requires_down:
        typer.echo(
            f"\n  Note: {', '.join(requires_down)} require a full restart:\n"
            "    pdavid --down\n"
            "    pdavid --mode up"
        )
    else:
        typer.echo("\n  Restart to apply: pdavid --mode up --force-recreate")


@app.command(name="bootstrap-admin")
def bootstrap_admin(
    db_url: Optional[str] = typer.Option(
        None,
        "--db-url",
        help="Override DATABASE_URL for the bootstrap script. Defaults to DATABASE_URL from .env.",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging."),
) -> None:
    """
    Provision the default admin user inside the running api container.

    The stack must be running before calling this command.
    Copy any printed ADMIN_API_KEY — it is required for API-level user provisioning.

    Safe to re-run: existing users and keys are detected and left untouched.
    """
    args = SimpleNamespace(verbose=verbose, gpu=False, ollama=False, vllm=False, training=False)
    o = Orchestrator(args)

    # Generate (or retrieve) the admin key — only happens here, never at init.
    admin_key = o._provision_admin_api_key()

    o.exec_bootstrap_admin(db_url=db_url)

    # Print admin credentials once, clearly, after the bootstrap completes.
    typer.echo("\n" + "=" * 60)
    typer.echo("  Bootstrap complete.")
    typer.echo(f"  ADMIN_API_KEY : {admin_key}")
    typer.echo("  Store this key securely — it will not be shown again.")
    typer.echo("=" * 60 + "\n")


def entry_point():
    app()


if __name__ == "__main__":
    entry_point()
