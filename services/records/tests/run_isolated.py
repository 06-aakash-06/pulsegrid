"""Run tests on a disposable local PG cluster, never shared Compose resources."""

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for binary in ("initdb", "pg_ctl"):
    if not shutil.which(binary):
        sys.exit(
            f"{binary} unavailable; install local PostgreSQL or skip integration tests"
        )
resources = root / ".test-resources"
resources.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="records-tests-", dir=resources) as directory:
    data = Path(directory) / "pg"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(
        ["initdb", "-D", str(data), "-A", "trust", "--no-locale", "--encoding=UTF8"],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [
            "pg_ctl",
            "-D",
            str(data),
            "-l",
            str(Path(directory) / "postgres.log"),
            "-o",
            f"-p {port} -h 127.0.0.1 -k ''",
            "start",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    try:
        env = {
            **os.environ,
            "PULSEGRID_RECORDS_TEST_PORT": str(port),
            "PULSEGRID_RECORDS_TEST_CLUSTER": str(data),
            "PULSEGRID_RECORDS_TEST_PASSWORD": secrets.token_urlsafe(32),
        }
        # Ensure scaffold tests do not inherit production configuration.
        env = {
            k: v
            for k, v in env.items()
            if not k.startswith("PULSEGRID_RECORDS_DB_")
            and not k.startswith("PULSEGRID_RECORDS_AUTH_")
        }
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests",
                "--basetemp=" + str(Path(directory) / "pytest"),
                *sys.argv[1:],
            ],
            cwd=root,
            env=env,
        )
    finally:
        subprocess.run(
            ["pg_ctl", "-D", str(data), "-m", "fast", "stop"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    sys.exit(result.returncode)
