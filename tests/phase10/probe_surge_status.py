"""Make bounded read-only Surge-status requests with correlation evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time
import uuid

from prepare_acceptance import AcceptanceActor, BASE, ROOT, isolated


PROJECT = "pulsegrid-audit-20261025"
APPOINTMENT = f"{PROJECT}-appointment-1"
OUTPUT = ROOT / "docs/phase-10/evidence/surge-status-reproduction.json"
REQUEST_COUNT = 8
INTERVAL_SECONDS = 15


def _trace_queries(trace_ids: list[str]) -> list[dict]:
    code = r'''import json,sys,urllib.error,urllib.request
out=[]
for tid in sys.argv[1:]:
 try:
  r=urllib.request.urlopen('http://tempo:3200/api/traces/'+tid,timeout=8)
  data=json.loads(r.read())
  out.append({'http':r.status,'batches':len(data.get('batches',data.get('resourceSpans',[])))})
 except urllib.error.HTTPError as e:
  out.append({'http':e.code})
 except Exception as e:
  out.append({'error':type(e).__name__})
print(json.dumps(out))'''
    result = subprocess.run(
        ["docker", "exec", APPOINTMENT, "python", "-c", code, *trace_ids],
        capture_output=True,
        text=True,
        timeout=80,
    )
    if result.returncode:
        return [{"probe_error": result.returncode} for _ in trace_ids]
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return [{"probe_error": "invalid_json"} for _ in trace_ids]


def main() -> None:
    isolated()
    state = json.loads((ROOT / "secrets/phase10/fixture.json").read_text())
    admin = AcceptanceActor(BASE, state["actors"]["hospital_admin"])
    admin.login()
    started = datetime.now(timezone.utc).isoformat()
    monotonic_start = time.monotonic()
    samples = []
    trace_ids = []

    for index in range(REQUEST_COUNT):
        trace_id = uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        request_id = str(uuid.uuid4())
        correlation_id = str(uuid.uuid4())
        begin = time.monotonic()
        try:
            response = admin.client.get(
                "/api/v1/appointments/operations/surge-mode",
                headers={
                    "Authorization": "Bearer " + admin.token,
                    "traceparent": f"00-{trace_id}-{span_id}-01",
                    "X-Request-ID": request_id,
                    "X-Correlation-ID": correlation_id,
                },
            )
            code = None
            current_state = None
            try:
                payload = response.json()
                code = payload.get("error", {}).get("code") if isinstance(payload.get("error"), dict) else payload.get("code")
                current_state = payload.get("state") if response.status_code == 200 else None
            except ValueError:
                pass
            sample = {
                "at": datetime.now(timezone.utc).isoformat(),
                "http": response.status_code,
                "duration_ms": round((time.monotonic() - begin) * 1000, 3),
                "request_id": response.headers.get("x-request-id", request_id),
                "correlation_id": response.headers.get("x-correlation-id", correlation_id),
                "trace_id": trace_id,
                "error_code": code,
                "surge_state": current_state,
            }
        except Exception as error:
            sample = {
                "at": datetime.now(timezone.utc).isoformat(),
                "http": None,
                "duration_ms": round((time.monotonic() - begin) * 1000, 3),
                "request_id": request_id,
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "client_error": type(error).__name__,
            }
        samples.append(sample)
        trace_ids.append(trace_id)
        print(index + 1, sample["http"], sample.get("error_code"), flush=True)
        if index + 1 < REQUEST_COUNT:
            time.sleep(INTERVAL_SECONDS)

    for sample, query in zip(samples, _trace_queries(trace_ids), strict=True):
        sample["trace_query"] = query
    document = {
        "isolated_project": PROJECT,
        "method": "read-only GET /api/v1/appointments/operations/surge-mode",
        "request_count": REQUEST_COUNT,
        "interval_seconds": INTERVAL_SECONDS,
        "started_at": started,
        "observed_seconds": round(time.monotonic() - monotonic_start, 3),
        "raw_tokens_recorded": False,
        "samples": samples,
    }
    OUTPUT.write_text(json.dumps(document, indent=2) + "\n")
    print("Surge-status probe complete", json.dumps({"samples": len(samples), "output": str(OUTPUT)}), flush=True)


if __name__ == "__main__":
    main()
