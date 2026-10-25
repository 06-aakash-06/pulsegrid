"""Observe the isolated Phase 10 Tempo stack with read-only synthetic traffic."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import uuid

from prepare_acceptance import AcceptanceActor, BASE, ROOT, isolated


PROJECT = "pulsegrid-audit-20261025"
TEMPO = f"{PROJECT}-tempo-1"
APPOINTMENT = f"{PROJECT}-appointment-1"
OUTPUT = ROOT / "docs/phase-10/evidence/tempo-observation-after.json"
TARGET_SECONDS = 600
INTERVAL_SECONDS = 30


def _inspect() -> dict:
    raw = subprocess.check_output(["docker", "inspect", TEMPO], text=True)
    item = json.loads(raw)[0]
    return {
        "restart_count": item["RestartCount"],
        "running": item["State"]["Running"],
        "oom_killed": item["State"]["OOMKilled"],
        "started_at": item["State"]["StartedAt"],
        "memory_limit_bytes": item["HostConfig"]["Memory"],
    }


def _probe(previous_trace_id: str | None) -> dict:
    code = r'''import json,sys,urllib.error,urllib.request
out={}
for path in ['/ready','/metrics','/api/search?tags=service.name%3Ddoctor&limit=5']:
 try:
  r=urllib.request.urlopen('http://tempo:3200'+path,timeout=8)
  body=r.read().decode()
  out[path]={'http':r.status}
  if path=='/metrics':
   selected={}
   for line in body.splitlines():
    if line.startswith(('go_gc_gomemlimit_bytes ','process_resident_memory_bytes ',
        'go_memstats_heap_alloc_bytes ','tempo_distributor_spans_received_total{',
        'tempo_live_store_failed_completions_total ',
        'tempo_live_store_local_failed_flushes_total ')):
     selected[line.split(' ',1)[0]]=line.rsplit(' ',1)[-1]
   out['metrics']=selected
  elif path.startswith('/api/search'):
   data=json.loads(body)
   out['search_result_count']=len(data.get('traces',[]))
 except urllib.error.HTTPError as e:
  out[path]={'http':e.code}
 except Exception as e:
  out[path]={'error':type(e).__name__}
if len(sys.argv)>1 and sys.argv[1]!='-':
 try:
  r=urllib.request.urlopen('http://tempo:3200/api/traces/'+sys.argv[1],timeout=8)
  data=json.loads(r.read())
  batches=data.get('batches',data.get('resourceSpans',[]))
  out['previous_trace_query']={'http':r.status,'batches':len(batches)}
 except urllib.error.HTTPError as e:
  out['previous_trace_query']={'http':e.code}
 except Exception as e:
  out['previous_trace_query']={'error':type(e).__name__}
print(json.dumps(out))'''
    args = ["docker", "exec", APPOINTMENT, "python", "-c", code]
    args.append(previous_trace_id or "-")
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        return {"probe_error": result.returncode}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"probe_error": "invalid_json"}


def _read_only_doctor_request(actor: AcceptanceActor) -> tuple[int, str, str]:
    trace_id = uuid.uuid4().hex
    span_id = uuid.uuid4().hex[:16]
    request_id = str(uuid.uuid4())
    response = actor.client.get(
        "/api/v1/doctors?limit=5",
        headers={
            "Authorization": "Bearer " + actor.token,
            "traceparent": f"00-{trace_id}-{span_id}-01",
            "X-Request-ID": request_id,
        },
    )
    return response.status_code, trace_id, request_id


def _log_categories() -> dict[str, int]:
    result = subprocess.run(
        ["docker", "logs", "--tail", "250", TEMPO],
        capture_output=True,
        text=True,
        timeout=15,
    )
    lines = set((result.stdout + result.stderr).splitlines())
    return {
        "idle_scheduler_no_jobs_found": sum("no jobs found" in line.lower() for line in lines),
        "error_lines": sum("level=error" in line.lower() or '"level":"error"' in line.lower() for line in lines),
        "warning_lines": sum("level=warn" in line.lower() or '"level":"warn"' in line.lower() for line in lines),
    }


def main() -> None:
    isolated()
    state = json.loads((ROOT / "secrets/phase10/fixture.json").read_text())
    patient = AcceptanceActor(BASE, state["actors"]["patient"])
    patient.login()

    initial_logs = subprocess.run(
        ["docker", "logs", "--tail", "250", TEMPO],
        capture_output=True,
        text=True,
        timeout=15,
    )
    unique_logs = set((initial_logs.stdout + initial_logs.stderr).splitlines())
    initial_container = _inspect()
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    samples: list[dict] = []
    previous_trace_id: str | None = None
    log_categories = {"idle_scheduler_no_jobs_found": 0, "error_lines": 0, "warning_lines": 0}
    last_sample_at = started

    while True:
        elapsed = time.monotonic() - started
        if samples and elapsed >= TARGET_SECONDS:
            break
        if samples:
            delay = INTERVAL_SECONDS - (time.monotonic() - last_sample_at)
            if delay > 0:
                time.sleep(delay)
        last_sample_at = time.monotonic()

        if samples and len(samples) % 8 == 0:
            patient.login()
        api_status, trace_id, request_id = _read_only_doctor_request(patient)
        probe = _probe(previous_trace_id)
        container = _inspect()
        logs = subprocess.run(
            ["docker", "logs", "--tail", "250", TEMPO],
            capture_output=True,
            text=True,
            timeout=15,
        )
        for line in set((logs.stdout + logs.stderr).splitlines()) - unique_logs:
            unique_logs.add(line)
            lowered = line.lower()
            if "no jobs found" in lowered:
                log_categories["idle_scheduler_no_jobs_found"] += 1
            if "level=error" in lowered or '"level":"error"' in lowered:
                log_categories["error_lines"] += 1
            if "level=warn" in lowered or '"level":"warn"' in lowered:
                log_categories["warning_lines"] += 1

        sample = {
            "at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": time.monotonic() - started,
            "read_only_doctor_request_http": api_status,
            "request_id": request_id,
            "trace_id": trace_id,
            "container": container,
            **probe,
        }
        samples.append(sample)
        previous_trace_id = trace_id
        document = {
            "stack": PROJECT,
            "traffic": "authenticated synthetic Patient GET /api/v1/doctors?limit=5 through isolated gateway",
            "target_seconds": TARGET_SECONDS,
            "interval_seconds": INTERVAL_SECONDS,
            "started_at": started_at,
            "initial_container": initial_container,
            "complete": sample["elapsed_seconds"] >= TARGET_SECONDS,
            "observed_seconds": sample["elapsed_seconds"],
            "sample_count": len(samples),
            "scheduler_and_log_categories": dict(log_categories),
            "samples": samples,
        }
        OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
        if len(samples) in (1, 11, 21):
            print(
                "Tempo observation",
                len(samples),
                "elapsed_s",
                round(sample["elapsed_seconds"], 1),
                "ready",
                probe.get("/ready"),
                "trace_query",
                probe.get("previous_trace_query"),
                flush=True,
            )

    print(
        "Tempo observation complete",
        round(time.monotonic() - started, 1),
        "seconds",
        len(samples),
        "samples",
        json.dumps(_inspect(), sort_keys=True),
        flush=True,
    )


if __name__ == "__main__":
    main()
