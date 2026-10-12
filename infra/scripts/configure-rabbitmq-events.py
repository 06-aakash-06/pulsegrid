"""Create least-privilege publisher and consumer RabbitMQ accounts."""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"
DEFAULT_PUBLISHER_USER = "pulsegrid_events_publisher"
DEFAULT_CONSUMER_USER = "pulsegrid_events_consumer"
COMPOSE = [
    "docker",
    "compose",
    "-f",
    "compose.yaml",
]


def read_env() -> tuple[list[str], dict[str, str]]:
    if not ENV_FILE.is_file():
        raise SystemExit("Missing .env; run infra/scripts/init-env.py first")
    lines = ENV_FILE.read_text().splitlines()
    values = {}
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return lines, values


def persist_event_credentials() -> tuple[str, str, str, str]:
    lines, values = read_env()
    values.pop("RABBITMQ_EVENTS_USER", None)
    values.pop("RABBITMQ_EVENTS_PASSWORD", None)
    publisher_user = values.get("RABBITMQ_EVENTS_PUBLISHER_USER") or DEFAULT_PUBLISHER_USER
    consumer_user = values.get("RABBITMQ_EVENTS_CONSUMER_USER") or DEFAULT_CONSUMER_USER
    for key, username in (
        ("RABBITMQ_EVENTS_PUBLISHER_USER", publisher_user),
        ("RABBITMQ_EVENTS_CONSUMER_USER", consumer_user),
    ):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", username):
            raise SystemExit(f"{key} has an invalid value")
    if publisher_user == consumer_user:
        raise SystemExit("Publisher and consumer RabbitMQ users must be distinct")

    updated = []
    publisher_password = values.get("RABBITMQ_EVENTS_PUBLISHER_PASSWORD") or secrets.token_urlsafe(32)
    consumer_password = values.get("RABBITMQ_EVENTS_CONSUMER_PASSWORD") or secrets.token_urlsafe(32)
    managed = {
        "RABBITMQ_EVENTS_PUBLISHER_USER": publisher_user,
        "RABBITMQ_EVENTS_PUBLISHER_PASSWORD": publisher_password,
        "RABBITMQ_EVENTS_CONSUMER_USER": consumer_user,
        "RABBITMQ_EVENTS_CONSUMER_PASSWORD": consumer_password,
    }
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            updated.append(line)
            continue
        key = line.split("=", 1)[0].strip()
        if key in {"RABBITMQ_EVENTS_USER", "RABBITMQ_EVENTS_PASSWORD"}:
            continue
        if key in managed:
            updated.append(f"{key}={managed.pop(key)}")
        else:
            updated.append(line)
    updated.extend(f"{key}={value}" for key, value in managed.items())
    temporary = ENV_FILE.with_suffix(".env.phase5.tmp")
    temporary.write_text("\n".join(updated) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, ENV_FILE)
    os.chmod(ENV_FILE, 0o600)
    return (
        publisher_user,
        publisher_password,
        consumer_user,
        consumer_password,
    )


def main() -> None:
    publisher_user, publisher_password, consumer_user, consumer_password = persist_event_credentials()
    start = subprocess.run(
        [*COMPOSE, "up", "-d", "rabbitmq"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if start.returncode:
        raise SystemExit("Could not start the existing RabbitMQ service")
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            health = subprocess.run(
                [*COMPOSE, "exec", "-T", "rabbitmq", "rabbitmq-diagnostics", "-q", "ping"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=8,
            )
        except subprocess.TimeoutExpired:
            health = None
        if health is not None and health.returncode == 0:
            break
        time.sleep(2)
    else:
        raise SystemExit("RabbitMQ did not become healthy; event credentials were saved in ignored .env")

    script = r"""set -eu
IFS= read -r publisher_user
IFS= read -r publisher_password
IFS= read -r consumer_user
IFS= read -r consumer_password
ensure_user() {
  user=$1
  password=$2
  if ! rabbitmqctl add_user "$user" "$password" >/dev/null 2>&1; then
    rabbitmqctl change_password "$user" "$password" >/dev/null
  fi
  rabbitmqctl set_user_tags "$user" >/dev/null
}
ensure_user "$publisher_user" "$publisher_password"
ensure_user "$consumer_user" "$consumer_password"
rabbitmqctl set_permissions -p / "$publisher_user" \
  '^pulsegrid\.events$' '^pulsegrid\.events$' '^$' >/dev/null
rabbitmqctl set_permissions -p / "$consumer_user" \
  '^pulsegrid\.(events|dlx|appointment\.journey\.(pharmacy|billing)\.v1|dlq\.appointment\.journey\.(pharmacy|billing)\.v1)$' \
  '^pulsegrid\.(events|appointment\.journey\.(pharmacy|billing)\.v1|dlq\.appointment\.journey\.(pharmacy|billing)\.v1)$' \
  '^pulsegrid\.(events|dlx|appointment\.journey\.(pharmacy|billing)\.v1|dlq\.appointment\.journey\.(pharmacy|billing)\.v1)$' >/dev/null
if rabbitmqctl list_users | awk '$1=="pulsegrid_events"{found=1} END{exit !found}'; then
  rabbitmqctl delete_user pulsegrid_events >/dev/null
fi
"""
    result = subprocess.run(
        [*COMPOSE, "exec", "-T", "rabbitmq", "sh", "-c", script],
        cwd=ROOT,
        input=(
            f"{publisher_user}\n{publisher_password}\n"
            f"{consumer_user}\n{consumer_password}\n"
        ),
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            "RabbitMQ event user setup failed; ensure the existing RabbitMQ service is healthy"
        )
    print("Started RabbitMQ and configured scoped event accounts; credentials remain in ignored .env")


if __name__ == "__main__":
    main()
