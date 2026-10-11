"""Run Pharmacy tests against a disposable PostgreSQL cluster and database."""

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

import psycopg

root = Path(__file__).resolve().parents[1]
for binary in ("initdb", "pg_ctl"):
    if not shutil.which(binary):
        sys.exit(f"{binary} unavailable")
with tempfile.TemporaryDirectory(prefix="pharmacy-tests-") as directory:
    data = Path(directory) / "pg"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    subprocess.run(["initdb", "-D", str(data), "-A", "trust", "--no-locale",
                    "--encoding=UTF8"], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["pg_ctl", "-D", str(data), "-l", str(Path(directory) / "postgres.log"),
                    "-o", f"-p {port} -h 127.0.0.1 -k ''", "start"],
                   check=True, stdout=subprocess.DEVNULL)
    try:
        password = secrets.token_urlsafe(24)
        user = os.environ.get("USER", "aakash")
        with psycopg.connect(host="127.0.0.1", port=port, dbname="postgres", user=user,
                             autocommit=True) as connection:
            connection.execute("CREATE ROLE pharmacy_app LOGIN")
            connection.execute("CREATE DATABASE pharmacy_workflow_test")
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith("PULSEGRID_PHARMACY_DB_")}
        environment.update(
            PULSEGRID_PHARMACY_TEST_DATABASE_URL=(
                f"postgresql+psycopg://{user}:{password}@127.0.0.1:{port}/pharmacy_workflow_test"
            ),
            PULSEGRID_PHARMACY_DB_HOST="127.0.0.1",
            PULSEGRID_PHARMACY_DB_PORT=str(port),
            PULSEGRID_PHARMACY_DB_NAME="pharmacy_workflow_test",
            PULSEGRID_PHARMACY_DB_USER=user,
            PULSEGRID_PHARMACY_DB_PASSWORD=password,
        )
        clean_environment = {k: v for k, v in environment.items()
                             if not k.startswith("PULSEGRID_PHARMACY_")}
        basic = subprocess.run([sys.executable, "-m", "pytest", "tests/test_app.py",
                                "tests/test_database.py", "-q", *sys.argv[1:]],
                               cwd=root, env=clean_environment)
        workflow = subprocess.run([sys.executable, "-m", "pytest",
                                   "tests/test_phase2_workflows.py", "-q", *sys.argv[1:]],
                                  cwd=root, env=environment)
        result = max(basic.returncode, workflow.returncode)
    finally:
        subprocess.run(["pg_ctl", "-D", str(data), "-m", "fast", "stop"],
                       check=True, stdout=subprocess.DEVNULL)
    sys.exit(result)
