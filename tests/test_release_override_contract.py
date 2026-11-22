from pathlib import Path
from types import SimpleNamespace

import pytest

import projectdavid_platform.start_orchestration as orchestration
from projectdavid_platform.start_orchestration import Orchestrator


def _orchestrator():
    return Orchestrator.__new__(Orchestrator)


def test_release_override_is_last_compose_file_before_profiles(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)

    base = tmp_path / "docker-compose.yml"

    ollama = tmp_path / "docker-compose.ollama.yml"

    override = tmp_path / "q-release.override.yml"

    o = _orchestrator()

    o.args = SimpleNamespace(
        ollama=True,
        vllm=True,
        training=False,
        release_override=override,
    )

    o.base_compose = str(base)

    o.ollama_compose = str(ollama)

    result = o._compose_files()

    assert result == [
        "--project-directory",
        str(tmp_path),
        "--env-file",
        str(tmp_path / ".env"),
        "-f",
        str(base),
        "-f",
        str(ollama),
        "-f",
        str(override),
        "--profile",
        "vllm",
    ]


def test_prepared_release_bypasses_platform_image_preparation():
    o = _orchestrator()

    o.args = SimpleNamespace(
        release_override=Path(r"C:\Q\q-release.override.yml"),
    )

    o.progress_json = True

    def unexpected():
        pytest.fail("Platform attempted image discovery in prepared mode")

    o._get_required_images = unexpected

    o._prepare_required_images()


def test_prepared_release_up_skips_version_discovery_and_never_pulls(
    tmp_path,
    monkeypatch,
):
    override = tmp_path / "q-release.override.yml"

    override.write_text(
        "services:\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        orchestration,
        "load_dotenv",
        lambda **kwargs: None,
    )

    o = _orchestrator()

    o._ENV_FILE = ".env"

    o.args = SimpleNamespace(
        release_override=override,
        pull=False,
        attached=False,
        build_before_up=False,
        force_recreate=False,
        exclude=[],
        services=[],
    )

    validation_calls = []
    version_calls = []
    commands = []
    progress = []

    o._validate_secrets = lambda: validation_calls.append("validated")

    o._check_version_upgrade = lambda: version_calls.append("version-checked")

    o._compose_files = lambda: [
        "-f",
        "docker-compose.yml",
        "-f",
        str(override),
    ]

    o._emit_progress = lambda stage: progress.append(stage)

    o._run_command = lambda command, **kwargs: commands.append(
        (
            command,
            kwargs,
        )
    )

    o.log = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    o._handle_up()

    assert validation_calls == [
        "validated",
    ]

    assert version_calls == []

    assert len(commands) == 1

    command = commands[0][0]

    assert command == [
        "docker",
        "compose",
        "-f",
        "docker-compose.yml",
        "-f",
        str(override),
        "up",
        "-d",
    ]

    assert "--pull" not in command
    assert "always" not in command

    assert progress == [
        "containers_starting",
        "service_booting",
    ]


def test_prepared_release_rejects_pull_even_when_called_programmatically(
    tmp_path,
    monkeypatch,
):
    override = tmp_path / "q-release.override.yml"

    override.write_text(
        "services:\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        orchestration,
        "load_dotenv",
        lambda **kwargs: None,
    )

    o = _orchestrator()

    o._ENV_FILE = ".env"

    o.args = SimpleNamespace(
        release_override=override,
        pull=True,
        attached=False,
        build_before_up=False,
        force_recreate=False,
        exclude=[],
        services=[],
    )

    version_calls = []
    command_calls = []
    emitted_errors = []

    o._validate_secrets = lambda: None

    o._check_version_upgrade = lambda: version_calls.append("version-checked")

    o._emit_error = lambda code, message: emitted_errors.append(
        (
            code,
            message,
        )
    )

    o._run_command = lambda *args, **kwargs: command_calls.append(
        (
            args,
            kwargs,
        )
    )

    o.log = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    with pytest.raises(
        SystemExit,
    ) as exc:
        o._handle_up()

    assert exc.value.code == 1

    assert version_calls == []
    assert command_calls == []

    assert emitted_errors
    assert emitted_errors[0][0] == "RELEASE_OVERRIDE_PULL_CONFLICT"


def test_standalone_pull_behavior_is_preserved(
    monkeypatch,
):
    monkeypatch.setattr(
        orchestration,
        "load_dotenv",
        lambda **kwargs: None,
    )

    o = _orchestrator()

    o._ENV_FILE = ".env"

    o.args = SimpleNamespace(
        release_override=None,
        pull=True,
        attached=False,
        build_before_up=False,
        force_recreate=False,
        exclude=[],
        services=[],
    )

    version_calls = []
    commands = []

    o._validate_secrets = lambda: None

    o._check_version_upgrade = lambda: version_calls.append("version-checked")

    o._compose_files = lambda: [
        "-f",
        "docker-compose.yml",
    ]

    o._emit_progress = lambda stage: None

    o._run_command = lambda command, **kwargs: commands.append(command)

    o.log = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
    )

    o._handle_up()

    assert version_calls == [
        "version-checked",
    ]

    assert commands == [
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "up",
            "-d",
            "--pull",
            "always",
        ],
    ]
