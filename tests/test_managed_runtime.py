from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest
import typer

import projectdavid_platform.start_orchestration as orchestration
from projectdavid_platform.start_orchestration import Orchestrator


def _make_orchestrator(*, managed_runtime: bool) -> Orchestrator:
    orchestrator = Orchestrator.__new__(Orchestrator)
    orchestrator.managed_runtime = managed_runtime
    orchestrator.log = logging.getLogger("test_managed_runtime")
    return orchestrator


def _configure_single_bundled_compose(
    tmp_path,
    monkeypatch,
):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()

    package_dir = tmp_path / "package"
    package_dir.mkdir()

    bundled_compose = package_dir / "docker-compose.yml"
    bundled_compose.write_text(
        "services:\n"
        "  inference-worker:\n"
        "    environment:\n"
        "      - VLLM_USE_V2_MODEL_RUNNER=0\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(runtime_dir)

    monkeypatch.setattr(
        orchestration,
        "_BUNDLED_CONFIGS",
        [
            (
                "docker-compose.yml",
                "docker-compose.yml",
            ),
        ],
    )

    monkeypatch.setattr(
        orchestration.importlib.resources,
        "files",
        lambda package_name: package_dir,
    )

    return runtime_dir


def test_existing_config_is_preserved_for_standalone_runtime(
    tmp_path,
    monkeypatch,
):
    runtime_dir = _configure_single_bundled_compose(
        tmp_path,
        monkeypatch,
    )

    existing = runtime_dir / "docker-compose.yml"
    existing.write_text(
        "# user-owned compose\n",
        encoding="utf-8",
    )

    orchestrator = _make_orchestrator(
        managed_runtime=False,
    )

    orchestrator._ensure_config_files()

    assert existing.read_text(encoding="utf-8") == "# user-owned compose\n"


def test_existing_config_is_refreshed_for_managed_runtime(
    tmp_path,
    monkeypatch,
):
    runtime_dir = _configure_single_bundled_compose(
        tmp_path,
        monkeypatch,
    )

    existing = runtime_dir / "docker-compose.yml"
    existing.write_text(
        "# stale managed compose\n",
        encoding="utf-8",
    )

    orchestrator = _make_orchestrator(
        managed_runtime=True,
    )

    orchestrator._ensure_config_files()

    content = existing.read_text(
        encoding="utf-8",
    )

    assert "stale managed compose" not in content
    assert "VLLM_USE_V2_MODEL_RUNNER=0" in content


def test_missing_runtime_is_rejected_for_standalone_mode(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    runtime_dir = tmp_path / "missing-standalone-runtime"

    with pytest.raises(
        typer.BadParameter,
        match="runtime directory does not exist",
    ):
        orchestration._activate_runtime_directory(
            runtime_dir,
            managed_runtime=False,
        )

    assert not runtime_dir.exists()


def test_missing_runtime_is_created_for_managed_mode(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    runtime_dir = tmp_path / "fresh-managed-runtime"

    resolved = orchestration._activate_runtime_directory(
        runtime_dir,
        managed_runtime=True,
    )

    assert resolved == runtime_dir.resolve()
    assert runtime_dir.is_dir()
    assert Path.cwd() == runtime_dir.resolve()


def test_managed_env_generation_does_not_inherit_shell_hf_token(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "HF_TOKEN",
        "developer-shell-token",
    )

    orchestrator = orchestration.Orchestrator.__new__(orchestration.Orchestrator)
    orchestrator.managed_runtime = True
    orchestrator.log = logging.getLogger("test-managed-env")
    orchestrator._get_host_port_from_compose_service = lambda *_args, **_kwargs: None
    orchestrator._print_summary = lambda *_args, **_kwargs: None

    orchestrator._generate_dot_env_file()

    content = Path(".env").read_text(
        encoding="utf-8",
    )

    assert "developer-shell-token" not in content
    assert "HF_TOKEN=" in content


def test_fresh_generated_env_is_loaded_immediately(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(
        "Q_FRESH_ENV_TEST",
        raising=False,
    )

    orchestrator = orchestration.Orchestrator.__new__(orchestration.Orchestrator)
    orchestrator.log = logging.getLogger("test-fresh-env-load")

    def generate_env():
        Path(".env").write_text(
            "Q_FRESH_ENV_TEST=loaded\n",
            encoding="utf-8",
        )

    orchestrator._generate_dot_env_file = generate_env

    orchestrator._check_for_required_env_file()

    assert os.environ["Q_FRESH_ENV_TEST"] == "loaded"


def test_missing_env_for_established_runtime_requires_recovery(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    (tmp_path / ".projectdavid-instance-id").write_text(
        "11111111-1111-4111-8111-111111111111",
        encoding="utf-8",
    )

    orchestrator = Orchestrator.__new__(Orchestrator)

    orchestrator.managed_runtime = True
    orchestrator.log = logging.getLogger("test-managed-env-recovery")

    generated = []
    emitted = []

    orchestrator._generate_dot_env_file = lambda: generated.append(True)

    orchestrator._emit_error = lambda code, message: emitted.append((code, message))

    with pytest.raises(
        SystemExit,
    ) as exc:
        orchestrator._check_for_required_env_file()

    assert exc.value.code == 1

    assert generated == []

    assert emitted
    assert emitted[0][0] == "ENV_RECOVERY_REQUIRED"

    assert "Refusing to generate replacement secrets" in emitted[0][1]

    assert not (tmp_path / ".env").exists()


def test_missing_env_without_runtime_identity_remains_fresh_install(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    orchestrator = Orchestrator.__new__(Orchestrator)

    orchestrator.managed_runtime = True
    orchestrator.log = logging.getLogger("test-managed-env-first-install")

    generated = []

    def generate_env():
        generated.append(True)

        Path(".env").write_text(
            "Q_H7_FRESH_INSTALL=1\n",
            encoding="utf-8",
        )

    orchestrator._generate_dot_env_file = generate_env

    orchestrator._check_for_required_env_file()

    assert generated == [True]

    assert (tmp_path / ".env").is_file()
