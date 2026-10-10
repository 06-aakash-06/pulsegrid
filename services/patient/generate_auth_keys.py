"""Generate operator-owned development keys once, outside tracked sources."""

import argparse
import json
import os
import secrets
from pathlib import Path
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--directory", type=Path, required=True)
args = parser.parse_args()
args.directory.mkdir(mode=0o700, parents=True, exist_ok=False)


def make(name, kid, service=None):
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    raw = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path = args.directory / (name + ".pem")
    with os.fdopen(
        os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as f:
        f.write(raw)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    public.update(kid=kid, alg="RS256", use="sig")
    if service:
        public["service"] = service
    return public


patient = make("patient-signing", "patient-dev-1")
(args.directory / "user-jwks.json").write_text(json.dumps({"keys": [patient]}))
service_keys = []
for domain in (
    "patient",
    "doctor",
    "appointment",
    "records",
    "pharmacy",
    "billing",
    "emergency",
):
    service_keys.append(make(domain + "-service", domain + "-service-1", domain))
(args.directory / "service-jwks.json").write_text(json.dumps({"keys": service_keys}))
with os.fdopen(
    os.open(
        args.directory / "idempotency.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    ),
    "wb",
) as f:
    f.write(secrets.token_bytes(32))
print("Generated development keys; private files are mode 0600. Never commit them.")
