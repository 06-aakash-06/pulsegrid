"""Guarded reset and readiness marker for the selected local PulseGrid demo stack.

The default command is a dry run. Reset requires a private, restore-verified
backup and the exact selected Compose project. It removes only that project's
PostgreSQL, Redis, RabbitMQ, and two Phase 4 cache volumes. Observability and
the separate Phase 10 audit project are checked and preserved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT = "pulsegrid"
AUDIT_PROJECT = "pulsegrid-audit-20261025"
COMPOSE_FILES = [
    "compose.yaml",
    "services/patient/compose.auth.yaml",
    "compose.phase4.yaml",
    "compose.observability.yaml",
]
BASE_VOLUMES = {
    "pulsegrid_postgres_data",
    "pulsegrid_redis_data",
    "pulsegrid_rabbitmq_data",
}
PRESERVED_VOLUMES = {
    "pulsegrid_prometheus_data",
    "pulsegrid_tempo_data",
    "pulsegrid_grafana_data",
}
EXPECTED_DATABASES = {
    "patient_db", "doctor_db", "appointment_db", "records_db",
    "pharmacy_db", "billing_db", "emergency_db",
}
DEFAULT_BACKUP = Path("/Users/aakash/.codex/backups/pulsegrid-phase11/20261025T101732Z")


def run(args: list[str], *, capture: bool = True) -> str:
    result = subprocess.run(args, cwd=ROOT, text=True, capture_output=capture)
    if result.returncode:
        detail = result.stderr.strip() if capture else ""
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{detail}")
    return result.stdout.strip() if capture else ""


def inspect_container(name: str) -> dict:
    return json.loads(run(["docker", "inspect", name]))[0]


def json_lines(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def check_target_identity() -> tuple[list[dict], str, list[str]]:
    if Path.cwd().resolve() != ROOT:
        raise RuntimeError(f"Run from the repository root: {ROOT}")
    containers = json_lines(run([
        "docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", "{{json .}}",
    ]))
    if not containers:
        raise RuntimeError("No containers identify the selected pulsegrid Compose project.")
    for item in containers:
        data = inspect_container(item["Names"])
        labels = data["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project.working_dir") != str(ROOT):
            raise RuntimeError(f"Container {item['Names']} is not owned by this checkout.")
    gateway = inspect_container("pulsegrid-traefik-1")
    labels = gateway["Config"].get("Labels") or {}
    if labels.get("com.docker.compose.project") != PROJECT:
        raise RuntimeError("The gateway label does not match the explicitly selected target.")
    ports = (gateway.get("HostConfig", {}).get("PortBindings", {}).get("8080/tcp") or [])
    if not any(p.get("HostIp") == "127.0.0.1" and p.get("HostPort") == "8080" for p in ports):
        raise RuntimeError("The selected gateway is not bound to loopback port 8080.")
    audit = json_lines(run([
        "docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={AUDIT_PROJECT}",
        "--format", "{{json .}}",
    ]))
    if not audit:
        raise RuntimeError("The separate Phase 10 audit project is not present; isolation cannot be confirmed.")
    audit_volume = run(["docker", "volume", "inspect", "--format", "{{.Name}}", "pulsegrid-audit-20261025_postgres_data"])
    if audit_volume != "pulsegrid-audit-20261025_postgres_data":
        raise RuntimeError("The Phase 10 PostgreSQL volume was not found under its isolated project name.")
    names = [item["Names"] for item in containers]
    gateway_config = labels.get("com.docker.compose.project.config_files", "")
    if any(str(ROOT / file) not in gateway_config for file in COMPOSE_FILES):
        raise RuntimeError("The active project Compose definition differs from the expected Phase 11 target.")
    return containers, audit_volume, names


def volume_names_to_remove(names: list[str]) -> list[str]:
    expected_cache_containers = {"pulsegrid-cache_a-1", "pulsegrid-cache_b-1"}
    volume_owners: dict[str, set[str]] = {}
    container_ids = run(["docker", "ps", "-aq"]).splitlines()
    for container_id in container_ids:
        attached = json.loads(run(["docker", "inspect", container_id]))[0]
        attached_name = attached.get("Name", "").lstrip("/")
        for mount in attached.get("Mounts", []):
            if mount.get("Type") == "volume":
                volume_owners.setdefault(mount["Name"], set()).add(attached_name)
    discovered = set(BASE_VOLUMES)
    cache_found = set()
    for container_name in expected_cache_containers:
        data = inspect_container(container_name)
        labels = data["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") != PROJECT:
            raise RuntimeError(f"{container_name} is outside the selected project.")
        data_mounts = [m for m in data.get("Mounts", []) if m.get("Destination") == "/data" and m.get("Type") == "volume"]
        if len(data_mounts) != 1:
            raise RuntimeError(f"Could not identify exactly one cache volume for {container_name}.")
        volume = data_mounts[0]["Name"]
        volume_info = json.loads(run(["docker", "volume", "inspect", volume]))[0]
        volume_labels = volume_info.get("Labels") or {}
        if volume_labels.get("com.docker.compose.project") not in {None, PROJECT}:
            raise RuntimeError(f"Cache volume {volume} belongs to another project.")
        if volume_owners.get(volume, set()) != {container_name}:
            raise RuntimeError(f"Cache volume {volume} is shared or not exclusively attached to {container_name}.")
        cache_found.add(volume)
    if len(cache_found) != 2:
        raise RuntimeError("The selected project does not have exactly two separate Phase 4 cache volumes.")
    discovered.update(cache_found)
    expected_named_owners = {
        "pulsegrid_postgres_data": "pulsegrid-postgres-1",
        "pulsegrid_redis_data": "pulsegrid-redis-1",
        "pulsegrid_rabbitmq_data": "pulsegrid-rabbitmq-1",
    }
    for volume in BASE_VOLUMES:
        info = json.loads(run(["docker", "volume", "inspect", volume]))[0]
        if (info.get("Labels") or {}).get("com.docker.compose.project") != PROJECT:
            raise RuntimeError(f"Named volume {volume} is not labeled as target-owned.")
        if volume_owners.get(volume, set()) != {expected_named_owners[volume]}:
            raise RuntimeError(f"Target volume {volume} is shared or not exclusively mounted by its expected service.")
    for volume in PRESERVED_VOLUMES:
        if run(["docker", "volume", "inspect", "--format", "{{.Name}}", volume]) != volume:
            raise RuntimeError(f"Expected retained observability volume {volume} is missing.")
        if volume in discovered:
            raise RuntimeError(f"Refusing to remove preserved volume {volume}.")
    return sorted(discovered)


def verify_private_backup(backup: Path) -> dict:
    backup = backup.resolve()
    if ROOT == backup or ROOT in backup.parents:
        raise RuntimeError("The backup directory must remain outside the active repository/deployment.")
    if not backup.is_dir() or backup.stat().st_mode & 0o077:
        raise RuntimeError("The backup directory must exist and be private (mode 0700 or stricter).")
    manifest_path = backup / "private-deletion-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    rv = manifest.get("restore_verification") or {}
    if manifest.get("target_project") != PROJECT or rv.get("all_archives_restored") != "yes" or rv.get("all_foreign_keys_validated") != "yes":
        raise RuntimeError("PostgreSQL archive restore verification is incomplete for the selected target.")
    final = manifest.get("final_pre_reset_database_snapshot") or {}
    if final.get("restore_verification") != "verified":
        raise RuntimeError("The quiescent final PostgreSQL snapshot has not been restore-verified.")
    for filename, record in (manifest.get("files") or {}).items():
        path = backup / filename
        if not path.is_file() or path.stat().st_size != record.get("bytes"):
            raise RuntimeError(f"Verified PostgreSQL archive is missing or has changed: {filename}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != record.get("sha256"):
            raise RuntimeError(f"Verified PostgreSQL archive checksum changed: {filename}")
    config = manifest.get("private_configuration_backup") or {}
    config_archive = backup / str(config.get("archive", ""))
    if not config_archive.is_file() or config_archive.stat().st_size != config.get("bytes"):
        raise RuntimeError("The private pre-reset environment/auth configuration archive is missing.")
    if hashlib.sha256(config_archive.read_bytes()).hexdigest() != config.get("sha256"):
        raise RuntimeError("The private configuration archive checksum does not match the manifest.")
    runtime = manifest.get("runtime_state_backup") or {}
    if runtime.get("status") != "verified":
        raise RuntimeError("Redis/RabbitMQ/cache/config runtime-state archive is not yet verified.")
    for service, record in runtime.get("volume_archives", {}).items():
        name = record.get("archive", "")
        path = backup / name
        if not path.is_file() or path.stat().st_size != record.get("archive_bytes"):
            raise RuntimeError(f"Runtime-state archive is missing or changed: {service}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.get("archive_sha256"):
            raise RuntimeError(f"Runtime-state archive checksum mismatch: {service}")
    return manifest


def dry_run(backup: Path) -> None:
    containers, audit_volume, names = check_target_identity()
    volumes = volume_names_to_remove(names)
    manifest = verify_private_backup(backup)
    print(json.dumps({
        "mode": "dry-run",
        "target_project": PROJECT,
        "gateway": "127.0.0.1:8080",
        "target_containers_to_remove": names,
        "target_data_volumes_to_remove": volumes,
        "observability_volumes_to_preserve": sorted(PRESERVED_VOLUMES),
        "phase10_project": AUDIT_PROJECT,
        "phase10_postgres_volume_to_preserve": audit_volume,
        "postgres_archives_restore_verified": True,
        "runtime_state_archives_verified": True,
        "inventory_databases": len(manifest["database_inventory"]),
        "inventory_business_tables": sum(len(db.get("tables", {})) for db in manifest["database_inventory"].values()),
        "exactly_execute_with": "--execute --target pulsegrid --confirm-target pulsegrid",
    }, indent=2))


def execute_reset(backup: Path) -> None:
    containers, audit_volume, names = check_target_identity()
    volumes = volume_names_to_remove(names)
    manifest = verify_private_backup(backup)
    if set(volumes) & PRESERVED_VOLUMES:
        raise RuntimeError("Reset candidate intersects an observability volume.")
    run(["docker", "compose", *sum((["-f", name] for name in COMPOSE_FILES), []), "-p", PROJECT, "down", "--remove-orphans"], capture=False)
    residual = json_lines(run([
        "docker", "ps", "-a", "--filter", f"label=com.docker.compose.project={PROJECT}",
        "--format", "{{json .}}",
    ]))
    if residual:
        raise RuntimeError("Target containers remain after Compose down; no volume deletion was attempted.")
    for volume in volumes:
        info = json.loads(run(["docker", "volume", "inspect", volume]))[0]
        attachments = info.get("Containers") or {}
        if attachments:
            raise RuntimeError(f"Refusing to remove attached volume {volume}.")
        run(["docker", "volume", "rm", volume], capture=False)
    remaining_audit = run(["docker", "volume", "inspect", "--format", "{{.Name}}", audit_volume])
    if remaining_audit != audit_volume:
        raise RuntimeError("Phase 10 audit volume verification failed after target reset.")
    for volume in PRESERVED_VOLUMES:
        if run(["docker", "volume", "inspect", "--format", "{{.Name}}", volume]) != volume:
            raise RuntimeError(f"Observability volume {volume} changed during reset.")
    manifest["runtime_state_backup"]["target_volumes_retired"] = volumes
    manifest["runtime_state_backup"]["target_containers_retired"] = names
    manifest["runtime_state_backup"]["reset_executed_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["status"] = "Backup verified; selected project business/state volumes retired; awaiting clean migration and seed verification"
    save_private_manifest(backup / "private-deletion-manifest.json", manifest)
    marker = {
        "project": PROJECT,
        "status": "awaiting-migrations",
        "backup_manifest_sha256": hashlib.sha256((backup / "private-deletion-manifest.json").read_bytes()).hexdigest(),
        "target_volumes_retired": volumes,
        "reset_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    private_write(ROOT / "secrets/phase11/rebuild-ready.json", marker)
    print(json.dumps({"status": "reset-complete-awaiting-migrations", "retired_volumes": volumes, "phase10_volume_preserved": audit_volume}, indent=2))


def save_private_manifest(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    os.chmod(path, 0o600)


def private_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    save_private_manifest(path, data)


def mark_ready() -> None:
    marker_path = ROOT / "secrets/phase11/rebuild-ready.json"
    if not marker_path.is_file():
        raise RuntimeError("The target reset has not been authorized and executed by this guard.")
    marker = json.loads(marker_path.read_text())
    if marker.get("project") != PROJECT or marker.get("status") != "awaiting-migrations":
        raise RuntimeError("The rebuild marker is not in the post-reset migration state.")
    check_target_identity()
    pg = inspect_container("pulsegrid-postgres-1")
    health = (pg.get("State", {}).get("Health") or {}).get("Status")
    if health != "healthy":
        raise RuntimeError("PostgreSQL is not healthy; migrations cannot be marked ready.")
    created = run(["docker", "volume", "inspect", "--format", "{{.CreatedAt}}", "pulsegrid_postgres_data"])
    dbs_text = run([
        "docker", "exec", "pulsegrid-postgres-1", "sh", "-ec",
        "psql -U \"$POSTGRES_USER\" -d postgres -Atqc \"SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname\"",
    ])
    dbs = set(dbs_text.splitlines())
    if not EXPECTED_DATABASES <= dbs:
        raise RuntimeError(f"Expected service databases are missing: {sorted(EXPECTED_DATABASES - dbs)}")
    for service in ("patient", "doctor", "appointment", "records", "pharmacy", "billing", "emergency"):
        if inspect_container(f"pulsegrid-{service}-migrate-1")["State"].get("ExitCode") != 0:
            raise RuntimeError(f"{service} migration did not exit successfully.")
        api = inspect_container(f"pulsegrid-{service}-1")
        if (api.get("State", {}).get("Health") or {}).get("Status") != "healthy":
            raise RuntimeError(f"{service} API is not healthy.")
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/api/v1/patients/health/ready", timeout=5) as response:
            if response.status != 200:
                raise RuntimeError("Patient readiness endpoint did not return HTTP 200.")
    except (OSError, urllib.error.URLError) as error:
        raise RuntimeError("Gateway readiness failed after migration.") from error
    marker.update({
        "status": "ready",
        "postgres_volume_created_at": created,
        "migrated_databases": sorted(EXPECTED_DATABASES),
        "marked_ready_at_utc": datetime.now(timezone.utc).isoformat(),
    })
    private_write(marker_path, marker)
    print(json.dumps({"status": "ready-for-owner-api-seed", "migrated_databases": sorted(EXPECTED_DATABASES), "postgres_volume_created_at": created}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    parser.add_argument("--target", default="pulsegrid")
    parser.add_argument("--confirm-target", default="")
    parser.add_argument("--execute", action="store_true", help="Execute the guarded destructive reset; dry-run is the default.")
    parser.add_argument("--mark-ready", action="store_true", help="Verify clean migrated databases and enable owner-API seeding.")
    args = parser.parse_args()
    if args.target != PROJECT:
        raise SystemExit("Only the explicitly selected pulsegrid target is accepted.")
    if args.mark_ready:
        mark_ready()
        return
    if args.execute and args.confirm_target != PROJECT:
        raise SystemExit("Destructive reset requires --confirm-target pulsegrid.")
    if args.execute:
        execute_reset(args.backup_dir)
    else:
        dry_run(args.backup_dir)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
