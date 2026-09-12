"""Read-only client for the unofficial Degree Explorer REST API.

Degree Explorer is a U of T student planner. After UTORauth SAML login,
the web app calls JSON routes under:

    https://degreeexplorer.utoronto.ca/degreeExplorer/rest

Confirmed student reads include academic history, current status, menu
payloads, and planner GETs. Write/POST routes are left for a later branch.

This is not an officially supported public API. Academic records are
sensitive: callers must not log or commit response bodies.
"""

from __future__ import annotations

import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .duo_mfa import DuoBrowserConfig, DuoMfaError, complete_duo_in_browser

BASE_URL = "https://degreeexplorer.utoronto.ca/degreeExplorer/rest"
APP_URL = "https://degreeexplorer.utoronto.ca/"
IDP_HOST = "idpz.utorauth.utoronto.ca"
SP_HOST = "degreeexplorer.utoronto.ca"
GET_ACADEMIC_HISTORY_PATH = "/dxStudent/getAcademicHistory"
GET_STUDENT_DATA_PATH = "/dxStudent/getStudentData"
GET_STUDENT_RECORD_PATH = "/dxStudent/getStudentRecord"
GET_STUDENT_USER_DATA_PATH = "/dxMenu/getStudentUserData"
GET_STUDENT_MENU_PATH = "/dxMenu/getStudentMenu"
GET_MESSAGES_PATH = "/messages/getMessages"
GET_SESSION_TIMEOUTS_PATH = "/dxMenu/getSessionTimeouts"
GET_PLANNER_PATH = "/dxPlanner/getPlanner"
GET_CELL_DETAILS_PATH = "/dxPlanner/getCellDetails"
DEFAULT_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
MAX_LOGIN_STEPS = 8


class DegreeExplorerError(Exception):
    """Base error for Degree Explorer client failures."""


class DegreeExplorerAuthError(DegreeExplorerError):
    """Login failed, MFA blocked, or the session is not authenticated."""


class _HtmlFormParser(HTMLParser):
    """Collect the first HTML form's action, method, and named fields."""

    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: (value or "") for key, value in attrs}
        if tag == "form" and self._current is None:
            self._current = {
                "action": attr_map.get("action", ""),
                "method": attr_map.get("method", "get").lower(),
                "inputs": {},
            }
            return
        if self._current is None:
            return
        if tag in {"input", "button"}:
            name = attr_map.get("name")
            if name:
                self._current["inputs"][name] = attr_map.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._current is not None:
            self.forms.append(self._current)
            self._current = None


def parse_first_form(html: str) -> dict[str, Any] | None:
    """Return the first HTML form on the page, or None if there is none."""
    parser = _HtmlFormParser()
    parser.feed(html)
    if not parser.forms:
        return None
    return parser.forms[0]


def _login_form_error(html: str) -> str | None:
    """Return a short IdP error if the login form came back with a failure."""
    text = html.lower()
    if "username or password is not correct" in text:
        return "UTORauth says the username or password is not correct."
    return None


class DegreeExplorerClient:
    """Session-backed client for Degree Explorer get/view REST methods."""

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

    def probe_reachability(self, path: str = GET_ACADEMIC_HISTORY_PATH) -> dict[str, Any]:
        """GET a REST path without following the SAML redirect.

        A healthy unauthenticated response is HTTP 302 to the UTORauth IdP.
        Following that redirect without a browser session is not a useful
        health signal, so this method stops at the first hop.
        """
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
        keep_open: bool = False,
        keep_open_timeout_ms: int | None = None,
        on_ready: Any = None,
    ) -> None:
        """Complete UTORauth SAML login for Degree Explorer.

        After the password form, U of T sends the session to Duo. Locally
        a Chromium window opens so you can enter a one-time passcode or
        approve a push. GitHub Actions cannot complete Duo; skip secrets
        there and keep the unauthenticated reachability probe.

        keep_open leaves Chromium up after Duo so extra REST calls can be
        observed. on_ready(page, context, result) runs while it is still open.

        Raises DegreeExplorerAuthError on empty credentials, a rejected
        password, or Duo that is not completed in time.
        """
        if not utorid or not password:
            raise DegreeExplorerAuthError("UTORid and password are required for login.")

        response = self.session.get(APP_URL, timeout=self.timeout)
        self._follow_idp_until_service(
            response,
            utorid,
            password,
            mfa_code,
            keep_open=keep_open,
            keep_open_timeout_ms=keep_open_timeout_ms,
            on_ready=on_ready,
        )

    def get(self, path: str, params: dict[str, str] | None = None) -> requests.Response:
        """GET a REST path on the Degree Explorer host and return the response."""
        url = path if path.startswith("http") else self.base_url + path
        return self.session.get(url, params=params, timeout=self.timeout)

    def get_academic_history(self) -> dict[str, Any]:
        """GET /dxStudent/getAcademicHistory as JSON.

        Typical payload keys include facultyCourses, studentSessions, and
        studentCourses. The caller must not persist this payload.
        """
        cached = self._browser_fetch or {}
        payload = cached.get("json")
        if isinstance(payload, dict):
            return payload
        return self._get_json(GET_ACADEMIC_HISTORY_PATH)

    def view_academic_history(self) -> dict[str, Any]:
        """Return counts and top-level keys from academic history.

        This is a view helper: it never returns marks, course codes, or
        other student-identifying fields.
        """
        payload = self.get_academic_history()
        return summarize_academic_history(payload)

    def get_student_data(self) -> dict[str, Any]:
        """GET /dxStudent/getStudentData. Used by the Current Status page."""
        return self._get_json(GET_STUDENT_DATA_PATH)

    def get_student_record(self) -> dict[str, Any]:
        """GET /dxStudent/getStudentRecord. Used by the Current Status page."""
        return self._get_json(GET_STUDENT_RECORD_PATH)

    def get_student_user_data(self) -> dict[str, Any]:
        """GET /dxMenu/getStudentUserData. Menu/session user payload."""
        return self._get_json(GET_STUDENT_USER_DATA_PATH)

    def get_student_menu(self) -> dict[str, Any]:
        """GET /dxMenu/getStudentMenu."""
        return self._get_json(GET_STUDENT_MENU_PATH)

    def get_messages(self) -> dict[str, Any]:
        """GET /messages/getMessages. UI string catalog, not a student inbox."""
        return self._get_json(GET_MESSAGES_PATH)

    def get_session_timeouts(self) -> dict[str, Any]:
        """GET /dxMenu/getSessionTimeouts."""
        return self._get_json(GET_SESSION_TIMEOUTS_PATH)

    def get_planner(self) -> dict[str, Any]:
        """GET /dxPlanner/getPlanner. Used by the Planner tab."""
        return self._get_json(GET_PLANNER_PATH)

    def get_cell_details(self, params: dict[str, str] | None = None) -> dict[str, Any]:
        """GET /dxPlanner/getCellDetails. Planner cell popup after a timeline click."""
        return self._get_json(GET_CELL_DETAILS_PATH, params)

    def view_json_keys(self, path: str) -> dict[str, Any]:
        """GET a REST path and return only top-level JSON keys."""
        payload = self._get_json(path)
        return {"path": path, "top_level_keys": sorted(payload.keys())}

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        response = self.get(path, params=params)
        if response.status_code in {401, 403} or _host_is(response.url, IDP_HOST):
            raise DegreeExplorerAuthError(
                f"{path} is not authenticated (HTTP {response.status_code})."
            )
        if response.status_code != 200:
            raise DegreeExplorerError(
                f"{path} returned HTTP {response.status_code}."
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DegreeExplorerError(f"{path} did not return JSON.") from exc
        if not isinstance(payload, dict):
            raise DegreeExplorerError(f"{path} JSON root was not an object.")
        return payload

    def _follow_idp_until_service(
        self,
        response: requests.Response,
        utorid: str,
        password: str,
        mfa_code: str | None = None,
        keep_open: bool = False,
        keep_open_timeout_ms: int | None = None,
        on_ready: Any = None,
    ) -> None:
        """Walk IdP HTML forms until the session is back on Degree Explorer."""
        posted_credentials = False
        for _ in range(MAX_LOGIN_STEPS):
            if _is_duo_host(response.url):
                if os.environ.get("GITHUB_ACTIONS") == "true":
                    raise DegreeExplorerAuthError(
                        "UTORauth asked for Duo. GitHub Actions cannot complete MFA."
                    )
                try:
                    self._browser_fetch = complete_duo_in_browser(
                        self.session,
                        response.url,
                        mfa_code=mfa_code,
                        utorid=utorid,
                        password=password,
                        rest_url=self.base_url + GET_ACADEMIC_HISTORY_PATH,
                        app_url=APP_URL,
                        browser_config=DuoBrowserConfig.degree_explorer(),
                        keep_open=keep_open,
                        keep_open_timeout_ms=keep_open_timeout_ms,
                        on_ready=on_ready,
                    )
                except DuoMfaError as exc:
                    raise DegreeExplorerAuthError(str(exc)) from exc
                return
            if _host_is(response.url, SP_HOST) and not _host_is(response.url, IDP_HOST):
                if "json" in response.headers.get("Content-Type", "") or response.status_code == 200:
                    return
            html = response.text
            form = parse_first_form(html)
            if form is None:
                raise DegreeExplorerAuthError(
                    "UTORauth login did not present a form to continue."
                )
            action_url = urljoin(response.url, form["action"])
            fields = dict(form["inputs"])
            if "j_username" in fields:
                if posted_credentials:
                    idp_error = _login_form_error(html)
                    raise DegreeExplorerAuthError(
                        idp_error
                        or "UTORauth returned the login form again. Check UTORid/password."
                    )
                fields["j_username"] = utorid
                fields["j_password"] = password
                if "_eventId_proceed" not in fields:
                    fields["_eventId_proceed"] = ""
                posted_credentials = True
            elif "SAMLResponse" not in fields and posted_credentials:
                raise DegreeExplorerAuthError(
                    "UTORauth did not return a SAMLResponse after login."
                )
            response = self.session.request(
                form["method"] or "post",
                action_url,
                data=fields,
                timeout=self.timeout,
                headers={"Referer": response.url},
            )

        raise DegreeExplorerAuthError("UTORauth login did not finish within the step limit.")


def summarize_academic_history(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a PII-free summary of an academic-history JSON object."""
    faculties = payload.get("facultyCourses") or []
    session_count = 0
    course_count = 0
    if isinstance(faculties, list):
        for faculty in faculties:
            if not isinstance(faculty, dict):
                continue
            for session in faculty.get("studentSessions") or []:
                session_count += 1
                if isinstance(session, dict):
                    courses = session.get("studentCourses") or []
                    course_count += len(courses) if isinstance(courses, list) else 0
    return {
        "top_level_keys": sorted(payload.keys()),
        "faculty_count": len(faculties) if isinstance(faculties, list) else 0,
        "session_count": session_count,
        "course_count": course_count,
    }


def _host_is(url: str, host: str) -> bool:
    return (urlparse(url).hostname or "") == host


def _is_duo_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("duosecurity.com")
