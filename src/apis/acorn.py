"""Read-only client for the unofficial ACORN Student Web Services REST API.

ACORN is U of T's course enrolment portal. After UTORauth SAML login and Duo,
the web app calls JSON routes under:

    https://acorn.utoronto.ca/sws/rest

This client only issues GET requests to ACORN REST paths. It does not call
POST/PUT/PATCH/DELETE enrolment or account mutation routes (for example
/enrolment/course/modify). UTORauth SAML login still posts HTML forms to the
IdP, which is required to establish a session.

Endpoint inventory is based on observed browser traffic. This is not an
officially supported public API. Enrolment-related payloads are sensitive:
callers must not log or commit bodies.
"""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .degree_explorer import parse_first_form
from .duo_mfa import DuoBrowserConfig, DuoMfaError, complete_duo_in_browser

BASE_URL = "https://acorn.utoronto.ca/sws/rest"
APP_URL = "https://acorn.utoronto.ca/sws"
IDP_HOST = "idpz.utorauth.utoronto.ca"
SP_HOST = "acorn.utoronto.ca"

ELIGIBLE_REGISTRATIONS_PATH = "/enrolment/eligible-registrations"
CURRENT_REGISTRATIONS_PATH = "/enrolment/current-registrations"
ENROLLED_COURSES_PATH = "/enrolment/course/enrolled-courses"
DASHBOARD_ENROLLED_PATH = "/dashboard/courseRegistration/enrolledCourses"
PLAN_PATH = "/enrolment/plan"
COURSE_VIEW_PATH = "/enrolment/course/view"
NOTIFICATION_PATH = "/notification"
PROFILE_PATH = "/profile/studentRegistrationInfo"
START_TIMES_PATH = "/enrolment/start-times"

# Observed on the ACORN dashboard after login (Sep 2026).
DASHBOARD_REST_PATHS = (
    "/notification",
    "/enrolment/current-registrations",
    "/acorn-check-list/items",
    "/acorn-check-list/todos",
    "/profile/studentRegistrationInfo",
    "/dashboard/finance/dentalOptOutSessionCode",
    "/dashboard/courseRegistration/enrolledCourses",
    "/enrolment/posts-with-invite-status",
    "/awards",
    "/fee-payment/tuitionFeeAdmissionDeposits",
    "/enrolment/start-times",
    "/financial-account/tuitionPrepayment",
    "/net-cost-view",
    "/dashboard/eventCalendar/getDashboardEvents/TODAY",
    "/enrolment/eligible-registrations",
)

DEFAULT_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_LOGIN_STEPS = 8

# Known ACORN mutation route suffixes — blocked by get().
_BLOCKED_REST_PATH_SUFFIXES = (
    "/modify",
    "/delete",
    "/update",
    "/create",
    "/submit",
    "/save",
    "/remove",
)

# Registration query fields copied from registrationParams for enrolled-courses.
_REGISTRATION_QUERY_FIELDS = (
    "postCode",
    "postDescription",
    "sessionCode",
    "sessionDescription",
    "status",
    "assocOrgCode",
    "acpDuration",
    "levelOfInstruction",
    "typeOfProgram",
    "designationCode1",
    "primaryOrgCode",
    "secondaryOrgCode",
    "collaborativeOrgCode",
    "adminOrgCode",
    "coSecondaryOrgCode",
    "yearOfStudy",
    "postAcpDuration",
)

class AcornError(Exception):
    """Base error for ACORN client failures."""


class AcornAuthError(AcornError):
    """Login failed, MFA blocked, or the session is not authenticated."""


class AcornWriteError(AcornError):
    """Caller attempted a non-read ACORN REST operation."""


def _login_form_error(html: str) -> str | None:
    text = html.lower()
    if "username or password is not correct" in text:
        return "UTORauth says the username or password is not correct."
    return None


def _host_is(url: str, host: str) -> bool:
    return (urlparse(url).hostname or "") == host


def _is_duo_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("duosecurity.com")


class AcornClient:
    """Session-backed, read-only client for ACORN GET REST methods."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = BASE_URL.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            }
        )
        self._browser_fetch: dict[str, Any] | None = None
        self._registrations: list[dict[str, Any]] | None = None

    def probe_reachability(
        self, path: str = ELIGIBLE_REGISTRATIONS_PATH
    ) -> dict[str, Any]:
        """GET a REST path without following the SAML redirect."""
        url = self.base_url + path
        response = self.session.get(url, allow_redirects=False, timeout=self.timeout)
        location = response.headers.get("Location", "")
        location_host = urlparse(urljoin(url, location)).hostname or ""
        return {
            "url": url,
            "status_code": response.status_code,
            "location": location,
            "location_host": location_host,
            "redirects_to_idp": (
                response.status_code in {301, 302, 303, 307, 308}
                and location_host == IDP_HOST
            ),
        }

    def login(
        self,
        utorid: str,
        password: str,
        mfa_code: str | None = None,
        *,
        keep_browser_open: bool = False,
        probe_urls: list[str] | None = None,
    ) -> None:
        """Complete UTORauth SAML login for ACORN, including Duo in a browser."""
        if not utorid or not password:
            raise AcornAuthError("UTORid and password are required for login.")

        response = self.session.get(APP_URL, timeout=self.timeout)
        self._follow_idp_until_service(
            response,
            utorid,
            password,
            mfa_code,
            keep_browser_open=keep_browser_open,
            probe_urls=probe_urls,
        )

    def get(self, path: str, params: dict[str, str] | None = None) -> requests.Response:
        """GET an ACORN REST path. Mutation routes are rejected."""
        self._assert_read_only_path(path)
        url = path if path.startswith("http") else self.base_url + path
        return self.session.get(url, params=params, timeout=self.timeout)

    def get_eligible_registrations(self) -> list[dict[str, Any]]:
        """GET /enrolment/eligible-registrations as a JSON array."""
        cached = self._browser_fetch or {}
        payload = cached.get("json")
        if isinstance(payload, list):
            self._registrations = payload
            return payload
        payload = self._get_json_array(ELIGIBLE_REGISTRATIONS_PATH)
        self._registrations = payload
        return payload

    def get_enrolled_courses(self, registration_index: int = 0) -> dict[str, Any]:
        """GET /enrolment/course/enrolled-courses for one registration."""
        params = self._registration_query_params(registration_index)
        return self._get_json(ENROLLED_COURSES_PATH, params=params)

    def get_current_registrations(self) -> list[Any]:
        """GET /enrolment/current-registrations."""
        return self._get_json_array(CURRENT_REGISTRATIONS_PATH)

    def get_dashboard_enrolled_courses(self) -> dict[str, Any]:
        """GET /dashboard/courseRegistration/enrolledCourses."""
        return self._get_json(DASHBOARD_ENROLLED_PATH)

    def get_notifications(self) -> Any:
        """GET /notification."""
        response = self.get(NOTIFICATION_PATH)
        return response.json()

    def get_profile(self) -> dict[str, Any]:
        """GET /profile/studentRegistrationInfo."""
        return self._get_json(PROFILE_PATH)

    def get_start_times(self) -> Any:
        """GET /enrolment/start-times."""
        response = self.get(START_TIMES_PATH)
        return response.json()

    def get_planned_courses(self, registration_index: int = 0) -> list[Any]:
        """GET /enrolment/plan for one registration."""
        registration = self._registration_record(registration_index)
        params = {
            "candidacyPostCode": str(registration.get("candidacyPostCode", "")),
            "candidacySessionCode": str(registration.get("candidacySessionCode", "")),
            "sessionCode": str(
                registration.get("registrationParams", {}).get("sessionCode", "")
            ),
        }
        return self._get_json_array(PLAN_PATH, params=params)

    def view_eligible_registrations(self) -> dict[str, Any]:
        """Return a PII-safe summary of eligible registrations."""
        registrations = self.get_eligible_registrations()
        summaries = []
        for item in registrations:
            if not isinstance(item, dict):
                continue
            post = item.get("post") or {}
            summaries.append(
                {
                    "candidacyPostCode": item.get("candidacyPostCode"),
                    "sessionDescription": item.get("sessionDescription"),
                    "post_description_present": bool(post.get("description")),
                }
            )
        return {
            "registration_count": len(registrations),
            "registrations": summaries,
        }

    def view_enrolled_courses(self, registration_index: int = 0) -> dict[str, Any]:
        """Return counts only from enrolled-courses JSON (APP/WAIT/DROP buckets)."""
        payload = self.get_enrolled_courses(registration_index)
        summary: dict[str, Any] = {"top_level_keys": sorted(payload.keys())}
        for bucket in ("APP", "WAIT", "DROP"):
            courses = payload.get(bucket)
            summary[f"{bucket.lower()}_count"] = (
                len(courses) if isinstance(courses, list) else 0
            )
        return summary

    def view_json_keys(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = self.get(path, params=params)
        if response.status_code != 200:
            return {
                "path": path,
                "http_status": response.status_code,
                "top_level_keys": None,
            }
        try:
            payload = response.json()
        except ValueError:
            return {"path": path, "http_status": 200, "top_level_keys": None}
        if isinstance(payload, dict):
            return {"path": path, "http_status": 200, "top_level_keys": sorted(payload.keys())}
        if isinstance(payload, list):
            return {
                "path": path,
                "http_status": 200,
                "top_level_keys": [f"[array len={len(payload)}]"],
            }
        return {"path": path, "http_status": 200, "top_level_keys": None}

    def default_probe_urls(self) -> list[str]:
        """Read-only REST URLs worth probing immediately after Duo."""
        return [self.base_url + path for path in DASHBOARD_REST_PATHS[:5]]

    def _assert_read_only_path(self, path: str) -> None:
        """Reject paths that look like ACORN write/mutation endpoints."""
        parsed_path = urlparse(path).path if path.startswith("http") else path
        lower = parsed_path.lower().rstrip("/")
        for suffix in _BLOCKED_REST_PATH_SUFFIXES:
            if lower.endswith(suffix):
                raise AcornWriteError(
                    f"Refusing non-read ACORN path {path!r}. "
                    "This client only supports GET on read endpoints."
                )

    def _registration_record(self, registration_index: int) -> dict[str, Any]:
        registrations = self.get_eligible_registrations()
        if registration_index < 0 or registration_index >= len(registrations):
            raise AcornError(f"registration_index {registration_index} is out of range.")
        record = registrations[registration_index]
        if not isinstance(record, dict):
            raise AcornError("Eligible registration entry was not an object.")
        return record

    def _registration_query_params(self, registration_index: int) -> dict[str, str]:
        record = self._registration_record(registration_index)
        params_obj = record.get("registrationParams") or {}
        if not isinstance(params_obj, dict):
            raise AcornError("registrationParams missing from eligible registration.")
        query: dict[str, str] = {}
        for key in _REGISTRATION_QUERY_FIELDS:
            value = params_obj.get(key)
            if value is not None:
                query[key] = str(value)
        return query

    def _get_json(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self.get(path, params=params)
        if response.status_code in {401, 403} or _host_is(response.url, IDP_HOST):
            raise AcornAuthError(
                f"{path} is not authenticated (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            raise AcornError(f"{path} returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AcornError(f"{path} did not return JSON.") from exc
        if not isinstance(payload, dict):
            raise AcornError(f"{path} JSON root was not an object.")
        return payload

    def _get_json_array(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> list[Any]:
        response = self.get(path, params=params)
        if response.status_code in {401, 403} or _host_is(response.url, IDP_HOST):
            raise AcornAuthError(
                f"{path} is not authenticated (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            raise AcornError(f"{path} returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AcornError(f"{path} did not return JSON.") from exc
        if not isinstance(payload, list):
            raise AcornError(f"{path} JSON root was not an array.")
        return payload

    def _follow_idp_until_service(
        self,
        response: requests.Response,
        utorid: str,
        password: str,
        mfa_code: str | None = None,
        *,
        keep_browser_open: bool = False,
        probe_urls: list[str] | None = None,
    ) -> None:
        posted_credentials = False
        probe_list = probe_urls if probe_urls is not None else self.default_probe_urls()
        for _ in range(MAX_LOGIN_STEPS):
            if _is_duo_host(response.url):
                if os.environ.get("GITHUB_ACTIONS") == "true":
                    raise AcornAuthError(
                        "UTORauth asked for Duo. GitHub Actions cannot complete MFA."
                    )
                try:
                    self._browser_fetch = complete_duo_in_browser(
                        self.session,
                        response.url,
                        mfa_code=mfa_code,
                        utorid=utorid,
                        password=password,
                        rest_url=self.base_url + ELIGIBLE_REGISTRATIONS_PATH,
                        app_url=APP_URL,
                        browser_config=DuoBrowserConfig.acorn(),
                        keep_open=keep_browser_open,
                        probe_urls=probe_list,
                    )
                except DuoMfaError as exc:
                    raise AcornAuthError(str(exc)) from exc
                return
            if _host_is(response.url, SP_HOST) and not _host_is(response.url, IDP_HOST):
                if "json" in response.headers.get("Content-Type", "") or response.status_code == 200:
                    return
            html = response.text
            form = parse_first_form(html)
            if form is None:
                raise AcornAuthError(
                    "UTORauth login did not present a form to continue."
                )
            action_url = urljoin(response.url, form["action"])
            fields = dict(form["inputs"])
            if "j_username" in fields:
                if posted_credentials:
                    idp_error = _login_form_error(html)
                    raise AcornAuthError(
                        idp_error
                        or "UTORauth returned the login form again. Check UTORid/password."
                    )
                fields["j_username"] = utorid
                fields["j_password"] = password
                if "_eventId_proceed" not in fields:
                    fields["_eventId_proceed"] = ""
                posted_credentials = True
            elif "SAMLResponse" not in fields and posted_credentials:
                raise AcornAuthError(
                    "UTORauth did not return a SAMLResponse after login."
                )
            response = self.session.request(
                form["method"] or "post",
                action_url,
                data=fields,
                timeout=self.timeout,
                headers={"Referer": response.url},
            )

        raise AcornAuthError("UTORauth login did not finish within the step limit.")
