import json
from types import SimpleNamespace


def parse_progress(output):
    prefix = "Q_PROGRESS "

    return [
        json.loads(line[len(prefix) :])
        for line in output.splitlines()
        if line.startswith(prefix)
    ]


def test_progress_events_are_opt_in(make_orchestrator, capsys):
    orchestrator = make_orchestrator()

    # Ignore unrelated constructor/setup output from the test fixture.
    capsys.readouterr()

    orchestrator._emit_progress("validating")

    assert (
        parse_progress(
            capsys.readouterr().out,
        )
        == []
    )


def test_up_emits_machine_readable_progress_in_order(
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
        "_compose_files",
        lambda: [],
    )
    monkeypatch.setattr(
        orchestrator,
        "_run_command",
        lambda *args, **kwargs: None,
    )

    orchestrator._handle_up()

    events = parse_progress(
        capsys.readouterr().out,
    )

    assert events == [
        {
            "type": "progress",
            "stage": "validating",
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
