"""Copy read-only operator secrets into tmpfs, then permanently drop privileges."""

import os
import sys
from pathlib import Path

if os.getuid() != 0:
    raise SystemExit("Credential bootstrap requires initial container root")
destination = Path("/run/credentials")
destination.mkdir(exist_ok=True, mode=0o700)
for key in ("PRIVATE_KEY_PATH", "SERVICE_PRIVATE_KEY_PATH", "IDEMPOTENCY_SECRET_PATH"):
    variable = "PULSEGRID_PHARMACY_AUTH_" + key
    source = os.environ.get(variable)
    if not source:
        continue
    data = Path(source).read_bytes()
    if len(data) > 16384:
        raise SystemExit("Credential size exceeds bound")
    target = destination / key.lower()
    # Restart may leave an existing tmpfs file owned by the previous process.
    if target.exists():
        target.unlink()
    with os.fdopen(
        os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400), "wb"
    ) as f:
        f.write(data)
    os.chown(target, 10001, 10001)
    os.environ[variable] = str(target)
os.chown(destination, 10001, 10001)
os.setgroups([])
os.setgid(10001)
os.setuid(10001)
os.execvp(sys.argv[1], sys.argv[1:])
