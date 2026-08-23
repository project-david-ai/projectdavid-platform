from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Mapping


class CredentialHandoffError(ValueError):
    """Raised when a Project David bootstrap credential cannot be handed off safely."""


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
            # Windows chmod semantics are limited. The file still resides in
            # the current user's Q runtime directory and is never exposed
            # through stdout, IPC, or logs.
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
    """
    api_key = _validate_admin_api_key(str(bootstrap_result.get("api_key") or ""))

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

    return safe_result
