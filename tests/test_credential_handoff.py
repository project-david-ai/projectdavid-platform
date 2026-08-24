import json
import os
import stat
from uuid import UUID

import pytest
from typer.testing import CliRunner

from projectdavid_platform import start_orchestration
from projectdavid_platform.credential_handoff import (
    CredentialHandoffError,
    get_or_create_runtime_instance_id,
    handoff_admin_credential,
    write_admin_credential_file,
)

runner = CliRunner()


def test_runtime_instance_id_is_created_and_stable(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    first = get_or_create_runtime_instance_id(runtime)
    second = get_or_create_runtime_instance_id(runtime)

    assert first == second
    assert UUID(first).version == 4

    identity_file = runtime / ".projectdavid-instance-id"

    assert identity_file.exists()
    assert identity_file.read_text(encoding="utf-8") == first


def test_runtime_instance_ids_are_unique_per_runtime(tmp_path):
    runtime_a = tmp_path / "runtime-a"
    runtime_b = tmp_path / "runtime-b"

    runtime_a.mkdir()
    runtime_b.mkdir()

    instance_a = get_or_create_runtime_instance_id(runtime_a)
    instance_b = get_or_create_runtime_instance_id(runtime_b)

    assert instance_a != instance_b


def test_runtime_instance_id_rejects_invalid_existing_state(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()

    identity_file = runtime / ".projectdavid-instance-id"
    identity_file.write_text(
        "not-a-valid-instance-id",
        encoding="utf-8",
    )

    with pytest.raises(
        CredentialHandoffError,
        match="runtime instance ID is invalid",
    ):
        get_or_create_runtime_instance_id(runtime)


def test_write_admin_credential_file(tmp_path):
    target = tmp_path / "runtime" / "secrets" / "project-david-admin.key"

    api_key = "ad_test_secret_value"

    result = write_admin_credential_file(
        target,
        api_key,
    )

    assert result == target.resolve()
    assert target.exists()

    assert target.read_text(encoding="utf-8") == api_key


def test_write_replaces_existing_credential(tmp_path):
    target = tmp_path / "project-david-admin.key"

    target.write_text(
        "ad_old_secret",
        encoding="utf-8",
    )

    write_admin_credential_file(
        target,
        "ad_new_secret",
    )

    assert target.read_text(encoding="utf-8") == "ad_new_secret"


def test_handoff_removes_plaintext_secret(
    tmp_path,
    monkeypatch,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.chdir(runtime)

    target = tmp_path / "project-david-admin.key"

    bootstrap_result = {
        "status": "ok",
        "user_id": "user_admin",
        "key_prefix": "ad_test",
        "key_created": False,
        "api_key": "ad_test_secret_value",
        "protocol": "json-v1",
    }

    result = handoff_admin_credential(
        bootstrap_result,
        target,
    )

    assert "api_key" not in result
    assert "admin_api_key" not in result

    assert result["status"] == "ok"
    assert result["user_id"] == "user_admin"
    assert result["key_prefix"] == "ad_test"
    assert result["protocol"] == "json-v1"

    assert result["credential_state"] == "ready"
    assert result["credential_file"] == str(target.resolve())

    assert UUID(result["instance_id"]).version == 4
    assert (runtime / ".projectdavid-instance-id").read_text(
        encoding="utf-8"
    ) == result["instance_id"]

    assert target.read_text(encoding="utf-8") == "ad_test_secret_value"

    # Sanitising the result must not mutate the original
    # bootstrap object used internally by Platform.
    assert bootstrap_result["api_key"] == "ad_test_secret_value"


def test_handoff_reuses_runtime_instance_id(
    tmp_path,
    monkeypatch,
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.chdir(runtime)

    first = handoff_admin_credential(
        {
            "status": "ok",
            "api_key": "ad_first_secret",
        },
        tmp_path / "first.key",
    )

    second = handoff_admin_credential(
        {
            "status": "ok",
            "api_key": "ad_second_secret",
        },
        tmp_path / "second.key",
    )

    assert first["instance_id"] == second["instance_id"]


def test_handoff_rejects_missing_admin_credential(
    tmp_path,
):
    with pytest.raises(
        CredentialHandoffError,
        match="valid admin credential",
    ):
        handoff_admin_credential(
            {
                "status": "ok",
                "protocol": "json-v1",
            },
            tmp_path / "admin.key",
        )


def test_handoff_rejects_wrong_key_type(tmp_path):
    with pytest.raises(
        CredentialHandoffError,
        match="valid admin credential",
    ):
        write_admin_credential_file(
            tmp_path / "admin.key",
            "sk_not_an_admin_key",
        )


@pytest.mark.skipif(
    os.name == "nt",
    reason=("Windows chmod semantics do not expose " "POSIX owner mode bits."),
)
def test_credential_file_is_owner_only_on_posix(
    tmp_path,
):
    target = tmp_path / "project-david-admin.key"

    write_admin_credential_file(
        target,
        "ad_test_secret_value",
    )

    mode = stat.S_IMODE(target.stat().st_mode)

    assert mode == 0o600


def test_bootstrap_cli_credential_file_never_emits_secret(
    tmp_path,
    monkeypatch,
):
    secret = "ad_cli_secret_that_must_not_escape"

    runtime = tmp_path / "runtime"
    runtime.mkdir()
    monkeypatch.chdir(runtime)

    class FakeOrchestrator:
        def __init__(self, args):
            self.args = args

        def exec_bootstrap_admin(
            self,
            db_url=None,
        ):
            return {
                "status": "ok",
                "user_id": "user_admin",
                "email": "admin@example.com",
                "key_prefix": "ad_cli",
                "user_created": False,
                "key_created": False,
                "api_key": secret,
                "protocol": "json-v1",
            }

    monkeypatch.setattr(
        start_orchestration,
        "Orchestrator",
        FakeOrchestrator,
    )

    target = tmp_path / "project-david-admin.key"

    result = runner.invoke(
        start_orchestration.app,
        [
            "bootstrap-admin",
            "--json",
            "--credential-file",
            str(target),
        ],
    )

    assert result.exit_code == 0

    # Plaintext must never reach command output.
    assert secret not in result.stdout
    assert '"api_key"' not in result.stdout

    payload = json.loads(result.stdout.strip())

    assert payload["status"] == "ok"
    assert payload["credential_state"] == "ready"
    assert payload["credential_file"] == str(target.resolve())

    assert UUID(payload["instance_id"]).version == 4
    assert (runtime / ".projectdavid-instance-id").read_text(
        encoding="utf-8"
    ) == payload["instance_id"]

    assert target.read_text(encoding="utf-8") == secret
