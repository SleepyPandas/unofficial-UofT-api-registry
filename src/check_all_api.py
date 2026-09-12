"""Run read-only API health checks and write publishable status files.

Local testing:
    1. Fill UOFT_UTORID and UOFT_PASSWORD in the repo-root .env file.
    2. python src/check_all_api.py

GitHub Actions maps UOFT_UTORID and UOFT_PASSWORD from repository secrets
(not environment secrets). The checker never writes API response bodies,
only status metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from apis.acorn import (
    ELIGIBLE_REGISTRATIONS_PATH,
    AcornAuthError,
    AcornClient,
    AcornError,
)
from apis.degree_explorer import (
    GET_ACADEMIC_HISTORY_PATH,
    DegreeExplorerAuthError,
    DegreeExplorerClient,
    DegreeExplorerError,
)
from apis.timetable_builder import TimetableBuilderAPI
from env_file import load_env_file

EASTERN = ZoneInfo("America/Toronto")
DATA_DIR = REPO_ROOT / "data"
APIS_PATH = DATA_DIR / "apis.json"
BADGE_COLORS = {
    "operational": "brightgreen",
    "auth_required": "blue",
    "degraded": "yellow",
    "down": "red",
    "deprecated": "lightgrey",
    "unknown": "lightgrey",
}

STATUS_LABELS = {
    "operational": "operational",
    "auth_required": "auth required",
    "degraded": "degraded",
    "down": "down",
    "deprecated": "deprecated",
    "unknown": "unknown",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DATA_DIR / "status.json",
        help="Status JSON path; badge endpoint JSON is written beside it.",
    )
    args = parser.parse_args()

    load_env_file(REPO_ROOT / ".env")
    registry = json.loads(APIS_PATH.read_text(encoding="utf-8"))
    results = []
    for api in registry.get("apis", []):
        if api.get("id") == "degree-explorer":
            results.append(check_degree_explorer(api))
        elif api.get("id") == "acorn":
            results.append(check_acorn(api))
        elif api.get("id") == "timetable-builder":
            results.append(check_timetable_builder(api))
        else:
            results.append(unchecked_api(api, "unknown", "Not part of this check yet."))

    payload = {
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "results": results,
    }
    write_status_files(payload, args.output)
    for result in results:
        print(
            f"{result['name']}: {result['status']} "
            f"(http={result.get('status_code')}, {result.get('detail')})"
        )
    return 0


def check_degree_explorer(api: dict[str, Any]) -> dict[str, Any]:
    """Probe Degree Explorer reachability, then optionally authenticate."""
    endpoint = api["endpoints"][0]
    started = time.perf_counter()
    client = DegreeExplorerClient()
    try:
        probe = client.probe_reachability(endpoint["path"])
    except Exception as exc:
        return result_row(
            api,
            endpoint,
            status="down",
            status_code=None,
            latency_ms=_latency_ms(started),
            detail=f"Reachability probe failed: {exc}",
        )

    if not probe["redirects_to_idp"]:
        status = "down" if (probe["status_code"] or 0) >= 500 else "degraded"
        return result_row(
            api,
            endpoint,
            status=status,
            status_code=probe["status_code"],
            latency_ms=_latency_ms(started),
            detail=(
                "Expected 302 to idpz.utorauth.utoronto.ca, "
                f"got HTTP {probe['status_code']} location={probe['location_host'] or 'none'}"
            ),
        )

    utorid = os.environ.get("UOFT_UTORID", "").strip()
    password = os.environ.get("UOFT_PASSWORD", "")
    reachable = result_row(
        api,
        endpoint,
        status="auth_required",
        status_code=probe["status_code"],
        latency_ms=_latency_ms(started),
        detail="Service redirected to UTORauth, which is the expected unauthenticated response.",
    )
    if not utorid or not password:
        return reachable

    auth_client = DegreeExplorerClient()
    try:
        auth_client.login(
            utorid,
            password,
            mfa_code=os.environ.get("UOFT_MFA_CODE", "").strip() or None,
        )
        history = auth_client.get_academic_history()
    except DegreeExplorerAuthError as exc:
        reachable["detail"] = (
            "Service is reachable via UTORauth. Authenticated probe did not finish: "
            f"{exc}"
        )
        return reachable
    except DegreeExplorerError as exc:
        reachable["detail"] = (
            "Service is reachable via UTORauth. Authenticated GET failed after login: "
            f"{exc}"
        )
        return reachable

    if "facultyCourses" not in history:
        reachable["detail"] = (
            "Service is reachable via UTORauth. Authenticated GET returned JSON "
            "without facultyCourses."
        )
        return reachable
    return result_row(
        api,
        endpoint,
        status="operational",
        status_code=200,
        latency_ms=_latency_ms(started),
        detail="Authenticated GET /dxStudent/getAcademicHistory returned JSON.",
    )


def check_acorn(api: dict[str, Any]) -> dict[str, Any]:
    """Probe ACORN reachability, then optionally authenticate."""
    endpoint = api["endpoints"][0]
    started = time.perf_counter()
    client = AcornClient()
    try:
        probe = client.probe_reachability(endpoint.get("path", ELIGIBLE_REGISTRATIONS_PATH))
    except Exception as exc:
        return result_row(
            api,
            endpoint,
            status="down",
            status_code=None,
            latency_ms=_latency_ms(started),
            detail=f"Reachability probe failed: {exc}",
        )

    if not probe["redirects_to_idp"]:
        status = "down" if (probe["status_code"] or 0) >= 500 else "degraded"
        return result_row(
            api,
            endpoint,
            status=status,
            status_code=probe["status_code"],
            latency_ms=_latency_ms(started),
            detail=(
                "Expected 302 to idpz.utorauth.utoronto.ca, "
                f"got HTTP {probe['status_code']} location={probe['location_host'] or 'none'}"
            ),
        )

    utorid = os.environ.get("UOFT_UTORID", "").strip()
    password = os.environ.get("UOFT_PASSWORD", "")
    reachable = result_row(
        api,
        endpoint,
        status="auth_required",
        status_code=probe["status_code"],
        latency_ms=_latency_ms(started),
        detail="Service redirected to UTORauth, which is the expected unauthenticated response.",
    )
    if not utorid or not password:
        return reachable

    auth_client = AcornClient()
    try:
        auth_client.login(
            utorid,
            password,
            mfa_code=os.environ.get("UOFT_MFA_CODE", "").strip() or None,
        )
        registrations = auth_client.get_eligible_registrations()
    except AcornAuthError as exc:
        reachable["detail"] = (
            "Service is reachable via UTORauth. Authenticated probe did not finish: "
            f"{exc}"
        )
        return reachable
    except AcornError as exc:
        reachable["detail"] = (
            "Service is reachable via UTORauth. Authenticated GET failed after login: "
            f"{exc}"
        )
        return reachable

    if not isinstance(registrations, list):
        reachable["detail"] = (
            "Service is reachable via UTORauth. Authenticated GET returned JSON "
            "that was not an array."
        )
        return reachable
    return result_row(
        api,
        endpoint,
        status="operational",
        status_code=200,
        latency_ms=_latency_ms(started),
        detail="Authenticated GET /enrolment/eligible-registrations returned JSON.",
    )


def check_timetable_builder(api: dict[str, Any]) -> dict[str, Any]:
    """Probe Timetable Builder (TTB) availability and latency."""
    endpoint = api["endpoints"][0]
    started = time.perf_counter()
    client = TimetableBuilderAPI()
    try:
        report = client.check_health()
        status = report["status"].lower()
        detail = report["error"] or f"GET {endpoint['path']} returned HTTP {report['http_status']}."
        return result_row(
            api,
            endpoint,
            status=status,
            status_code=report["http_status"],
            latency_ms=report["latency_ms"],
            detail=detail,
        )
    except Exception as exc:
        return result_row(
            api,
            endpoint,
            status="down",
            status_code=None,
            latency_ms=_latency_ms(started),
            detail=f"Health probe failed: {exc}",
        )


def unchecked_api(api: dict[str, Any], status: str, detail: str) -> dict[str, Any]:
    endpoint = (api.get("endpoints") or [{}])[0]
    return result_row(api, endpoint, status=status, status_code=None, latency_ms=None, detail=detail)


def result_row(
    api: dict[str, Any],
    endpoint: dict[str, Any],
    status: str,
    status_code: int | None,
    latency_ms: int | None,
    detail: str,
) -> dict[str, Any]:
    return {
        "id": api.get("id"),
        "name": api.get("name"),
        "auth": api.get("auth"),
        "official_support": api.get("official_support"),
        "notes": api.get("notes"),
        "method": endpoint.get("method", "GET"),
        "path": endpoint.get("path", GET_ACADEMIC_HISTORY_PATH),
        "url": api.get("base_url", "").rstrip("/") + endpoint.get("path", ""),
        "human_url": api.get("human_url"),
        "status": status,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "detail": detail,
    }


def write_status_files(payload: dict[str, Any], output_path: Path) -> None:
    """Write full status plus Shields.io endpoint payloads."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    badges_dir = output_path.parent / "badges"
    badges_dir.mkdir(exist_ok=True)
    for result in payload.get("results", []):
        status = result["status"]
        badge = {
            "schemaVersion": 1,
            "label": "",
            "message": STATUS_LABELS.get(status, status.replace("_", " ")),
            "color": BADGE_COLORS.get(status, "lightgrey"),
            "cacheSeconds": 300,
        }
        badge_path = badges_dir / f"{result['id']}.json"
        badge_path.write_text(json.dumps(badge, indent=2) + "\n", encoding="utf-8")

    checked_badge = {
        "schemaVersion": 1,
        "label": "last checked",
        "message": _eastern_badge_time(payload.get("checked_at")),
        "color": "blue",
        "cacheSeconds": 300,
    }
    (badges_dir / "checked-at.json").write_text(
        json.dumps(checked_badge, indent=2) + "\n",
        encoding="utf-8",
    )


def _eastern_badge_time(checked_at: str | None) -> str:
    """Format a UTC ISO timestamp as a short Eastern Time badge label."""
    if not checked_at:
        return "never"
    try:
        instant = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
    except ValueError:
        return checked_at
    local = instant.astimezone(EASTERN)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%b')} {local.day}, {hour}:{local.strftime('%M')} {local.strftime('%p')} ET"


def _latency_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
