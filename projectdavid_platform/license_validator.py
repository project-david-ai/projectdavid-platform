"""
projectdavid_platform/license_validator.py

Project David — Offline License Validator

Validates Ed25519-signed license files at startup.
No network calls. Works fully airgapped.

License file (.pdavid.lic) is placed in the project root by the customer.
"""

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

# ─── PUBLIC KEY ─────────────────────────────────────────────────────────────
# Generated once with scripts/generate_keypair.py
# Private key stays with the author. This public key is safe to distribute.
# Override at runtime via PDAVID_PUBLIC_KEY_B64 env var (preferred for deployments).
_PDAVID_PUBLIC_KEY_DEFAULT = "yw8e90FT7HvtBT9cPH9cS1xTX7I3gR3dlGCvU6h4ZJg="


def _get_public_key() -> str:
    return os.environ.get("PDAVID_PUBLIC_KEY_B64", _PDAVID_PUBLIC_KEY_DEFAULT)


# ─── CONSTANTS ───────────────────────────────────────────────────────────────
LICENSE_FILENAME = ".pdavid.lic"
GRACE_PERIOD_DAYS = 30
REMINDER_THRESHOLD = 60  # days before expiry to start warning
CONTACT_EMAIL = "licensing@projectdavid.co.uk"
CONTACT_URL = "https://projectdavid.co.uk"

# ─── RESULT ──────────────────────────────────────────────────────────────────


class LicenseStatus:
    VALID = "valid"
    GRACE = "grace"  # missing but within grace period
    EXPIRED = "expired"
    INVALID = "invalid"  # signature mismatch or malformed
    MISSING = "missing"  # no license file found


class LicenseResult:
    def __init__(
        self,
        status: str,
        customer: Optional[str] = None,
        org_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        days_remaining: Optional[int] = None,
        days_in_grace: Optional[int] = None,
        message: Optional[str] = None,
    ):
        self.status = status
        self.customer = customer
        self.org_id = org_id
        self.expires_at = expires_at
        self.days_remaining = days_remaining
        self.days_in_grace = days_in_grace
        self.message = message

    @property
    def is_runnable(self) -> bool:
        return self.status in (LicenseStatus.VALID, LicenseStatus.GRACE)


# ─── VALIDATOR ───────────────────────────────────────────────────────────────


def validate_license(license_path: Optional[str] = None) -> LicenseResult:
    """
    Validate the license file. Returns a LicenseResult with full details.
    No network calls made under any circumstances.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        # cryptography not installed — skip validation (dev mode)
        return LicenseResult(
            LicenseStatus.VALID,
            message="cryptography not installed — skipping validation",
        )

    # ── Locate license file ──────────────────────────────────────────────────
    search_paths = [
        Path(license_path) if license_path else None,
        (
            Path(os.environ.get("PDAVID_LICENSE_PATH", ""))
            if os.environ.get("PDAVID_LICENSE_PATH")
            else None
        ),
        Path.cwd() / LICENSE_FILENAME,
        Path.home() / ".pdavid" / LICENSE_FILENAME,
    ]

    lic_file = None
    for p in search_paths:
        if p and p.exists():
            lic_file = p
            break

    now = datetime.now(timezone.utc)

    if not lic_file:
        # Check if we're within the grace period since first run
        grace_file = Path.home() / ".pdavid" / ".grace_start"
        if not grace_file.exists():
            grace_file.parent.mkdir(mode=0o700, exist_ok=True)
            grace_file.write_text(now.isoformat())

        grace_start = datetime.fromisoformat(grace_file.read_text().strip())
        days_in_grace = (now - grace_start).days

        if days_in_grace <= GRACE_PERIOD_DAYS:
            return LicenseResult(
                status=LicenseStatus.GRACE,
                days_in_grace=days_in_grace,
                message=f"No license file found. Grace period: {GRACE_PERIOD_DAYS - days_in_grace} day(s) remaining.",
            )
        else:
            return LicenseResult(
                status=LicenseStatus.MISSING,
                message="Grace period expired. A commercial license is required.",
            )

    # ── Parse license file ───────────────────────────────────────────────────
    try:
        data = json.loads(lic_file.read_text())
        payload = data["payload"]
        signature_b64 = data["signature"]
    except Exception:
        return LicenseResult(
            status=LicenseStatus.INVALID, message="License file is malformed."
        )

    # ── Verify signature ─────────────────────────────────────────────────────
    try:
        pub_bytes = base64.b64decode(_get_public_key())
        sig_bytes = base64.b64decode(signature_b64)
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        payload_bytes = json.dumps(
            payload, separators=(",", ":"), sort_keys=True
        ).encode()
        pub_key.verify(sig_bytes, payload_bytes)
    except InvalidSignature:
        return LicenseResult(
            status=LicenseStatus.INVALID, message="License signature is invalid."
        )
    except Exception as e:
        return LicenseResult(
            status=LicenseStatus.INVALID, message=f"License validation error: {e}"
        )

    # ── Check expiry ─────────────────────────────────────────────────────────
    try:
        expires_at = datetime.fromisoformat(payload["expires_at"])
    except Exception:
        return LicenseResult(
            status=LicenseStatus.INVALID, message="License expiry date is malformed."
        )

    days_remaining = (expires_at - now).days

    if days_remaining < 0:
        return LicenseResult(
            status=LicenseStatus.EXPIRED,
            customer=payload.get("customer"),
            org_id=payload.get("org_id"),
            expires_at=expires_at,
            days_remaining=0,
            message="License has expired.",
        )

    return LicenseResult(
        status=LicenseStatus.VALID,
        customer=payload.get("customer"),
        org_id=payload.get("org_id"),
        expires_at=expires_at,
        days_remaining=days_remaining,
    )


# ─── ENFORCEMENT ─────────────────────────────────────────────────────────────


def enforce_license(verbose: bool = False) -> None:
    """
    Call this at startup. Prints appropriate messages and exits if not licensed.
    """
    result = validate_license()

    _print_header()

    if result.status == LicenseStatus.VALID:
        typer.echo(f"  ✅ Licensed to  : {result.customer}")
        typer.echo(f"  📋 Org ID       : {result.org_id}")
        typer.echo(
            f"  📅 Expires      : {result.expires_at.strftime('%Y-%m-%d')} ({result.days_remaining} days remaining)"
        )

        if result.days_remaining <= REMINDER_THRESHOLD:
            typer.echo(f"\n  ⚠️  License expires in {result.days_remaining} days.")
            typer.echo(f"  Renew at: {CONTACT_EMAIL}")

        _print_footer()
        return

    if result.status == LicenseStatus.GRACE:
        days_left = GRACE_PERIOD_DAYS - result.days_in_grace
        typer.echo("  ⚠️  No license file found.")
        typer.echo(f"  Grace period    : {days_left} day(s) remaining")
        typer.echo(
            "\n  Project David Platform requires a commercial license for production use."
        )
        typer.echo(f"  Contact : {CONTACT_EMAIL}")
        typer.echo(f"  Website : {CONTACT_URL}")
        typer.echo(f"\n  Place your license file at: {Path.cwd() / LICENSE_FILENAME}")
        _print_footer()
        return

    # ── Not runnable ─────────────────────────────────────────────────────────
    _print_footer()

    if result.status == LicenseStatus.MISSING:
        _print_license_required("No license file found and grace period has expired.")
    elif result.status == LicenseStatus.EXPIRED:
        _print_license_required(
            f"License expired on {result.expires_at.strftime('%Y-%m-%d')}."
        )
    elif result.status == LicenseStatus.INVALID:
        _print_license_required(f"License file is invalid: {result.message}")

    raise SystemExit(1)


def _print_header():
    typer.echo("\n" + "=" * 60)
    typer.echo("  Project David Platform — License")
    typer.echo("=" * 60)


def _print_footer():
    typer.echo("=" * 60 + "\n")


def _print_license_required(reason: str):
    typer.echo("\n" + "=" * 60, err=True)
    typer.echo("  ❌ Commercial License Required", err=True)
    typer.echo("=" * 60, err=True)
    typer.echo(f"\n  {reason}\n", err=True)
    typer.echo("  Project David Platform is free for noncommercial use.", err=True)
    typer.echo("  Commercial use requires a license.\n", err=True)
    typer.echo("  To obtain a license:", err=True)
    typer.echo(f"    Email   : {CONTACT_EMAIL}", err=True)
    typer.echo(f"    Website : {CONTACT_URL}\n", err=True)
    typer.echo("  Include your organisation name, country, and intended use.", err=True)
    typer.echo("  We respond within 48 hours.", err=True)
    typer.echo("=" * 60 + "\n", err=True)
