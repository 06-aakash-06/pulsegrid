"""Generate a private local .env once; never prints or overwrites credentials."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[2]
target = root / ".env"
content = root.joinpath(".env.example").read_text().splitlines()
lines = []
for line in content:
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        if key.endswith("PASSWORD"):
            value = secrets.token_urlsafe(32)
        line = key + "=" + value
    lines.append(line)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as stream:
    stream.write("\n".join(lines) + "\n")
print("Created private .env with random local credentials")
