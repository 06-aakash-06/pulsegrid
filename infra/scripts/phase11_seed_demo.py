"""Seed a fictional PulseGrid hospital through the seven owner APIs.

This command is additive and guarded. A clean local database is bootstrapped
through the existing Patient first-admin CLI; no service-owned tables are
written directly. Passwords and resumable state stay under ignored secrets/.
"""

from __future__ import annotations

import argparse
import httpx
import json
import os
import re
import secrets
import subprocess
import sys
import time
from datetime import date, datetime, time as day_time, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CREDENTIALS = ROOT / "secrets/phase11/credentials.json"
DEFAULT_STATE = ROOT / "secrets/phase11/seed-state.json"
ROLE_SET = {
    "patient",
    "doctor",
    "receptionist",
    "pharmacist",
    "billing_staff",
    "emergency_staff",
    "hospital_admin",
    "ops",
}

PATIENT_NAMES = [
    "Arjun Mehta", "Aarav Sharma", "Ishita Iyer", "Rohan Kapoor",
    "Meera Nair", "Kabir Menon", "Ananya Das", "Dev Malhotra",
    "Sana Qureshi", "Vihaan Rao", "Aditi Kulkarni", "Neil Chawla",
    "Kavya Reddy", "Rehan Siddiqui", "Tara Banerjee", "Ishan Bhat",
    "Maya Fernandes", "Aditya Pillai", "Zoya Khan", "Karan Sethi",
    "Nisha Thomas", "Yash Verma", "Diya Mukherjee", "Sameer Joshi",
    "Riya Sen", "Manav Desai", "Leela Krishnan", "Farhan Ali",
    "Pooja Shetty", "Ritvik Ghosh", "Anika Bose", "Siddharth Jain",
    "Saira Merchant", "Omkar Patil", "Nandini Rao", "Ayaan D'Souza",
    "Bhavna Shah", "Harish Kumar", "Lavanya Roy", "Imran Ansari",
]

DOCTORS = [
    ("Dr. Ananya Rao", "Cardiology"),
    ("Dr. Vikram Shah", "General Medicine"),
    ("Dr. Priya Nair", "Pediatrics"),
    ("Dr. Arjun Iyer", "Orthopaedics"),
    ("Dr. Sneha Kulkarni", "Dermatology"),
    ("Dr. Rahul Menon", "Ophthalmology"),
    ("Dr. Kavita Reddy", "Obstetrics and Gynaecology"),
    ("Dr. Sameer Khan", "Neurology"),
    ("Dr. Meera Das", "ENT"),
    ("Dr. Aditya Bose", "Gastroenterology"),
    ("Dr. Neha Kapoor", "Endocrinology"),
    ("Dr. Kiran Thomas", "Nephrology"),
    ("Dr. Farah Siddiqui", "Pulmonology"),
    ("Dr. Rohan Malhotra", "Urology"),
    ("Dr. Aditi Sharma", "Psychiatry"),
    ("Dr. Nikhil Joshi", "Dentistry"),
    ("Dr. Pooja Menon", "Oncology"),
    ("Dr. Sandeep Patil", "Radiology"),
    ("Dr. Leela Krishnan", "Rheumatology"),
    ("Dr. Imran Qureshi", "Emergency Medicine"),
]

MEDICINES = [
    "Paracetamol 500 mg tablet", "Paracetamol 650 mg tablet",
    "Ibuprofen 200 mg tablet", "Ibuprofen 400 mg tablet",
    "Naproxen 250 mg tablet", "Diclofenac 50 mg tablet",
    "Aspirin 75 mg tablet", "Amoxicillin 500 mg capsule",
    "Azithromycin 500 mg tablet", "Amoxicillin-clavulanate 625 mg tablet",
    "Cefixime 200 mg tablet", "Cefuroxime 500 mg tablet",
    "Ciprofloxacin 500 mg tablet", "Doxycycline 100 mg capsule",
    "Metronidazole 400 mg tablet", "Pantoprazole 40 mg tablet",
    "Omeprazole 20 mg capsule", "Famotidine 20 mg tablet",
    "Ondansetron 4 mg tablet", "Domperidone 10 mg tablet",
    "Cetirizine 10 mg tablet", "Loratadine 10 mg tablet",
    "Fexofenadine 120 mg tablet", "Levocetirizine 5 mg tablet",
    "Salbutamol 100 mcg inhaler", "Budesonide 200 mcg inhaler",
    "Montelukast 10 mg tablet", "Metformin 500 mg tablet",
    "Metformin 850 mg tablet", "Glimepiride 1 mg tablet",
    "Atorvastatin 10 mg tablet", "Atorvastatin 20 mg tablet",
    "Amlodipine 5 mg tablet", "Losartan 50 mg tablet",
    "Telmisartan 40 mg tablet", "Metoprolol 25 mg tablet",
    "Enalapril 5 mg tablet", "Hydrochlorothiazide 12.5 mg tablet",
    "Levothyroxine 50 mcg tablet", "Cholecalciferol 60000 IU capsule",
    "Calcium carbonate 500 mg tablet", "Ferrous sulfate 200 mg tablet",
    "Folic acid 5 mg tablet", "Oral rehydration salts sachet",
    "Zinc sulfate 20 mg tablet", "Hydrocortisone 1% cream",
    "Clotrimazole 1% cream", "Mupirocin 2% ointment",
    "Povidone-iodine 5% solution", "Dextromethorphan 15 mg/5 mL syrup",
]

LOCAL_ROLES = [
    "patient", "doctor", "receptionist", "pharmacist", "billing_staff",
    "emergency_staff", "hospital_admin", "ops",
]


def persist(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(state, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
    os.chmod(path, 0o600)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def key_for(state: dict, label: str) -> str:
    return str(uuid5(UUID(state["run_id"]), label))


def require(response: httpx.Response, expected: tuple[int, ...]) -> dict | None:
    if response.status_code not in expected:
        try:
            error = response.json().get("error", {}).get("code", "unknown")
        except (ValueError, AttributeError):
            error = "non_json"
        raise RuntimeError(
            f"{response.request.method} {response.request.url.path} returned "
            f"{response.status_code} ({error}); expected {expected}"
        )
    return response.json() if response.status_code != 204 else None


class Actor:
    def __init__(self, base_url: str, origin: str, data: dict, label: str):
        self.base_url = base_url.rstrip("/")
        self.data = data
        self.label = label
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"Origin": origin},
            timeout=httpx.Timeout(20, connect=8),
            trust_env=False,
        )
        self.token: str | None = None

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, *, json_body=None, headers=None):
        retries = 0
        while True:
            response = self.client.request(
                method, path, json=json_body, headers=headers
            )
            if response.status_code != 429 or retries >= 8:
                return response
            retry_after = response.headers.get("Retry-After", "1")
            try:
                delay = max(1, min(60, int(retry_after)))
            except ValueError:
                delay = 1
            print(f"Admission limited; honoring a {delay}s retry deadline.", flush=True)
            time.sleep(delay)
            retries += 1

    def register(self, state: dict, state_path: Path) -> dict:
        if self.data.get("profile"):
            return self.data["profile"]
        csrf = require(self._request("GET", "/api/v1/auth/csrf"), (200,))
        response = self._request(
            "POST",
            "/api/v1/auth/register",
            json_body=self.data["registration"],
            headers={
                "X-CSRF-Token": csrf["csrf_token"],
                "Idempotency-Key": key_for(state, f"register:{self.label}"),
                "X-Anonymous-Command-ID": self.data["anonymous_command_id"],
            },
        )
        self.data["profile"] = require(response, (201,))
        persist(state_path, state)
        return self.data["profile"]

    def login(self) -> None:
        csrf = require(self._request("GET", "/api/v1/auth/csrf"), (200,))
        response = self._request(
            "POST",
            "/api/v1/auth/login",
            json_body={"email": self.data["email"], "password": self.data["password"]},
            headers={"X-CSRF-Token": csrf["csrf_token"]},
        )
        self.token = require(response, (200,))["access_token"]

    def call(
        self,
        method: str,
        path: str,
        body=None,
        *,
        etag: str | None = None,
        key: str | None = None,
        expected: tuple[int, ...] = (200,),
        params: dict | None = None,
    ):
        headers = {}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        if etag is not None:
            headers["If-Match"] = etag
        if key is not None:
            headers["Idempotency-Key"] = key
        response = self._request(
            method,
            path,
            json_body=body,
            headers=headers,
        ) if params is None else self._request_with_params(
            method, path, body, headers, params
        )
        data = require(response, expected)
        return data, response.headers.get("ETag"), response.status_code

    def _request_with_params(self, method, path, body, headers, params):
        retries = 0
        while True:
            response = self.client.request(
                method, path, params=params, json=body, headers=headers
            )
            if response.status_code != 429 or retries >= 8:
                return response
            try:
                delay = max(1, min(60, int(response.headers.get("Retry-After", "1"))))
            except ValueError:
                delay = 1
            print(f"Admission limited; honoring a {delay}s retry deadline.", flush=True)
            time.sleep(delay)
            retries += 1


def actor_for(base: str, origin: str, state: dict, label: str) -> Actor:
    return Actor(base, origin, state["actors"][label], label)


def register_actor(
    base: str,
    origin: str,
    state: dict,
    state_path: Path,
    label: str,
    email: str,
    display_name: str,
    password: str,
    birth_date: date | None = None,
) -> Actor:
    data = state["actors"].get(label)
    if data is None:
        registration = {
            "email": email,
            "password": password,
            "display_name": display_name,
        }
        if birth_date:
            registration["date_of_birth"] = birth_date.isoformat()
        data = {
            "email": email,
            "password": password,
            "registration": registration,
            "anonymous_command_id": secrets.token_urlsafe(32),
        }
        state["actors"][label] = data
        persist(state_path, state)
    elif data["email"] != email or data["registration"]["display_name"] != display_name:
        raise RuntimeError(f"Persisted actor definition changed for {label}")
    actor = actor_for(base, origin, state, label)
    actor.register(state, state_path)
    return actor


def command(
    state: dict,
    state_path: Path,
    label: str,
    actor: Actor,
    method: str,
    path: str,
    body: dict,
    *,
    etag: str | None = None,
    expected: tuple[int, ...] = (201,),
):
    resources = state["resources"]
    if label not in resources:
        requests = state.setdefault("command_requests", {})
        intent = requests.get(label)
        if intent is None:
            intent = {
                "method": method,
                "path": path,
                "body": body,
                "etag": etag,
            }
            requests[label] = intent
            persist(state_path, state)
        elif intent["method"] != method or intent["path"] != path:
            raise RuntimeError(f"Persisted command intent changed route for {label}.")
        result = actor.call(
            intent["method"],
            intent["path"],
            intent["body"],
            etag=intent["etag"],
            key=key_for(state, f"command:{label}"),
            expected=expected,
        )[0]
        resources[label] = result
        persist(state_path, state)
    return resources[label]


def set_roles(admin: Actor, actor: Actor, state: dict, state_path: Path, roles: list[str]):
    current, etag, _ = admin.call(
        "GET", f"/api/v1/patients/users/{actor.data['profile']['user_id']}"
    )
    if sorted(current["roles"]) != sorted(roles):
        updated = admin.call(
            "PATCH",
            f"/api/v1/patients/users/{current['id']}/roles",
            {"roles": roles},
            etag=etag,
        )[0]
        actor.data["roles"] = updated["roles"]
        persist(state_path, state)


def local_first_admin(email: str, port: int) -> None:
    env_path = ROOT / ".env"
    for line in env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value.strip().strip('"').strip("'"))
    sys.path.insert(0, str(ROOT / "services/patient"))
    from patient_service.bootstrap_admin import bootstrap_first_admin
    from patient_service.settings import Settings

    settings = Settings(
        environment="development",
        db_host="127.0.0.1",
        db_port=port,
        db_name="patient_db",
        db_user="patient_app",
        db_password=os.environ["PATIENT_DB_PASSWORD"],
    )
    bootstrap_first_admin(email, settings)


def verify_local_target(base: str, origin: str) -> None:
    parsed = urlparse(base)
    if parsed.port != 8080:
        raise RuntimeError("The selected local seed target must be the pulsegrid gateway on port 8080.")
    labels_text = subprocess.run(
        ["docker", "inspect", "--format", "{{json .Config.Labels}}", "pulsegrid-traefik-1"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    labels = json.loads(labels_text)
    if (
        labels.get("com.docker.compose.project") != "pulsegrid"
        or labels.get("com.docker.compose.project.working_dir") != str(ROOT)
    ):
        raise RuntimeError("Gateway labels do not identify the selected pulsegrid project and checkout.")
    marker_path = ROOT / "secrets/phase11/rebuild-ready.json"
    if not marker_path.is_file():
        raise RuntimeError("The guarded rebuild has not marked this database ready for seeding.")
    marker = json.loads(marker_path.read_text())
    if marker.get("project") != "pulsegrid" or marker.get("status") not in {"ready", "seeded"}:
        raise RuntimeError("The private rebuild marker does not authorize this seed target.")
    volume_created = subprocess.run(
        ["docker", "volume", "inspect", "--format", "{{.CreatedAt}}", "pulsegrid_postgres_data"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if marker.get("postgres_volume_created_at") != volume_created:
        raise RuntimeError("The active PostgreSQL volume does not match the clean rebuild marker.")
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            env[key] = value.strip().strip('"').strip("'")
    origins = {value.strip() for value in env.get("AUTH_ORIGINS", "").split(",") if value.strip()}
    if env.get("APP_ENVIRONMENT") != "development" or env.get("GATEWAY_PORT") != "8080":
        raise RuntimeError("The local target marker is missing or does not match the selected gateway.")
    if origin not in origins:
        raise RuntimeError("The browser origin is not listed in the local Patient auth allowlist.")


def next_weekday(value: date) -> date:
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def next_half_hour(value: datetime) -> datetime:
    value = value.replace(second=0, microsecond=0)
    minute = 30 if value.minute < 30 else 60
    if minute == 60:
        value = value.replace(minute=0) + timedelta(hours=1)
    else:
        value = value.replace(minute=30)
    return value


def load_people(state, base, origin, state_path, credentials_path, shared_password):
    actors = {}
    accounts = load_json(credentials_path)["accounts"]
    for index, spec in enumerate(accounts):
        label = f"login:{spec['role']}"
        password = spec.get("password") or shared_password
        birth = date(1978 + index % 20, 1 + index % 12, 10 + index % 17)
        actors[label] = register_actor(
            base, origin, state, state_path, label, spec["email"],
            spec["display_name"], password, birth,
        )
    return actors


def seed(base: str, origin: str, state_path: Path, credentials_path: Path, db_port: int):
    credentials = load_json(credentials_path)
    if credentials.get("environment") != "local-demo-only":
        raise RuntimeError("This run is local-only and requires local demo credentials.")
    shared_password = credentials.get("password", "")
    if len(shared_password) < 12:
        raise RuntimeError("The private local demo credential is incomplete.")
    parsed = urlparse(base)
    origin_parsed = urlparse(origin)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The default seed command accepts loopback HTTP targets only.")
    if origin_parsed.scheme != "http" or origin_parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The local browser origin must be loopback HTTP.")
    verify_local_target(base, origin)
    if not state_path.exists():
        marker = load_json(ROOT / "secrets/phase11/rebuild-ready.json")
        if marker.get("status") == "seeded":
            raise RuntimeError("The clean target has already been seeded; rebuild it before starting a new run.")
        ready = httpx.get(
            base.rstrip("/") + "/api/v1/patients/health/ready",
            timeout=5,
            trust_env=False,
        )
        require(ready, (200,))
        state = {
            "run_id": str(uuid4()),
            "target": base.rstrip("/"),
            "actors": {},
            "resources": {},
            "complete": False,
        }
        persist(state_path, state)
    else:
        state = load_json(state_path)
        if state.get("target") != base.rstrip("/"):
            raise RuntimeError("Private seed state belongs to a different API target.")
        if state.get("complete"):
            print("The saved local demo seed is already complete; no API writes were made.")
            return

    # The initial administrator is provisioned only through the existing
    # local-only Patient bootstrap function after loopback PostgreSQL exposure.
    bootstrap_label = "bootstrap:first-admin"
    bootstrap_email = "phase11-bootstrap@pulsegrid.demo.test"
    bootstrap_actor = register_actor(
        base, origin, state, state_path, bootstrap_label,
        bootstrap_email, "PulseGrid Setup Administrator", shared_password,
    )
    login_actors = None
    if not state.get("bootstrap_complete"):
        try:
            local_first_admin(bootstrap_email, db_port)
        except ValueError as error:
            if "active hospital administrator already exists" not in str(error):
                raise
            bootstrap_actor.login()
            user, _, _ = bootstrap_actor.call(
                "GET", f"/api/v1/patients/users/{bootstrap_actor.data['profile']['user_id']}"
            )
            if "hospital_admin" not in user["roles"]:
                raise RuntimeError("A different active administrator exists on the target.")
        state["bootstrap_complete"] = True
        persist(state_path, state)
    if state.get("bootstrap_disabled"):
        login_actors = load_people(
            state, base, origin, state_path, credentials_path, shared_password
        )
        admin = login_actors["login:hospital_admin"]
        admin.login()
    else:
        bootstrap_actor.login()
        admin = bootstrap_actor

    if not state.get("baseline_verified"):
        users_page, _, _ = admin.call(
            "GET", "/api/v1/patients/users", params={"state": "active", "limit": "100"}
        )
        patients_page, _, _ = admin.call(
            "GET", "/api/v1/patients", params={"limit": "100"}
        )
        doctors_page, _, _ = bootstrap_actor.call(
            "GET", "/api/v1/doctors", params={"active": "true", "limit": "100"}
        )
        patient_id = bootstrap_actor.data["profile"]["id"]
        appointments_page, _, _ = bootstrap_actor.call(
            "GET", "/api/v1/appointments", params={"limit": "100"}
        )
        consultations_page, _, _ = bootstrap_actor.call(
            "GET", "/api/v1/records/consultations", params={"limit": "100", "patient_id": patient_id}
        )
        medicines_page, _, _ = bootstrap_actor.call(
            "GET", "/api/v1/pharmacy/medicines", params={"limit": "100"}
        )
        invoices_page, _, _ = bootstrap_actor.call(
            "GET", "/api/v1/billing/invoices", params={"limit": "100", "patient_id": patient_id}
        )
        emergencies_page, _, _ = bootstrap_actor.call(
            "GET", "/api/v1/emergencies", params={"limit": "100"}
        )
        if (
            len(users_page["items"]) != 1
            or users_page["items"][0]["email"] != bootstrap_email
            or len(patients_page["items"]) != 1
            or patients_page["items"][0]["id"] != patient_id
            or any(page["items"] for page in (
                doctors_page, appointments_page, consultations_page,
                medicines_page, invoices_page, emergencies_page,
            ))
        ):
            raise RuntimeError("The selected target is not a clean, newly migrated hospital database.")
        state["baseline_verified"] = True
        persist(state_path, state)

    if login_actors is None:
        login_actors = load_people(
            state, base, origin, state_path, credentials_path, shared_password
        )
    for role, actor in login_actors.items():
        set_roles(admin, actor, state, state_path, [actor.label.split(":", 1)[1]])

    patient_actors = [login_actors["login:patient"]]
    for index, name in enumerate(PATIENT_NAMES[1:], start=1):
        label = f"patient:{index + 1:02d}"
        birth = date(1958 + (index * 7) % 42, 1 + (index * 5) % 12, 1 + (index * 11) % 27)
        actor = register_actor(
            base, origin, state, state_path, label,
            f"patient{index + 1:02d}@pulsegrid.demo.test", name,
            state["actors"].get(label, {}).get("password") or secrets.token_urlsafe(32),
            birth,
        )
        patient_actors.append(actor)

    doctor_actors = [login_actors["login:doctor"]]
    for index, (name, _) in enumerate(DOCTORS[1:], start=1):
        label = f"doctor:{index + 1:02d}"
        actor = register_actor(
            base, origin, state, state_path, label,
            f"doctor{index + 1:02d}@pulsegrid.demo.test", name,
            state["actors"].get(label, {}).get("password") or secrets.token_urlsafe(32),
            date(1965 + index % 30, 2 + index % 10, 3 + index % 25),
        )
        doctor_actors.append(actor)

    print("Registered the eight intended accounts and the patient/doctor directory identities.", flush=True)
    for actor in doctor_actors[1:]:
        set_roles(admin, actor, state, state_path, ["doctor"])
    for actor in login_actors.values():
        actor.login()
    for actor in doctor_actors:
        if actor.token is None:
            actor.login()
    for actor in patient_actors:
        if actor.token is None:
            actor.login()

    specialties = []
    doctors = []
    for index, ((display_name, specialty_name), actor) in enumerate(zip(DOCTORS, doctor_actors)):
        slug = re.sub(r"[^a-z0-9]+", "-", specialty_name.lower()).strip("-")
        specialty = command(
            state, state_path, f"specialty:{index + 1:02d}", admin, "POST",
            "/api/v1/doctors/specialties", {"slug": slug, "name": specialty_name},
        )
        specialties.append(specialty)
        doctor_profile = command(
            state, state_path, f"doctor-profile:{index + 1:02d}", admin, "POST",
            "/api/v1/doctors",
            {
                "staff_user_id": actor.data["profile"]["user_id"],
                "display_name": display_name,
                "specialty_ids": [specialty["id"]],
            },
        )
        doctors.append(doctor_profile)

    print("Creating 20 accepted doctor schedules and 40 patient appointments.", flush=True)
    local_tz = ZoneInfo("Asia/Kolkata")
    near_start = next_half_hour(datetime.now(local_tz) + timedelta(minutes=50))
    future_day_1 = next_weekday(date.today() + timedelta(days=2))
    future_day_2 = next_weekday(future_day_1 + timedelta(days=1))
    schedules = []
    for index, (doctor, actor) in enumerate(zip(doctors, doctor_actors)):
        if index == 0:
            blocks = [
                (near_start, timedelta(hours=1)),
                (datetime.combine(future_day_1, day_time(9, 0), local_tz), timedelta(hours=10)),
                (datetime.combine(future_day_2, day_time(9, 0), local_tz), timedelta(hours=9)),
            ]
        else:
            blocks = [
                (datetime.combine(future_day_1, day_time(9, 0), local_tz), timedelta(hours=1)),
                (datetime.combine(future_day_2, day_time(9, 0), local_tz), timedelta(hours=1)),
            ]
        intervals = [
            {
                "starts_at": start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                "ends_at": (start + duration).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            for start, duration in blocks
        ]
        _, doctor_etag, _ = actor.call("GET", f"/api/v1/doctors/{doctor['id']}")
        proposal = command(
            state, state_path, f"schedule-proposal:{index + 1:02d}", actor, "POST",
            f"/api/v1/doctors/{doctor['id']}/schedules",
            {"timezone": "Asia/Kolkata", "slot_minutes": 30, "intervals": intervals, "expected_revision": 0},
            etag=doctor_etag, expected=(202,),
        )
        intervals = proposal["intervals"]
        command(
            state, state_path, f"schedule-decision:{index + 1:02d}", actor, "POST",
            "/api/v1/appointments/schedule-decisions",
            {"doctor_id": doctor["id"], "proposal_id": proposal["id"], "expected_accepted_revision": 0},
        )
        current, proposal_etag, _ = actor.call(
            "GET", f"/api/v1/doctors/{doctor['id']}/schedules/{proposal['id']}"
        )
        if current["status"] == "pending":
            command(
                state, state_path, f"schedule-reconcile:{index + 1:02d}", actor, "POST",
                f"/api/v1/doctors/{doctor['id']}/schedules/{proposal['id']}/reconcile",
                {}, etag=proposal_etag, expected=(200,),
            )
        schedules.append({"doctor": doctor, "proposal": proposal, "intervals": intervals})

    appointments = []
    for patient_index, patient in enumerate(patient_actors):
        doctor_index = 0
        appointment_key = f"appointment:{patient_index + 1:02d}"
        appointment = state["resources"].get(appointment_key)
        if appointment is None:
            if patient_index < 2:
                interval_index = 0
            elif patient_index < 22:
                interval_index = 1
            else:
                interval_index = 2
            interval = schedules[doctor_index]["intervals"][interval_index]
            availability = None
            for attempt in range(15):
                availability, _, _ = patient.call(
                    "GET", "/api/v1/appointments/availability",
                    params={
                        "doctor_id": schedules[doctor_index]["doctor"]["id"],
                        "from": interval["starts_at"],
                        "to": interval["ends_at"],
                    },
                )
                if availability["slots"]:
                    break
                time.sleep(1)
            else:
                raise RuntimeError(
                    f"Accepted schedule interval {interval_index + 1} has no remaining slots for "
                    f"missing patient appointment {patient_index + 1}."
                )
            # Use a currently open slot. This remains safe when resuming after
            # a partial run, where some earlier slots may already be booked.
            appointment = command(
                state, state_path, appointment_key, patient, "POST",
                "/api/v1/appointments",
                {
                    "patient_id": patient.data["profile"]["id"],
                    "slot_id": availability["slots"][0]["id"],
                    "expected_schedule_revision": availability["accepted_revision"],
                },
            )
        appointments.append({"appointment": appointment, "patient": patient, "doctor": doctor_actors[doctor_index], "doctor_profile": doctors[doctor_index]})

    pharmacist = login_actors["login:pharmacist"]
    medicine_profiles = []
    for index, name in enumerate(MEDICINES):
        medicine = command(
            state, state_path, f"medicine:{index + 1:02d}", pharmacist, "POST",
            "/api/v1/pharmacy/medicines",
            {"sku": f"PG-DEMO-{index + 1:03d}", "name": name},
        )
        medicine_profiles.append(medicine)
        command(
            state, state_path, f"stock:{index + 1:02d}", pharmacist, "POST",
            "/api/v1/pharmacy/inventory-adjustments",
            {
                "medicine_id": medicine["id"],
                "batch_code": f"PG26-{index + 1:03d}",
                "expires_on": (date.today() + timedelta(days=540)).isoformat(),
                "delta": 100,
                "reason": "Opening demonstration inventory",
                "expected_batch_version": 0,
            },
        )
    print("Created 50 generic medicine catalog entries with owner-controlled stock.", flush=True)

    # One check-in/queue/consultation journey, three further consultation
    # histories, prescriptions, pharmacy outcomes, and invoice/payment states.
    receptionist = login_actors["login:receptionist"]
    billing = login_actors["login:billing_staff"]
    patient_zero = patient_actors[0]
    appointment_zero = appointments[0]
    # Move the first booked visit into the current 30-minute check-in window.
    # The original near-term schedule was accepted before the catalog seed and
    # its check-in window may still be closed by the time setup reaches here.
    # This uses the ordinary Doctor proposal, Appointment acceptance, and
    # patient reschedule APIs; it does not bypass the operational window.
    if state.get("checkin_window_ready"):
        appointment_zero["appointment"] = state["resources"]["appointment:01"]
        appointments[0]["appointment"] = appointment_zero["appointment"]
    else:
        doctor_id = appointment_zero["doctor_profile"]["id"]
        accepted_schedules = [
            value
            for key, value in state["resources"].items()
            if key.startswith("schedule-reconcile:")
            and value.get("doctor_id") == doctor_id
            and value.get("status") == "accepted"
        ]
        if not accepted_schedules:
            raise RuntimeError("No accepted doctor schedule is checkpointed for the check-in journey.")
        base_schedule = max(accepted_schedules, key=lambda item: item["revision"])
        repair_proposals = [
            (int(key.rsplit(":", 1)[1]), key, value)
            for key, value in state["resources"].items()
            if key.startswith("schedule-proposal:checkin-window-repair:")
            and value.get("doctor_id") == doctor_id
        ]
        if repair_proposals:
            repair_revision, proposal_key, checkin_proposal = max(repair_proposals)
        else:
            all_doctor_proposals = [
                value.get("revision", 0)
                for key, value in state["resources"].items()
                if key.startswith("schedule-proposal:")
                and value.get("doctor_id") == doctor_id
            ]
            latest_revision = max(all_doctor_proposals, default=base_schedule["revision"])
            accepted_revision = max(item["revision"] for item in accepted_schedules)
            existing_intervals = [
                {
                    "starts_at": item["starts_at"],
                    "ends_at": item["ends_at"],
                }
                for item in base_schedule["intervals"]
            ]
            near_start = next_half_hour(datetime.now(timezone.utc) + timedelta(minutes=10))
            while any(
                datetime.fromisoformat(item["starts_at"].replace("Z", "+00:00"))
                < near_start + timedelta(minutes=30)
                and datetime.fromisoformat(item["ends_at"].replace("Z", "+00:00"))
                > near_start
                for item in existing_intervals
            ):
                latest_end = max(
                    datetime.fromisoformat(item["ends_at"].replace("Z", "+00:00"))
                    for item in existing_intervals
                )
                near_start = next_half_hour(latest_end + timedelta(minutes=1))
            proposed_intervals = [
                *existing_intervals,
                {
                    "starts_at": near_start.isoformat().replace("+00:00", "Z"),
                    "ends_at": (near_start + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
                },
            ]
            proposed_intervals.sort(key=lambda item: item["starts_at"])
            _, doctor_etag, _ = appointment_zero["doctor"].call(
                "GET", f"/api/v1/doctors/{doctor_id}"
            )
            repair_revision = latest_revision + 1
            proposal_key = f"schedule-proposal:checkin-window-repair:{repair_revision}"
            checkin_proposal = command(
                state, state_path, proposal_key, appointment_zero["doctor"], "POST",
                f"/api/v1/doctors/{doctor_id}/schedules",
                {
                    "timezone": "Asia/Kolkata",
                    "slot_minutes": 30,
                    "intervals": proposed_intervals,
                    "expected_revision": latest_revision,
                },
                etag=doctor_etag,
                expected=(202,),
            )
            command(
                state, state_path, f"schedule-decision:checkin-window-repair:{repair_revision}", appointment_zero["doctor"], "POST",
                "/api/v1/appointments/schedule-decisions",
                {"doctor_id": doctor_id, "proposal_id": checkin_proposal["id"], "expected_accepted_revision": accepted_revision},
            )
        current_proposal, proposal_etag, _ = appointment_zero["doctor"].call(
            "GET", f"/api/v1/doctors/{doctor_id}/schedules/{checkin_proposal['id']}"
        )
        if current_proposal["status"] == "pending":
            command(
                state, state_path, f"schedule-reconcile:checkin-window-repair:{repair_revision}", appointment_zero["doctor"], "POST",
                f"/api/v1/doctors/{doctor_id}/schedules/{checkin_proposal['id']}/reconcile",
                {}, etag=proposal_etag, expected=(200,),
            )
        for attempt in range(15):
            checkin_availability, _, _ = patient_zero.call(
                "GET", "/api/v1/appointments/availability",
                params={"doctor_id": appointment_zero["doctor_profile"]["id"], "from": checkin_proposal["intervals"][0]["starts_at"], "to": checkin_proposal["intervals"][0]["ends_at"]},
            )
            if checkin_availability["slots"]:
                break
            time.sleep(1)
        else:
            raise RuntimeError("The accepted check-in schedule did not project a bookable slot.")
        _, appointment_etag, _ = patient_zero.call(
            "GET", f"/api/v1/appointments/{appointment_zero['appointment']['id']}"
        )
        rescheduled = command(
            state, state_path, "checkin-slot-reschedule", patient_zero, "POST",
            f"/api/v1/appointments/{appointment_zero['appointment']['id']}/reschedule",
            {"target_slot_id": checkin_availability["slots"][0]["id"], "expected_schedule_revision": checkin_availability["accepted_revision"]},
            etag=appointment_etag, expected=(200,),
        )
        appointment_zero["appointment"] = rescheduled
        appointments[0]["appointment"] = rescheduled
        state["resources"]["appointment:01"] = rescheduled
        state["checkin_window_ready"] = True
        persist(state_path, state)
    _, workflow_etag, _ = patient_zero.call(
        "GET", f"/api/v1/appointments/{appointment_zero['appointment']['id']}/workflow"
    )
    checkin = command(
        state, state_path, "staff-check-in:02", receptionist, "POST",
        f"/api/v1/appointments/{appointment_zero['appointment']['id']}/staff-check-in",
        {"reason": "Arrival confirmed for the fictional demonstration"},
        etag=workflow_etag, expected=(200,),
    )
    queue_entry = checkin["queue_entry"]
    queue_result = command(
        state, state_path, "queue-start:01", appointment_zero["doctor"], "POST",
        f"/api/v1/appointments/queue-entries/{queue_entry['id']}/start", {},
        etag=f'"{queue_entry["version"]}"', expected=(200,),
    )

    visit_appointments = [appointment_zero]
    near_visit_start = datetime.fromisoformat(
        appointment_zero["appointment"]["starts_at"].replace("Z", "+00:00")
    )
    for doctor_index, patient_index in ((1, 1), (2, 2), (3, 3)):
        doctor = doctors[doctor_index]
        doctor_actor = doctor_actors[doctor_index]
        patient = patient_actors[patient_index]
        appointment_key = f"consult-appointment:{doctor_index + 1:02d}"
        appointment = state["resources"].get(appointment_key)
        accepted_schedules = [
            value
            for key, value in state["resources"].items()
            if key.startswith("schedule-reconcile:")
            and value.get("doctor_id") == doctor["id"]
            and value.get("status") == "accepted"
        ]
        if not accepted_schedules:
            raise RuntimeError(f"No accepted schedule is checkpointed for doctor {doctor_index + 1}.")
        base_schedule = max(accepted_schedules, key=lambda item: item["revision"])
        proposal_key = f"schedule-proposal:consult-window:{doctor_index + 1:02d}"
        proposal = state["resources"].get(proposal_key)
        if proposal is None:
            all_doctor_proposals = [
                value.get("revision", 0)
                for key, value in state["resources"].items()
                if key.startswith("schedule-proposal:")
                and value.get("doctor_id") == doctor["id"]
            ]
            latest_revision = max(all_doctor_proposals, default=base_schedule["revision"])
            accepted_revision = max(item["revision"] for item in accepted_schedules)
            intervals = [
                {"starts_at": item["starts_at"], "ends_at": item["ends_at"]}
                for item in base_schedule["intervals"]
            ]
            intervals.append({
                "starts_at": near_visit_start.isoformat().replace("+00:00", "Z"),
                "ends_at": (near_visit_start + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            })
            intervals.sort(key=lambda item: item["starts_at"])
            _, doctor_etag, _ = doctor_actor.call("GET", f"/api/v1/doctors/{doctor['id']}")
            proposal = command(
                state, state_path, proposal_key, doctor_actor, "POST",
                f"/api/v1/doctors/{doctor['id']}/schedules",
                {
                    "timezone": "Asia/Kolkata",
                    "slot_minutes": 30,
                    "intervals": intervals,
                    "expected_revision": latest_revision,
                },
                etag=doctor_etag,
                expected=(202,),
            )
            command(
                state, state_path, f"schedule-decision:consult-window:{doctor_index + 1:02d}", doctor_actor, "POST",
                "/api/v1/appointments/schedule-decisions",
                {"doctor_id": doctor["id"], "proposal_id": proposal["id"], "expected_accepted_revision": accepted_revision},
            )
        else:
            accepted_revision = max(item["revision"] for item in accepted_schedules)
            command(
                state, state_path, f"schedule-decision:consult-window:{doctor_index + 1:02d}", doctor_actor, "POST",
                "/api/v1/appointments/schedule-decisions",
                {"doctor_id": doctor["id"], "proposal_id": proposal["id"], "expected_accepted_revision": accepted_revision},
            )
        current_proposal, proposal_etag, _ = doctor_actor.call(
            "GET", f"/api/v1/doctors/{doctor['id']}/schedules/{proposal['id']}"
        )
        if current_proposal["status"] == "pending":
            command(
                state, state_path, f"schedule-reconcile:consult-window:{doctor_index + 1:02d}", doctor_actor, "POST",
                f"/api/v1/doctors/{doctor['id']}/schedules/{proposal['id']}/reconcile",
                {}, etag=proposal_etag, expected=(200,),
            )
        if appointment is None:
            # The inserted interval may sort after old future intervals. Query
            # its exact accepted range to avoid relying on proposal ordering.
            near_interval = next(
                item for item in proposal["intervals"]
                if datetime.fromisoformat(item["starts_at"].replace("Z", "+00:00")) == near_visit_start
            )
            availability, _, _ = patient.call(
                "GET", "/api/v1/appointments/availability",
                params={"doctor_id": doctor["id"], "from": near_interval["starts_at"], "to": near_interval["ends_at"]},
            )
            if not availability["slots"]:
                raise RuntimeError(f"Doctor {doctor_index + 1} has no projected consultation slot.")
            appointment = command(
                state, state_path, appointment_key, patient, "POST",
                "/api/v1/appointments",
                {"patient_id": patient.data["profile"]["id"], "slot_id": availability["slots"][0]["id"], "expected_schedule_revision": availability["accepted_revision"]},
            )
        _, workflow_etag, _ = patient.call(
            "GET", f"/api/v1/appointments/{appointment['id']}/workflow"
        )
        checkin = command(
            state, state_path, f"staff-check-in:consult:{doctor_index + 1:02d}", receptionist, "POST",
            f"/api/v1/appointments/{appointment['id']}/staff-check-in",
            {"reason": "Arrival confirmed for the fictional demonstration"},
            etag=workflow_etag, expected=(200,),
        )
        queue_entry = checkin["queue_entry"]
        command(
            state, state_path, f"queue-start:consult:{doctor_index + 1:02d}", doctor_actor, "POST",
            f"/api/v1/appointments/queue-entries/{queue_entry['id']}/start", {},
            etag=f'"{queue_entry["version"]}"', expected=(200,),
        )
        visit_appointments.append({
            "appointment": appointment,
            "patient": patient,
            "doctor": doctor_actor,
            "doctor_profile": doctor,
        })

    content = {
        "summary": "Routine outpatient review",
        "assessment": "Fictional demonstration entry; no real patient or clinical finding.",
        "plan": "Demonstration record only. Not clinical advice or a care recommendation.",
    }
    consultation_items = [
        [{"medicine_id": medicine_profiles[0]["id"], "quantity": 2, "dosage": "As directed by the fictional treating clinician.", "instructions": "Demonstration prescription only; not for clinical use."}],
        [],
        [{"medicine_id": medicine_profiles[1]["id"], "quantity": 1, "dosage": "As directed by the fictional treating clinician.", "instructions": "Demonstration prescription only; not for clinical use."}],
        [{"medicine_id": medicine_profiles[2]["id"], "quantity": 1, "dosage": "As directed by the fictional treating clinician.", "instructions": "Demonstration prescription only; not for clinical use."}],
    ]
    finalized = []
    for index, item in enumerate(visit_appointments):
        consultation = command(
            state, state_path, f"consultation:{index + 1:02d}", item["doctor"], "POST",
            "/api/v1/records/consultations",
            {"appointment_id": item["appointment"]["id"], "clinical_content": content},
        )
        _, consultation_etag, _ = item["doctor"].call(
            "GET", f"/api/v1/records/consultations/{consultation['id']}"
        )
        result = command(
            state, state_path, f"consultation-finalize:{index + 1:02d}", item["doctor"], "POST",
            f"/api/v1/records/consultations/{consultation['id']}/finalize",
            {"prescription_items": consultation_items[index]},
            etag=consultation_etag, expected=(200,),
        )
        finalized.append({**item, "consultation": consultation, "final": result})

    # Existing generic catalogue has fixed charges in INR minor units.
    command(
        state, state_path, "tariff:consultation", billing, "POST",
        "/api/v1/billing/tariffs",
        {"charge_code": "consultation", "unit_amount_minor": 12000, "currency": "INR"},
    )
    for index, medicine in enumerate(medicine_profiles):
        command(
            state, state_path, f"tariff:medicine:{index + 1:02d}", billing, "POST",
            "/api/v1/billing/tariffs",
            {"charge_code": f"medicine:{medicine['id']}", "unit_amount_minor": 500 + index % 5 * 100, "currency": "INR"},
        )

    dispenses = []
    for index in (0, 2):
        prescription = finalized[index]["final"]["prescription"]
        if not prescription:
            raise RuntimeError("Expected a prescription in the seeded consultation.")
        reservation = command(
            state, state_path, f"reservation:{index + 1:02d}", pharmacist, "POST",
            "/api/v1/pharmacy/reservations",
            {"prescription_id": prescription["id"], "items":[{"prescription_item_id": prescription["items"][0]["id"], "quantity": prescription["items"][0]["quantity"]}]},
        )
        if index == 0:
            dispenses.append(command(
                state, state_path, "dispense:01", pharmacist, "POST",
                f"/api/v1/pharmacy/reservations/{reservation['id']}/dispense", {},
                # Use the reservation's original version so a replay after a
                # successful-but-uncheckpointed response matches its first
                # idempotency fingerprint exactly.
                etag=f'"{reservation["version"]}"', expected=(201,),
            ))
        else:
            dispenses.append({"reservation": reservation, "state": "reserved"})

    invoice_results = []
    for index in range(3):
        item = finalized[index]
        invoice = command(
            state, state_path, f"invoice:{index + 1:02d}", billing, "POST",
            "/api/v1/billing/invoices",
            {"appointment_id": item["appointment"]["id"], "currency": "INR"},
        )
        _, invoice_etag, _ = billing.call(
            "GET", f"/api/v1/billing/invoices/{invoice['id']}"
        )
        dispensing_ids = [dispenses[0]["id"]] if index == 0 else []
        charged = command(
            state, state_path, f"invoice-import:{index + 1:02d}", billing, "POST",
            f"/api/v1/billing/invoices/{invoice['id']}/charges",
            {"consultation_id": item["consultation"]["id"], "dispensing_ids": dispensing_ids},
            etag=invoice_etag, expected=(200,),
        )
        invoice_results.append({"invoice": invoice, "charged": charged, "patient": item["patient"]})

    first = invoice_results[0]
    patient_invoice, payment_etag, _ = first["patient"].call(
        "GET", f"/api/v1/billing/invoices/{first['invoice']['id']}"
    )
    total = patient_invoice["total_minor"]
    command(
        state, state_path, "payment:declined", first["patient"], "POST",
        f"/api/v1/billing/invoices/{first['invoice']['id']}/payments",
        {"amount_minor": total, "currency": "INR", "simulated_outcome": "decline"},
        etag=payment_etag, expected=(201,),
    )
    current_invoice, payment_etag, _ = first["patient"].call(
        "GET", f"/api/v1/billing/invoices/{first['invoice']['id']}"
    )
    if current_invoice["paid_minor"] != 0:
        raise RuntimeError("Declined demo payment unexpectedly changed the invoice balance.")
    command(
        state, state_path, "payment:successful", first["patient"], "POST",
        f"/api/v1/billing/invoices/{first['invoice']['id']}/payments",
        {"amount_minor": total, "currency": "INR", "simulated_outcome": "success"},
        etag=payment_etag, expected=(201,),
    )
    second = invoice_results[1]
    second_patient_invoice, second_etag, _ = second["patient"].call(
        "GET", f"/api/v1/billing/invoices/{second['invoice']['id']}"
    )
    command(
        state, state_path, "payment:declined-only", second["patient"], "POST",
        f"/api/v1/billing/invoices/{second['invoice']['id']}/payments",
        {"amount_minor": second_patient_invoice["total_minor"], "currency": "INR", "simulated_outcome": "decline"},
        etag=second_etag, expected=(201,),
    )

    emergency_staff = login_actors["login:emergency_staff"]
    emergency_cases = []
    for index in range(3):
        case = command(
            state, state_path, f"emergency:{index + 1:02d}", patient_actors[index], "POST",
            "/api/v1/emergencies",
            {
                "patient_id": patient_actors[index].data["profile"]["id"],
                "description": "Fictional emergency department scenario for system demonstration; no dispatch is requested.",
                "reported_urgency": "urgent" if index < 2 else "unspecified",
            },
        )
        emergency_cases.append(case)
    if not state.get("emergency_complete"):
        active_case = emergency_cases[0]
        _, case_etag, _ = emergency_staff.call(
            "GET", f"/api/v1/emergencies/{active_case['id']}"
        )
        command(
            state, state_path, "emergency-priority:01", emergency_staff, "PATCH",
            f"/api/v1/emergencies/{active_case['id']}/priority",
            {"assigned_priority": 3, "reason": "Fictional department demonstration"},
            etag=case_etag, expected=(200,),
        )
        _, case_etag, _ = emergency_staff.call(
            "GET", f"/api/v1/emergencies/{active_case['id']}"
        )
        command(
            state, state_path, "emergency-claim:01", emergency_staff, "POST",
            f"/api/v1/emergencies/{active_case['id']}/claim", {},
            etag=case_etag, expected=(200,),
        )
        _, case_etag, _ = emergency_staff.call(
            "GET", f"/api/v1/emergencies/{active_case['id']}"
        )
        command(
            state, state_path, "emergency-processing:01", emergency_staff, "POST",
            f"/api/v1/emergencies/{active_case['id']}/transitions",
            {"state": "processing", "reason": "Fictional workflow demonstration"},
            etag=case_etag, expected=(200,),
        )
        state["emergency_complete"] = True
        persist(state_path, state)

    # Keep exactly the eight requested login accounts enabled. Patient and
    # Doctor owner records remain, while the other schema-required identities
    # are disabled through Patient's audited account-state API.
    admin = login_actors["login:hospital_admin"]
    active_labels = {f"login:{role}" for role in LOCAL_ROLES}
    # The local bootstrap identity starts with the Patient role by design;
    # remove it before disabling so it cannot appear as a hospital patient.
    set_roles(admin, bootstrap_actor, state, state_path, ["hospital_admin"])
    disabled = [label for label in state["actors"] if label not in active_labels]
    for label in disabled:
        data = state["actors"][label]
        if not data.get("profile"):
            raise RuntimeError(f"Cannot disable unregistered seed identity {label}.")
        user, user_etag, _ = admin.call(
            "GET", f"/api/v1/patients/users/{data['profile']['user_id']}"
        )
        if user["state"] == "active":
            admin.call(
                "PATCH",
                f"/api/v1/patients/users/{user['id']}/account-state",
                {"state": "disabled", "reason": "Non-login fictional demo directory identity"},
                etag=user_etag,
            )
        if label == bootstrap_label:
            state["bootstrap_disabled"] = True
        persist(state_path, state)

    active_users, _, _ = admin.call(
        "GET", "/api/v1/patients/users", params={"state": "active", "limit": "100"}
    )
    actual_accounts = {
        item["email"]: item["roles"] for item in active_users["items"]
    }
    intended = {item["email"]: [item["role"]] for item in credentials["accounts"]}
    if actual_accounts != intended:
        raise RuntimeError("The enabled account set differs from the eight intended role accounts.")

    patients_page, _, _ = login_actors["login:receptionist"].call(
        "GET", "/api/v1/patients", params={"limit": "100"}
    )
    doctors_page, _, _ = patient_zero.call(
        "GET", "/api/v1/doctors", params={"active": "true", "limit": "100"}
    )
    medicines_page, _, _ = pharmacist.call(
        "GET", "/api/v1/pharmacy/medicines", params={"limit": "100"}
    )
    if len(patients_page["items"]) != 40:
        raise RuntimeError(f"Patient directory contains {len(patients_page['items'])} patient-role profiles, expected 40.")
    if len(doctors_page["items"]) != 20:
        raise RuntimeError(f"Doctor directory contains {len(doctors_page['items'])} doctors, expected 20.")
    if len(medicines_page["items"]) != 50:
        raise RuntimeError(f"Pharmacy catalog contains {len(medicines_page['items'])} medicines, expected 50.")

    state["complete"] = True
    state["counts"] = {
        "active_login_accounts": 8,
        "disabled_schema_identity_accounts": len(disabled),
        "patients": len(patients_page["items"]),
        "doctors": len(doctors_page["items"]),
        "medicines": len(medicines_page["items"]),
        "appointments": len(appointments) + len(visit_appointments) - 1,
        "consultations": len(finalized),
        "prescriptions": sum(bool(x["final"]["prescription"]) for x in finalized),
        "emergency_cases": len(emergency_cases),
        "invoices": len(invoice_results),
    }
    for label in disabled:
        data = state["actors"][label]
        data.pop("password", None)
        data.pop("registration", None)
        data.pop("anonymous_command_id", None)
    persist(state_path, state)
    marker_path = ROOT / "secrets/phase11/rebuild-ready.json"
    marker = load_json(marker_path)
    marker["status"] = "seeded"
    marker["seeded_at_utc"] = datetime.now(timezone.utc).isoformat()
    persist(marker_path, marker)
    for actor in [*login_actors.values(), *patient_actors, *doctor_actors, bootstrap_actor]:
        actor.close()
    print(json.dumps({"status": "complete", "counts": state["counts"]}, indent=2), flush=True)


def verify_existing_demo(base: str, origin: str, state_path: Path, credentials_path: Path):
    credentials = load_json(credentials_path)
    if credentials.get("environment") != "local-demo-only" or len(credentials.get("password", "")) < 12:
        raise RuntimeError("Existing-demo verification requires the private local credential file.")
    parsed, origin_parsed = urlparse(base), urlparse(origin)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Existing-demo verification accepts the selected loopback target only.")
    if origin_parsed.scheme != "http" or origin_parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("The local browser origin must be loopback HTTP.")
    verify_local_target(base, origin)
    if not state_path.is_file():
        raise RuntimeError("Private local seed state is missing.")
    state = load_json(state_path)
    if state.get("target") != base.rstrip("/") or not state.get("complete"):
        raise RuntimeError("The private seed checkpoint does not describe a completed seed for this target.")
    marker = load_json(ROOT / "secrets/phase11/rebuild-ready.json")
    if marker.get("status") != "seeded":
        raise RuntimeError("The guarded rebuild marker does not describe a seeded database.")

    actors = {}
    for spec in credentials["accounts"]:
        label = f"login:{spec['role']}"
        data = state.get("actors", {}).get(label)
        if not data or not data.get("profile") or data.get("email") != spec["email"]:
            raise RuntimeError(f"The completed seed checkpoint lacks the intended {spec['role']} account.")
        actors[spec["role"]] = Actor(base, origin, data, label)
    try:
        for actor in actors.values():
            actor.login()
        users_page, _, _ = actors["hospital_admin"].call(
            "GET", "/api/v1/patients/users", params={"state": "active", "limit": "100"}
        )
        disabled_users_page, _, _ = actors["hospital_admin"].call(
            "GET", "/api/v1/patients/users", params={"state": "disabled", "limit": "100"}
        )
        actual_accounts = {item["email"]: item["roles"] for item in users_page["items"]}
        intended_accounts = {item["email"]: [item["role"]] for item in credentials["accounts"]}
        if actual_accounts != intended_accounts:
            raise RuntimeError("The post-restart enabled account set differs from the eight intended accounts.")

        patient_page, _, _ = actors["receptionist"].call(
            "GET", "/api/v1/patients", params={"limit": "100"}
        )
        doctor_page, _, _ = actors["patient"].call(
            "GET", "/api/v1/doctors", params={"active": "true", "limit": "100"}
        )
        appointment_page, _, _ = actors["receptionist"].call(
            "GET", "/api/v1/appointments", params={"limit": "100"}
        )
        medicine_page, _, _ = actors["pharmacist"].call(
            "GET", "/api/v1/pharmacy/medicines", params={"limit": "100"}
        )
        inventory_page, _, _ = actors["pharmacist"].call(
            "GET", "/api/v1/pharmacy/inventory", params={"limit": "100"}
        )
        reservation_page, _, _ = actors["pharmacist"].call(
            "GET", "/api/v1/pharmacy/reservations", params={"limit": "100"}
        )
        invoice_page, _, _ = actors["billing_staff"].call(
            "GET", "/api/v1/billing/invoices", params={"limit": "100"}
        )
        emergency_page, _, _ = actors["emergency_staff"].call(
            "GET", "/api/v1/emergencies", params={"limit": "100"}
        )
        patient_id = actors["patient"].data["profile"]["id"]
        consultation_page, _, _ = actors["patient"].call(
            "GET", "/api/v1/records/consultations", params={"limit": "100"}
        )
        prescription_page, _, _ = actors["patient"].call(
            "GET", "/api/v1/records/prescriptions", params={"limit": "100"}
        )
        enabled_doctor_id = state["resources"]["doctor-profile:01"]["id"]
        doctor_view, _, _ = actors["doctor"].call("GET", f"/api/v1/doctors/{enabled_doctor_id}")
        if doctor_view["id"] != enabled_doctor_id:
            raise RuntimeError("The doctor login cannot read its own doctor profile after restart.")

        counts = {
            "enabled_login_accounts": len(actual_accounts),
            "disabled_schema_identity_accounts": len(disabled_users_page["items"]),
            "patient_profiles": len(patient_page["items"]),
            "doctor_profiles": len(doctor_page["items"]),
            "appointments": len(appointment_page["items"]),
            "medicines": len(medicine_page["items"]),
            "inventory_batches": len(inventory_page["items"]),
            "reservations": len(reservation_page["items"]),
            "invoices": len(invoice_page["items"]),
            "emergency_cases": len(emergency_page["items"]),
            "patient_visible_consultations": len(consultation_page["items"]),
            "patient_visible_prescriptions": len(prescription_page["items"]),
        }
        expected = {
            "enabled_login_accounts": 8,
            "disabled_schema_identity_accounts": 59,
            "patient_profiles": 40,
            "doctor_profiles": 20,
            "appointments": 43,
            "medicines": 50,
            "inventory_batches": 50,
            "reservations": 2,
            "invoices": 3,
            "emergency_cases": 3,
            "patient_visible_consultations": 1,
            "patient_visible_prescriptions": 1,
        }
        if counts != expected:
            raise RuntimeError(f"Post-restart API counts differ from the seeded acceptance set: {counts}")
        patient_names = {item["display_name"] for item in patient_page["items"]}
        doctor_names = {item["display_name"] for item in doctor_page["items"]}
        medicine_names = {item["name"] for item in medicine_page["items"]}
        if patient_names != set(PATIENT_NAMES):
            raise RuntimeError("The post-restart patient directory differs from the agreed fictional roster.")
        if doctor_names != {name for name, _ in DOCTORS}:
            raise RuntimeError("The post-restart doctor directory differs from the agreed fictional roster.")
        if medicine_names != set(MEDICINES):
            raise RuntimeError("The post-restart medicine catalogue differs from the agreed generic roster.")
        patient_ids = {item["id"] for item in patient_page["items"]}
        doctor_ids = {item["id"] for item in doctor_page["items"]}
        medicine_ids = {item["id"] for item in medicine_page["items"]}
        appointment_by_id = {item["id"]: item for item in appointment_page["items"]}
        if any(
            appointment["patient_id"] not in patient_ids
            or appointment["doctor_id"] not in doctor_ids
            for appointment in appointment_by_id.values()
        ):
            raise RuntimeError("An appointment references a patient or doctor outside its owner roster.")
        if any(
            invoice["patient_id"] not in patient_ids
            or invoice["appointment_id"] not in appointment_by_id
            for invoice in invoice_page["items"]
        ):
            raise RuntimeError("An invoice references a patient or appointment outside the verified owner APIs.")
        if any(case["patient_id"] not in patient_ids for case in emergency_page["items"]):
            raise RuntimeError("An emergency case references a patient outside the verified Patient roster.")
        finalized_resources = [
            value for key, value in state.get("resources", {}).items()
            if key.startswith("consultation-finalize:")
        ]
        consultation_by_id = {}
        prescription_by_id = {}
        prescription_item_ids = set()
        for finalized in finalized_resources:
            consultation = finalized["consultation"]
            consultation_by_id[consultation["id"]] = consultation
            if (
                consultation["patient_id"] not in patient_ids
                or consultation["doctor_id"] not in doctor_ids
                or consultation["appointment_id"] not in appointment_by_id
            ):
                raise RuntimeError("A consultation references an item outside the verified owner APIs.")
            record = finalized["record"]
            if record["patient_id"] != consultation["patient_id"] or record["consultation_id"] != consultation["id"]:
                raise RuntimeError("A clinical record does not match its finalized consultation and patient.")
            prescription = finalized.get("prescription")
            if prescription is not None:
                if prescription["patient_id"] != consultation["patient_id"] or prescription["consultation_id"] != consultation["id"]:
                    raise RuntimeError("A prescription does not match its finalized consultation and patient.")
                prescription_by_id[prescription["id"]] = prescription
                prescription_item_ids.update(item["id"] for item in prescription["items"])
                if any(item["medicine_id"] not in medicine_ids for item in prescription["items"]):
                    raise RuntimeError("A prescription item references a medicine outside the Pharmacy catalog.")
        if len(consultation_by_id) != 4 or len(prescription_by_id) != 3:
            raise RuntimeError("The checkpoint lacks the expected finalized consultation/prescription set.")
        for reservation in reservation_page["items"]:
            if (
                reservation["patient_id"] not in patient_ids
                or reservation["prescription_id"] not in prescription_by_id
                or any(
                    item["prescription_item_id"] not in prescription_item_ids
                    or item["medicine_id"] not in medicine_ids
                    for item in reservation["items"]
                )
            ):
                raise RuntimeError("A Pharmacy reservation references an unverified patient, prescription or medicine.")
        reservations_by_state = {}
        for item in reservation_page["items"]:
            reservations_by_state[item["state"]] = reservations_by_state.get(item["state"], 0) + 1
        invoice_paid = [
            item for item in invoice_page["items"]
            if int(item["total_minor"]) > 0 and int(item["paid_minor"]) == int(item["total_minor"])
        ]
        emergency_by_state = {}
        for item in emergency_page["items"]:
            emergency_by_state[item["state"]] = emergency_by_state.get(item["state"], 0) + 1
        if reservations_by_state.get("dispensed") != 1 or reservations_by_state.get("reserved") != 1:
            raise RuntimeError(f"The post-restart pharmacy outcomes differ from the seed scenarios: {reservations_by_state}")
        if len(invoice_paid) != 1 or sum(int(item["paid_minor"]) > 0 for item in invoice_page["items"]) != 1:
            raise RuntimeError("The post-restart invoice/payment outcomes differ from the seeded scenarios.")
        if emergency_by_state.get("processing") != 1:
            raise RuntimeError(f"The post-restart emergency workflow state is missing: {emergency_by_state}")
        counts["dispensed_reservations"] = reservations_by_state["dispensed"]
        counts["fully_paid_invoices"] = len(invoice_paid)
        counts["processing_emergency_cases"] = emergency_by_state["processing"]
        print(json.dumps({"status": "verified", "logins": sorted(actors), "api_counts": counts}, indent=2), flush=True)
    finally:
        for actor in actors.values():
            actor.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--origin", default="http://127.0.0.1:5173")
    parser.add_argument("--db-port", type=int, default=55433)
    parser.add_argument("--credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    if len(PATIENT_NAMES) != 40 or len(DOCTORS) != 20 or len(MEDICINES) != 50:
        raise SystemExit("Dataset sizes do not meet the agreed acceptance counts.")
    if not args.credentials.is_file():
        raise SystemExit("Private Phase 11 credential file is missing.")
    if args.check_only:
        print(json.dumps({"patients": len(PATIENT_NAMES), "doctors": len(DOCTORS), "medicines": len(MEDICINES), "roles": sorted(ROLE_SET)}, indent=2))
        return
    if args.verify_existing:
        verify_existing_demo(args.base_url, args.origin, args.state, args.credentials)
        return
    seed(args.base_url, args.origin, args.state, args.credentials, args.db_port)


if __name__ == "__main__":
    main()
