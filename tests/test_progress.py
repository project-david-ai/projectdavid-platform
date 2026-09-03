import json
from types import SimpleNamespace

import pytest


def parse_progress(output):
    prefix = "Q_PROGRESS "

    return [
        json.loads(line[len(prefix) :])
        for line in output.splitlines()
        if line.startswith(prefix)
    ]


def make_result(
    *,
    returncode=0,
    stdout="",
    stderr="",
):
    return SimpleNamespace(
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_progress_events_are_opt_in(
    make_orchestrator,
    capsys,
):
    orchestrator = make_orchestrator()

    capsys.readouterr()

    orchestrator._emit_progress(
        "validating",
    )

    assert (
        parse_progress(
            capsys.readouterr().out,
        )
        == []
    )


def test_up_emits_progress_when_images_are_present(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    monkeypatch.setattr(
        orchestrator,
        "_preflight",
        lambda: True,
    )
    monkeypatch.setattr(
        orchestrator,
        "_validate_secrets",
        lambda: None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_check_version_upgrade",
        lambda: None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_required_images",
        lambda: ["example/image:1"],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_missing_images",
        lambda images: [],
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_command",
        lambda *args, **kwargs: make_result(),
    )

    capsys.readouterr()

    orchestrator.run()

    assert parse_progress(
        capsys.readouterr().out,
    ) == [
        {
            "type": "progress",
            "stage": "validating",
        },
        {
            "type": "progress",
            "stage": "images_checking",
        },
        {
            "type": "progress",
            "stage": "containers_starting",
        },
        {
            "type": "progress",
            "stage": "service_booting",
        },
    ]


def test_missing_images_are_pulled_before_containers_start(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)
    commands = []

    monkeypatch.setattr(
        orchestrator,
        "_preflight",
        lambda: True,
    )
    monkeypatch.setattr(
        orchestrator,
        "_validate_secrets",
        lambda: None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_check_version_upgrade",
        lambda: None,
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_required_images",
        lambda: [
            "present/image:1",
            "missing/image:2",
        ],
    )
    monkeypatch.setattr(
        orchestrator,
        "_get_missing_images",
        lambda images: [
            "missing/image:2",
        ],
    )

    def run_command(command, **kwargs):
        commands.append(command)
        return make_result()

    monkeypatch.setattr(
        orchestrator,
        "_run_command",
        run_command,
    )

    capsys.readouterr()

    orchestrator.run()

    assert parse_progress(
        capsys.readouterr().out,
    ) == [
        {
            "type": "progress",
            "stage": "validating",
        },
        {
            "type": "progress",
            "stage": "images_checking",
        },
        {
            "type": "progress",
            "stage": "image_missing",
            "total": 1,
        },
        {
            "type": "progress",
            "stage": "image_downloading",
            "current": 0,
            "total": 1,
            "item": "missing/image:2",
        },
        {
            "type": "progress",
            "stage": "image_downloading",
            "current": 1,
            "total": 1,
            "item": "missing/image:2",
        },
        {
            "type": "progress",
            "stage": "containers_starting",
        },
        {
            "type": "progress",
            "stage": "service_booting",
        },
    ]

    pull_index = commands.index(
        [
            "docker",
            "pull",
            "missing/image:2",
        ]
    )

    compose_up_index = next(
        index
        for index, command in enumerate(commands)
        if (command[:2] == ["docker", "compose"] and "up" in command)
    )

    assert pull_index < compose_up_index


def test_startup_preflight_failure_still_emits_validating(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    monkeypatch.setattr(
        orchestrator,
        "_preflight",
        lambda: False,
    )

    capsys.readouterr()

    with pytest.raises(SystemExit):
        orchestrator.run()

    assert parse_progress(
        capsys.readouterr().out,
    ) == [
        {
            "type": "progress",
            "stage": "validating",
        },
    ]


def parse_errors(output):
    prefix = "Q_ERROR "

    return [
        json.loads(line[len(prefix) :])
        for line in output.splitlines()
        if line.startswith(prefix)
    ]


def test_error_events_are_opt_in(
    make_orchestrator,
    capsys,
):
    orchestrator = make_orchestrator()

    capsys.readouterr()

    orchestrator._emit_error(
        "TEST_ERROR",
        "Something failed.",
    )

    captured = capsys.readouterr()

    assert (
        parse_errors(
            captured.out + captured.err,
        )
        == []
    )


def test_docker_unavailable_emits_structured_error(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    import projectdavid_platform.start_orchestration as orchestration

    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    monkeypatch.setattr(
        orchestration.shutil,
        "which",
        lambda command: None,
    )

    capsys.readouterr()

    assert orchestrator._has_docker() is False

    captured = capsys.readouterr()

    assert parse_errors(
        captured.out + captured.err,
    ) == [
        {
            "type": "error",
            "code": "DOCKER_UNAVAILABLE",
            "message": "Docker is not available.",
        }
    ]


def test_compose_unavailable_emits_structured_error(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    import subprocess

    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    def fail_command(*args, **kwargs):
        raise subprocess.CalledProcessError(
            1,
            ["docker", "compose", "version"],
        )

    monkeypatch.setattr(
        orchestrator,
        "_run_command",
        fail_command,
    )

    capsys.readouterr()

    assert orchestrator._has_docker_compose() is False

    captured = capsys.readouterr()

    assert parse_errors(
        captured.out + captured.err,
    ) == [
        {
            "type": "error",
            "code": "DOCKER_COMPOSE_UNAVAILABLE",
            "message": "Docker Compose is not available.",
        }
    ]


def test_gpu_unavailable_emits_structured_error(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    monkeypatch.setattr(
        orchestrator,
        "_has_nvidia_support",
        lambda: False,
    )

    capsys.readouterr()

    assert orchestrator._validate_gpu_prereqs("--vllm") is False

    captured = capsys.readouterr()

    assert parse_errors(
        captured.out + captured.err,
    ) == [
        {
            "type": "error",
            "code": "GPU_UNAVAILABLE",
            "message": "A compatible NVIDIA GPU is required.",
        }
    ]


def test_blocking_port_conflict_emits_structured_error(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    import projectdavid_platform.start_orchestration as orchestration

    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    monkeypatch.setattr(
        orchestrator,
        "_compose_owns_host_port",
        lambda port: False,
    )

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def settimeout(self, timeout):
            return None

        def connect_ex(self, address):
            return 0

    monkeypatch.setattr(
        orchestration._socket,
        "socket",
        lambda *args, **kwargs: FakeSocket(),
    )

    capsys.readouterr()

    assert (
        orchestrator._check_port_conflicts(
            {
                8265: (
                    "Ray dashboard",
                    "error",
                ),
            }
        )
        is False
    )

    captured = capsys.readouterr()

    assert parse_errors(
        captured.out + captured.err,
    ) == [
        {
            "type": "error",
            "code": "PORT_CONFLICT",
            "message": "Required local ports are already in use.",
        }
    ]


def test_compose_port_ownership_matches_current_runtime_containers(
    base_args,
    make_orchestrator,
    monkeypatch,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    commands = []

    def run_command(command, **kwargs):
        commands.append(command)

        if command[:2] == ["docker", "compose"] and command[-2:] == ["ps", "-q"]:
            return make_result(
                stdout=("abcdef1234567890abcdef1234567890\n"),
            )

        if command[:2] == ["docker", "ps"] and "publish=8265" in command:
            return make_result(
                stdout="abcdef123456\n",
            )

        if command[:2] == ["docker", "ps"] and "publish=10001" in command:
            return make_result(
                stdout="999999999999\n",
            )

        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(
        orchestrator,
        "_run_command",
        run_command,
    )

    assert orchestrator._compose_owns_host_port(8265) is True

    assert orchestrator._compose_owns_host_port(10001) is False


def test_port_owned_by_current_project_david_runtime_is_not_a_conflict(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    import projectdavid_platform.start_orchestration as orchestration

    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def settimeout(self, timeout):
            return None

        def connect_ex(self, address):
            return 0

    monkeypatch.setattr(
        orchestration._socket,
        "socket",
        lambda *args, **kwargs: FakeSocket(),
    )

    monkeypatch.setattr(
        orchestrator,
        "_compose_owns_host_port",
        lambda port: True,
    )

    capsys.readouterr()

    assert (
        orchestrator._check_port_conflicts(
            {
                8265: (
                    "Ray dashboard",
                    "error",
                ),
                10001: (
                    "Ray client server",
                    "error",
                ),
            }
        )
        is True
    )

    captured = capsys.readouterr()

    assert (
        parse_errors(
            captured.out + captured.err,
        )
        == []
    )


def test_image_inspection_emits_real_item_count_progress(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    results = iter(
        [
            make_result(returncode=0),
            make_result(returncode=1),
            make_result(returncode=0),
        ]
    )

    monkeypatch.setattr(
        orchestrator,
        "_run_command",
        lambda *args, **kwargs: next(results),
    )

    capsys.readouterr()

    missing = orchestrator._get_missing_images(
        [
            "one/image:1",
            "two/image:2",
            "three/image:3",
        ]
    )

    assert missing == [
        "two/image:2",
    ]

    assert parse_progress(
        capsys.readouterr().out,
    ) == [
        {
            "type": "progress",
            "stage": "images_checking",
            "current": 0,
            "total": 3,
        },
        {
            "type": "progress",
            "stage": "images_checking",
            "current": 1,
            "total": 3,
            "item": "one/image:1",
        },
        {
            "type": "progress",
            "stage": "images_checking",
            "current": 2,
            "total": 3,
            "item": "two/image:2",
        },
        {
            "type": "progress",
            "stage": "images_checking",
            "current": 3,
            "total": 3,
            "item": "three/image:3",
        },
    ]


def test_progress_payload_accepts_backward_compatible_details(
    base_args,
    make_orchestrator,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    capsys.readouterr()

    orchestrator._emit_progress(
        "image_downloading",
        current=2,
        total=5,
        item="example/image:1",
    )

    assert parse_progress(
        capsys.readouterr().out,
    ) == [
        {
            "type": "progress",
            "stage": "image_downloading",
            "current": 2,
            "total": 5,
            "item": "example/image:1",
        }
    ]


def test_container_progress_reports_real_running_service_count(
    base_args,
    make_orchestrator,
    monkeypatch,
    capsys,
):
    args = SimpleNamespace(
        **vars(base_args),
        progress_json=True,
    )

    orchestrator = make_orchestrator(args)

    monkeypatch.setattr(
        orchestrator,
        "_get_running_services",
        lambda: [
            "mysql",
            "redis",
        ],
    )

    capsys.readouterr()

    running = orchestrator._emit_service_start_progress(
        [
            "mysql",
            "redis",
            "api",
        ],
    )

    assert running == {
        "mysql",
        "redis",
    }

    assert parse_progress(
        capsys.readouterr().out,
    ) == [
        {
            "type": "progress",
            "stage": "containers_starting",
            "current": 2,
            "total": 3,
            "item": "redis",
        }
    ]
