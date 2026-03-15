# projectdavid_platform/start_orchestration.py
# start_orchestration.py
#
# Deployment orchestrator for the Project David / Entities platform.
# Distributed as part of the `projectdavid-platform` pip package.
#
# After `pip install projectdavid-platform`:
#   pdavid --mode up
#   pdavid --mode up --gpu
#   pdavid --mode up --exclude vllm --exclude ollama
#   pdavid --mode up --services api db qdrant
#   pdavid --mode logs --follow
#   pdavid configure --set HF_TOKEN=hf_abc123
#   pdavid bootstrap-admin
#
from __future__ import annotations

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
API_CONTAINER_NAME = "fastapi_cosmic_catalyst"
BASE_COMPOSE_FILE = "docker-compose.yml"
GPU_COMPOSE_FILE = "docker-compose.gpu.yml"
PACKAGE_NAME = "projectdavid_platform"

# Bundled config files that must exist in the user's CWD before Docker Compose
# can start. Each entry is (package-relative path, CWD-relative destination).
_BUNDLED_CONFIGS = [
    ("docker/nginx/nginx.conf", "docker/nginx/nginx.conf"),
    ("docker/otel/otel-config.yaml", "docker/otel/otel-config.yaml"),
    ("docker/searxng/settings.yml", "docker/searxng/settings.yml"),
]

# Platform-specific Docker install URLs
_DOCKER_INSTALL_URLS = {
    "windows": "https://docs.docker.com/desktop/install/windows-install/",
    "darwin": "https://docs.docker.com/desktop/install/mac-install/",
    "linux": "https://docs.docker.com/engine/install/",
}
_DOCKER_COMPOSE_INSTALL_URL = "https://docs.docker.com/compose/install/"
_NVIDIA_TOOLKIT_INSTALL_URL = (
    "https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
)


# ---------------------------------------------------------------------------
# Compose file path resolution
# ---------------------------------------------------------------------------


def _resolve_compose_file(filename: str) -> str:
    """
    Resolve the path to a compose file.

    Priority:
      1. Current working directory — local copy wins, enabling overrides.
      2. Installed package data — used after pip install with no local copy.
    """
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
app = typer.Typer(
    name="pdavid",
    help=(
        "Deployment orchestrator for the Project David / Entities platform.\n\n"
        "Install:  pip install projectdavid-platform\n"
        "Start:    pdavid --mode up\n"
        "GPU:      pdavid --mode up --gpu\n"
        "Skip svc: pdavid --mode up --exclude vllm --exclude ollama\n"
        "Config:   pdavid configure --set HF_TOKEN=hf_abc123"
    ),
    add_completion=False,
)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
class Orchestrator:
    """
    Manages the deployment stack: .env generation, Docker Compose lifecycle,
    and exec-based provisioning commands against the running api container.
    """

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
        "ASSISTANTS_BASE_URL": "http://localhost:9000",
        "SANDBOX_SERVER_URL": "http://sandbox:8000",
        "DOWNLOAD_BASE_URL": "http://localhost:9000/v1/files/download",
        "HF_TOKEN": "",
        "HF_CACHE_PATH": "",
        "VLLM_MODEL": "Qwen/Qwen2.5-VL-3B-Instruct",
        "BASE_URL_HEALTH": "http://localhost:9000/v1/health",
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
        "Tool Identifiers": [
            "TOOL_CODE_INTERPRETER",
            "TOOL_WEB_SEARCH",
            "TOOL_COMPUTER",
            "TOOL_VECTOR_STORE_SEARCH",
        ],
        "Other": [
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

        # _ensure_config_files MUST run before _resolve_compose_file and
        # _load_compose_config. Docker Compose will race to create volume
        # mount targets as empty directories if the files don't exist yet —
        # running this first guarantees the actual files are in place before
        # any Docker operation can win that race.
        self._ensure_config_files()

        self.base_compose = _resolve_compose_file(BASE_COMPOSE_FILE)
        self.gpu_compose = _resolve_compose_file(GPU_COMPOSE_FILE)
        self.compose_config = self._load_compose_config()
        self._check_for_required_env_file()
        self._configure_shared_path()
        self._configure_hf_cache_path()
        self._ensure_dockerignore()

    # ------------------------------------------------------------------
    # .env path helpers
    # ------------------------------------------------------------------

    @property
    def _env_file_abs(self) -> str:
        """
        Absolute path to the .env file in the current working directory.
        Always resolves from CWD so Docker Compose receives a fully-qualified
        path regardless of where the bundled compose file lives.
        """
        return str(Path(self._ENV_FILE).resolve())

    # ------------------------------------------------------------------
    # Config file bootstrap
    # ------------------------------------------------------------------

    def _ensure_config_files(self) -> None:
        """
        Copy bundled service config files (nginx, otel, searxng) into the
        user's CWD before Docker Compose starts.

        Rules:
        - Runs first in __init__ to win the race against Docker Compose, which
          will autocreate volume mount targets as empty directories if the
          files don't exist at startup time.
        - If Docker already won a previous race and created a directory where
          a file should be, the directory is removed and replaced with the
          correct file. A warning is printed so the user is aware.
        - Never overwrites an existing *file* — local customisations are
          always respected.
        - Skips silently if the package data cannot be located (e.g. a
          partial or editable install without the data files present).
        - Creates the full directory tree as needed.
        """
        copied = []
        skipped = []

        for pkg_rel, cwd_rel in _BUNDLED_CONFIGS:
            dest = Path.cwd() / cwd_rel

            # Docker Compose race condition: if a previous run started before
            # this file existed, Docker will have created an empty directory
            # at the mount target path. Detect and replace it with the real file.
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
                skipped.append(cwd_rel)
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
                    "The service that depends on it may fail to start. "
                    "You can create it manually or reinstall: "
                    "pip install --force-reinstall projectdavid-platform",
                    cwd_rel,
                    e,
                )

        if copied:
            typer.echo(
                f"\n  Installed {len(copied)} config file(s) to CWD:\n"
                + "\n".join(f"    {f}" for f in copied)
                + "\n  Edit them freely — pdavid will never overwrite local copies.\n"
            )

    # ------------------------------------------------------------------
    # Preflight dependency checks
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

    def _validate_gpu_prereqs(self) -> bool:
        if self._has_nvidia_support():
            self.log.info("NVIDIA GPU support confirmed.")
            return True
        typer.echo(
            "\nGPU stack requested (--gpu) but NVIDIA drivers / nvidia-smi not found.\n"
            "Requirements for GPU stack:\n"
            "  1. NVIDIA GPU with drivers installed\n"
            f"  2. NVIDIA Container Toolkit: {_NVIDIA_TOOLKIT_INSTALL_URL}\n"
            "\nTo start without GPU services, omit --gpu:\n"
            "  pdavid --mode up\n"
            "Or exclude only the GPU services:\n"
            "  pdavid --mode up --exclude vllm --exclude ollama\n",
            err=True,
        )
        return False

    def _preflight(self) -> bool:
        self.log.debug("Running preflight dependency checks...")
        if not self._has_docker():
            return False
        if not self._has_docker_compose():
            return False
        if getattr(self.args, "gpu", False) and not self._validate_gpu_prereqs():
            return False
        self.log.debug("Preflight checks passed.")
        return True

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _compose_files(self) -> List[str]:
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
            if key == "ADMIN_API_KEY":
                env_values[key] = f"ad_{secrets.token_urlsafe(32)}"
            elif key == "API_KEY":
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
            "\n  Use ADMIN_API_KEY to bootstrap the admin user:\n"
            "    pdavid bootstrap-admin\n"
            "\n  Once bootstrapped, manage users via the API.\n"
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
    # Action handlers
    # ------------------------------------------------------------------

    def _handle_up(self):
        load_dotenv(dotenv_path=self._ENV_FILE, override=True)
        self._validate_secrets()

        up_cmd = ["docker", "compose"] + self._compose_files() + ["up"]
        if not getattr(self.args, "attached", False):
            up_cmd.append("-d")
        if getattr(self.args, "build_before_up", False):
            up_cmd.append("--build")
        if getattr(self.args, "force_recreate", False):
            up_cmd.append("--force-recreate")

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

        # DATABASE_URL points to db:3306 (internal) — correct inside the container.
        # SPECIAL_DB_URL points to localhost:3307 (host-side only) — wrong inside container.
        # Fall back to DATABASE_URL from the loaded .env if no override is provided.
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
        mode = getattr(self.args, "mode", "up")
        self.log.info("Mode: %s%s", mode, " + GPU" if getattr(self.args, "gpu", False) else "")

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
    gpu: bool = typer.Option(
        False,
        "--gpu",
        help="Include GPU services (vLLM + Ollama) via docker-compose.gpu.yml.",
    ),
    services: Optional[List[str]] = typer.Option(
        None,
        "--services",
        help="Target specific service(s). Repeat for multiple: --services api --services db",
    ),
    exclude: Optional[List[str]] = typer.Option(
        None,
        "--exclude",
        "-x",
        help="Exclude service(s) from 'up'. Repeat for multiple: --exclude vllm --exclude ollama",
    ),
    down: bool = typer.Option(False, "--down", help="Run 'down' before starting."),
    clear_volumes: bool = typer.Option(
        False, "--clear-volumes", "-v", help="Remove volumes on down."
    ),
    force_recreate: bool = typer.Option(
        False, "--force-recreate", help="Force-recreate containers."
    ),
    attached: bool = typer.Option(False, "--attached", "-a", help="Run up in foreground."),
    build_before_up: bool = typer.Option(False, "--build-before-up", help="Build before up."),
    no_cache: bool = typer.Option(False, "--no-cache", help="Build without cache."),
    parallel: bool = typer.Option(False, "--parallel", help="Build images in parallel."),
    nuke: bool = typer.Option(
        False,
        "--nuke",
        help="DANGER: destroy all stack data. Requires confirmation.",
    ),
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

    Examples:\n
      pdavid --mode up\n
      pdavid --mode up --gpu\n
      pdavid --mode up --exclude vllm --exclude ollama\n
      pdavid --mode up --services api db qdrant\n
      pdavid --mode up --down --clear-volumes\n
      pdavid --mode logs --follow --timestamps\n
      pdavid --mode logs --services api --tail 100\n
      pdavid configure --set HF_TOKEN=hf_abc123\n
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

    if clear_volumes:
        down = True

    args = SimpleNamespace(
        mode=mode,
        gpu=gpu,
        services=services or [],
        exclude=exclude or [],
        down=down,
        clear_volumes=clear_volumes,
        force_recreate=force_recreate,
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
    args = SimpleNamespace(verbose=verbose, gpu=False)
    o = Orchestrator(args)
    o.exec_bootstrap_admin(db_url=db_url)


def entry_point():
    app()


if __name__ == "__main__":
    app()
