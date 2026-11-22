from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID, uuid4

_INSTANCE_ID_FILE = ".projectdavid-instance-id"


class CredentialHandoffError(ValueError):
    """Raised when Project David runtime handoff state is invalid."""


def _validate_admin_api_key(api_key: str) -> str:
    candidate = str(api_key or "").strip()

    if not candidate.startswith("ad_"):
        raise CredentialHandoffError(
            "Project David bootstrap did not provide a valid admin credential"
        )

    if any(character.isspace() for character in candidate):
        raise CredentialHandoffError(
            "Project David admin credential contains invalid whitespace"
        )

    return candidate


def _validate_instance_id(instance_id: str) -> str:
    candidate = str(instance_id or "").strip()

    try:
        parsed = UUID(candidate)
    except (ValueError, AttributeError) as exc:
        raise CredentialHandoffError(
            "Project David runtime instance ID is invalid"
        ) from exc

    if parsed.version != 4:
        raise CredentialHandoffError("Project David runtime instance ID is invalid")

    return str(parsed)


def get_or_create_runtime_instance_id(
    runtime_dir: str | Path | None = None,
) -> str:
    """
    Return the stable non-secret identity of this Project David runtime.

    The ID belongs to mutable runtime state, not to the installed launcher.
    """
    runtime = (
        Path(runtime_dir).expanduser().resolve()
        if runtime_dir is not None
        else Path.cwd().resolve()
    )

    target = runtime / _INSTANCE_ID_FILE

    if target.exists():
        return _validate_instance_id(target.read_text(encoding="utf-8"))

    instance_id = str(uuid4())

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL

    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    descriptor = None

    try:
        descriptor = os.open(
            target,
            flags,
            stat.S_IRUSR | stat.S_IWUSR,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            descriptor = None
            handle.write(instance_id)
            handle.flush()
            os.fsync(handle.fileno())

    except FileExistsError:
        return _validate_instance_id(target.read_text(encoding="utf-8"))

    finally:
        if descriptor is not None:
            os.close(descriptor)

    return instance_id


def write_admin_credential_file(
    credential_file: str | Path,
    api_key: str,
) -> Path:
    """
    Atomically write the Project David admin credential to a handoff file.

    The caller may pass a Windows or POSIX path. The secret is never logged or
    returned by this function.
    """
    secret = _validate_admin_api_key(api_key)

    target = Path(credential_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC

    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    descriptor = None

    try:
        descriptor = os.open(
            temporary,
            flags,
            stat.S_IRUSR | stat.S_IWUSR,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            descriptor = None
            handle.write(secret)
            handle.flush()
            os.fsync(handle.fileno())

        try:
            os.chmod(
                temporary,
                stat.S_IRUSR | stat.S_IWUSR,
            )
        except OSError:
            pass

        os.replace(
            temporary,
            target,
        )

        return target

    finally:
        if descriptor is not None:
            os.close(descriptor)

        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def handoff_admin_credential(
    bootstrap_result: Mapping[str, Any],
    credential_file: str | Path,
) -> dict[str, Any]:
    """
    Persist the bootstrap credential and return a renderer-safe result.

    The returned object deliberately contains no plaintext admin credential.
    It also exposes the stable non-secret identity of the active runtime.
    """
    api_key = _validate_admin_api_key(str(bootstrap_result.get("api_key") or ""))

    instance_id = get_or_create_runtime_instance_id()

    written_path = write_admin_credential_file(
        credential_file,
        api_key,
    )

    safe_result = {
        key: value
        for key, value in bootstrap_result.items()
        if key
        not in {
            "api_key",
            "admin_api_key",
        }
    }

    safe_result["credential_state"] = "ready"
    safe_result["credential_file"] = str(written_path)
    safe_result["instance_id"] = instance_id

    return safe_result
