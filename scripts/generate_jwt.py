"""Generate a JWT for local development.

On first run this creates an RSA keypair in the output directory: the private key
(`private.pem`) and the public key as a JWKS (`jwks.json`). The API reads the JWKS to verify tokens.
"""

import argparse
import json
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KID = "dev-key"
ALGORITHM = "RS256"


def load_or_create_key(out_dir: Path):
    private_path = out_dir / "private.pem"
    jwks_path = out_dir / "jwks.json"

    if private_path.exists():
        return serialization.load_pem_private_key(
            private_path.read_bytes(), password=None
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    private_path.chmod(0o600)

    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid=KID, use="sig", alg=ALGORITHM)
    jwks_path.write_text(json.dumps({"keys": [jwk]}, indent=2) + "\n")
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument(
        "--expires-in", type=int, default=3600, help="Lifetime in seconds"
    )
    parser.add_argument("--out-dir", type=Path, default=Path(".jwt"))
    args = parser.parse_args()

    key = load_or_create_key(args.out_dir)
    now = int(time.time())
    payload = {
        "sub": args.username,
        "username": args.username,
        "iat": now,
        "exp": now + args.expires_in,
    }
    print(jwt.encode(payload, key, algorithm=ALGORITHM, headers={"kid": KID}))


if __name__ == "__main__":
    main()
