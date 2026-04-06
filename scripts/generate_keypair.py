"""
scripts/generate_keypair.py

Project David — Ed25519 Keypair Generator

Run this ONCE. Store private.key somewhere safe and never commit it.
The public key output goes into projectdavid_platform/license_validator.py.

USAGE:
    python scripts/generate_keypair.py
"""

import base64
import sys
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )
except ImportError:
    print("[error] pip install cryptography")
    sys.exit(1)


def main():
    key = Ed25519PrivateKey.generate()
    pub_bytes = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    priv_bytes = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())

    pub_b64 = base64.b64encode(pub_bytes).decode()
    priv_b64 = base64.b64encode(priv_bytes).decode()

    key_dir = Path.home() / ".pdavid"
    key_dir.mkdir(mode=0o700, exist_ok=True)
    key_file = key_dir / "private.key"
    key_file.write_text(priv_b64)
    key_file.chmod(0o600)

    print("\n" + "=" * 60)
    print("  Project David — Ed25519 Keypair Generated")
    print("=" * 60)
    print(f"\n  Private key saved to: {key_file}")
    print("  ⚠️  NEVER commit this file. Back it up securely.\n")
    print("  Public key (paste into projectdavid_platform/license_validator.py):")
    print(f'\n    PDAVID_PUBLIC_KEY = "{pub_b64}"\n')
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
