"""
scripts/generate_license.py

Project David — Commercial License Generator

Run this offline on your secure machine to issue a license file
to a paying customer. The private key never leaves your possession.

USAGE:
    python scripts/generate_license.py \
        --customer  "Acme Defence Ltd" \
        --org-id    "acme-defence" \
        --country   "GB" \
        --nodes     5 \
        --days      365 \
        --key       ~/.pdavid/private.key \
        --out       acme_defence.pdavid.lic

FIRST TIME SETUP (run once, keep private.key safe forever):
    python scripts/generate_keypair.py
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding  # noqa: F401
    from cryptography.hazmat.primitives.serialization import NoEncryption  # noqa: F401
    from cryptography.hazmat.primitives.serialization import PrivateFormat  # noqa: F401


except ImportError:
    print("[error] pip install cryptography")
    sys.exit(1)


def load_private_key(path: str) -> Ed25519PrivateKey:
    raw = base64.b64decode(Path(path).read_text().strip())
    return Ed25519PrivateKey.from_private_bytes(raw)


def generate_license(
    customer: str,
    org_id: str,
    country: str,
    nodes: int,
    days: int,
    private_key: Ed25519PrivateKey,
) -> dict:
    now = datetime.now(timezone.utc)
    payload = {
        "schema": "pdavid-license-v1",
        "customer": customer,
        "org_id": org_id,
        "country": country,
        "max_nodes": nodes,
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "features": ["platform"],
    }

    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    signature = private_key.sign(payload_bytes)

    return {
        "payload": payload,
        "signature": base64.b64encode(signature).decode(),
    }


def main():
    parser = argparse.ArgumentParser(description="Generate a Project David license")
    parser.add_argument(
        "--customer", required=True, help="Customer name e.g. 'Acme Defence Ltd'"
    )
    parser.add_argument(
        "--org-id", required=True, help="Short org slug e.g. 'acme-defence'"
    )
    parser.add_argument("--country", required=True, help="ISO country code e.g. 'GB'")
    parser.add_argument(
        "--nodes", type=int, default=1, help="Max cluster nodes (default: 1)"
    )
    parser.add_argument(
        "--days", type=int, default=365, help="License duration in days (default: 365)"
    )
    parser.add_argument(
        "--key", default="~/.pdavid/private.key", help="Path to private key file"
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output .lic file path (default: <org_id>.pdavid.lic)",
    )
    args = parser.parse_args()

    key_path = Path(args.key).expanduser()
    if not key_path.exists():
        print(f"[error] Private key not found: {key_path}")
        print("Run: python scripts/generate_keypair.py")
        sys.exit(1)

    private_key = load_private_key(str(key_path))
    license_data = generate_license(
        customer=args.customer,
        org_id=args.org_id,
        country=args.country,
        nodes=args.nodes,
        days=args.days,
        private_key=private_key,
    )

    out_path = Path(args.out or f"{args.org_id}.pdavid.lic")
    out_path.write_text(json.dumps(license_data, indent=2))

    print(f"\n✅ License generated → {out_path}")
    print(f"   Customer  : {args.customer}")
    print(f"   Org ID    : {args.org_id}")
    print(f"   Country   : {args.country}")
    print(f"   Max nodes : {args.nodes}")
    print(f"   Expires   : {license_data['payload']['expires_at'][:10]}")
    print(f"\n   Send {out_path} to the customer.")
    print(
        "   They place it at the root of their projectdavid-platform directory as .pdavid.lic"
    )


if __name__ == "__main__":
    main()
