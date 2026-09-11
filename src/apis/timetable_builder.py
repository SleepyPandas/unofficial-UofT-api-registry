"""
University of Toronto - Timetable Builder (TTB) API Client

This module provides a comprehensive interface to query the public Timetable
Builder API operated by the University of Toronto Enterprise Applications and
Solutions Integration (EASI).

Base URL:
    https://api.easi.utoronto.ca/ttb

Authentication:
    Public and unauthenticated. No API key, token, or UTORid credentials
    are required to access these endpoints.

Headers:
    Requests must explicitly send "Accept: application/json" to receive JSON
    responses; otherwise the service defaults to XML (<TTBResponse>).

Complete List of Live Endpoints Identified:
    - GET  /current-session
    - GET  /reference-data
    - GET  /getMatchingDivisions
    - GET  /getMatchingDepartments?term={term}&divisions={division}
    - GET  /getOptimizedMatchingCourseTitles?term={term}&divisions={division}&sessions={session}
    - GET  /getCoursesByCodeAndSectionCode/{courseCode}
    - GET  /getCoursesByCodeAndSectionCode/{courseCode}?sectionCode={sectionCode}
    - POST /getPageableCourses
    - POST /getCourses
    - POST /tiny/shorten
    - GET  /tiny/retrieve?id={id}
    - POST /generateYear
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Union


class TimetableBuilderAPI:
    """Client for interacting with the University of Toronto Timetable Builder (TTB) API."""

    BASE_URL: str = "https://api.easi.utoronto.ca/ttb"
    DEFAULT_TIMEOUT: int = 15
    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        """Initialize the Timetable Builder API client.

        Args:
            timeout: Network request timeout in seconds.
        """
        self.timeout = timeout

    def _request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Union[Dict[str, Any], List[Any], str, bytes]] = None,
        params: Optional[Dict[str, Any]] = None,
        content_type: str = "application/json",
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the TTB API and parse JSON response.

        Args:
            endpoint: URL path relative to BASE_URL (e.g. "/current-session").
            method: HTTP method ("GET" or "POST").
            data: Payload for POST requests (dict, list, string, or bytes).
            params: Query parameters for the request.
            content_type: Value for Content-Type header on POST requests.

        Returns:
            Parsed JSON response dictionary.

        Raises:
            urllib.error.HTTPError: When an HTTP error status is returned.
            urllib.error.URLError: When a connection or network error occurs.
            json.JSONDecodeError: When the server response is not valid JSON.
        """
        url = f"{self.BASE_URL}{endpoint}"
        if params:
            query_string = urllib.parse.urlencode(params)
            url = f"{url}?{query_string}"

        headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "application/json",
            "Origin": "https://ttb.utoronto.ca",
            "Referer": "https://ttb.utoronto.ca/",
        }

        body_bytes = None
        if data is not None and method.upper() == "POST":
            headers["Content-Type"] = content_type
            if isinstance(data, (dict, list)):
                body_bytes = json.dumps(data).encode("utf-8")
            elif isinstance(data, str):
                body_bytes = data.encode("utf-8")
            elif isinstance(data, bytes):
                body_bytes = data

        req = urllib.request.Request(
            url=url,
            data=body_bytes,
            headers=headers,
            method=method.upper(),
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            raw_data = response.read().decode("utf-8")
            return json.loads(raw_data)

    # -------------------------------------------------------------------------
    # Core GET Methods
    # -------------------------------------------------------------------------

    def get_current_session(self) -> Dict[str, Any]:
        """Fetch active academic sessions and session codes.

        Endpoint:
            GET /current-session

        Returns:
            Dictionary containing session options and labels (e.g., Fall, Winter).
        """
        return self._request("/current-session", method="GET")

    def get_reference_data(self) -> Dict[str, Any]:
        """Fetch global reference metadata.

        Endpoint:
            GET /reference-data

        Returns:
            Dictionary containing sessions, divisions, campuses, delivery modes,
            day/time preferences, credit weights, and sort directions.
        """
        return self._request("/reference-data", method="GET")

    def get_matching_divisions(self) -> List[Dict[str, Any]]:
        """Fetch all recognized university academic divisions.

        Endpoint:
            GET /getMatchingDivisions

        Returns:
            List of division dictionaries containing division labels and codes.
        """
        response = self._request("/getMatchingDivisions", method="GET")
        return response.get("payload", [])

    def get_matching_departments(
        self,
        term: str,
        division: str = "ARTSC",
    ) -> List[Dict[str, Any]]:
        """Search academic departments within a given division.

        Endpoint:
            GET /getMatchingDepartments?term={term}&divisions={division}

        Note:
            Both 'term' and 'divisions' query parameters are required by the server;
            omitting either results in an HTTP 404 response.

        Args:
            term: Department search keyword (e.g. "computer", "math", "history").
            division: Academic division code (e.g. "ARTSC", "APSC").

        Returns:
            List of matching department records.
        """
        params = {"term": term, "divisions": division}
        response = self._request("/getMatchingDepartments", method="GET", params=params)
        departments_dict = response.get("payload", {}).get("departments", {})
        results: List[Dict[str, Any]] = []
        for faculty_name, dept_list in departments_dict.items():
            results.extend(dept_list)
        return results

    def autocomplete_courses(
        self,
        term: str,
        division: str = "ARTSC",
        session: str = "20269",
        lower_threshold: int = 50,
        upper_threshold: int = 200,
    ) -> List[Dict[str, Any]]:
        """Fast autocomplete and keyword search for course titles and codes.

        Endpoint:
            GET /getOptimizedMatchingCourseTitles

        Args:
            term: Course code prefix or keyword (e.g. "CSC108", "MAT", "physics").
            division: Academic division code (e.g. "ARTSC").
            session: Session code (e.g. "20269" for Fall).
            lower_threshold: Minimum match count threshold (default: 50).
            upper_threshold: Maximum match count threshold (default: 200).

        Returns:
            List of matching course records with code, title, sectionCode, and rank.
        """
        params = {
            "term": term,
            "divisions": division,
            "sessions": session,
            "lowerThreshold": lower_threshold,
            "upperThreshold": upper_threshold,
        }
        response = self._request("/getOptimizedMatchingCourseTitles", method="GET", params=params)
        return response.get("payload", {}).get("codesAndTitles", [])

    def get_course_by_code(
        self,
        course_code: str,
        section_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve complete course details, meeting times, and rooms by course code.

        Endpoints:
            GET /getCoursesByCodeAndSectionCode/{courseCode}
            GET /getCoursesByCodeAndSectionCode/{courseCode}?sectionCode={sectionCode}

        Args:
            course_code: Course code (e.g. "CSC108H1", "MAT137Y1").
            section_code: Optional term section code ("F", "S", or "Y").

        Returns:
            List of course objects matching the code and section.
        """
        endpoint = f"/getCoursesByCodeAndSectionCode/{urllib.parse.quote(course_code)}"
        params = {"sectionCode": section_code} if section_code else None
        response = self._request(endpoint, method="GET", params=params)
        pageable = response.get("payload", {}).get("pageableCourse", {})
        return pageable.get("courses", [])

    def retrieve_shared_timetable(self, share_id: str) -> Dict[str, Any]:
        """Retrieve a saved timetable by its unique share ID.

        Endpoint:
            GET /tiny/retrieve?id={id}

        Args:
            share_id: Unique identifier generated when saving a timetable
                      (e.g. "6aa367989fb9f116ed9cb63e").

        Returns:
            Dictionary containing stored timetable data and creation timestamp.
        """
        params = {"id": share_id}
        return self._request("/tiny/retrieve", method="GET", params=params)

    # -------------------------------------------------------------------------
    # Core POST Methods
    # -------------------------------------------------------------------------

    def search_courses(
        self,
        query: str = "",
        division: str = "ARTSC",
        session: str = "20269",
        page: int = 1,
        page_size: int = 5,
        campuses: Optional[List[str]] = None,
        delivery_modes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Search timetable courses with pagination and full filtering criteria.

        Endpoint:
            POST /getPageableCourses

        Args:
            query: Course code or keyword (e.g. "CSC108", "Computer Science").
            division: Academic division code (e.g. "ARTSC", "APSC", "UTM", "UTSC").
            session: Session code (e.g. "20269" for Fall, "20271" for Winter).
            page: Page number starting at 1.
            page_size: Maximum number of courses per page.
            campuses: Optional list of campus filter strings.
            delivery_modes: Optional list of delivery mode filter strings.

        Returns:
            Dictionary containing pageable course records and metadata.
        """
        payload = {
            "courseCodeAndTitleProps": {
                "courseCode": "",
                "courseTitle": query.strip(),
                "courseSectionCode": "",
                "searchCourseDescription": bool(query.strip()),
            },
            "departmentProps": [],
            "campuses": campuses or [],
            "sessions": [session] if session else [],
            "requirementProps": [],
            "instructor": "",
            "courseLevels": [],
            "deliveryModes": delivery_modes or [],
            "dayPreferences": [],
            "timePreferences": [],
            "divisions": [division] if division else [],
            "creditWeights": [],
            "page": page,
            "pageSize": page_size,
            "direction": "asc",
        }
        return self._request("/getPageableCourses", method="POST", data=payload)

    def create_share_link(self, timetable_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Save a timetable configuration and generate a persistent share ID.

        Endpoint:
            POST /tiny/shorten

        Args:
            timetable_payload: Dictionary representing timetable sessions and course lists.

        Returns:
            Dictionary containing generated "id", "created" timestamp, and encoded payload.
        """
        raw_json = json.dumps(timetable_payload)
        url_encoded_body = urllib.parse.quote(raw_json)
        return self._request(
            "/tiny/shorten",
            method="POST",
            data=url_encoded_body,
            content_type="application/x-www-form-urlencoded",
        )

    def get_all_courses(self) -> List[Dict[str, Any]]:
        """Fetch the entire catalog of courses across all divisions and sessions.

        Endpoint:
            POST /getCourses

        Caution:
            This endpoint returns the complete course database (over 8,000 courses).
            Response payload is typically 30+ MB and may take 5-10 seconds to download.

        Returns:
            List of all course dictionaries.
        """
        response = self._request("/getCourses", method="POST", data={})
        return response.get("payload", [])

    # -------------------------------------------------------------------------
    # Health Check Method
    # -------------------------------------------------------------------------

    def check_health(self) -> Dict[str, Any]:
        """Check availability and responsiveness of the TTB service.

        Performs a lightweight GET request against /current-session and measures
        latency and status code.

        Returns:
            Dictionary containing:
                - service: Service display name
                - status: "Operational", "Degraded", or "Down"
                - http_status: HTTP response status code
                - latency_ms: Response time in milliseconds
                - checked_at: ISO 8601 UTC timestamp
                - error: Error message string if failed, else None
        """
        start_time = time.time()
        checked_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        try:
            res = self.get_current_session()
            elapsed_ms = int((time.time() - start_time) * 1000)

            if res and "payload" in res:
                return {
                    "service": "Timetable Builder (TTB)",
                    "status": "Operational",
                    "http_status": 200,
                    "latency_ms": elapsed_ms,
                    "checked_at": checked_at,
                    "error": None,
                }
            return {
                "service": "Timetable Builder (TTB)",
                "status": "Degraded",
                "http_status": 200,
                "latency_ms": elapsed_ms,
                "checked_at": checked_at,
                "error": "Response missing expected payload schema",
            }

        except urllib.error.HTTPError as err:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "service": "Timetable Builder (TTB)",
                "status": "Down" if err.code >= 500 else "Degraded",
                "http_status": err.code,
                "latency_ms": elapsed_ms,
                "checked_at": checked_at,
                "error": f"HTTP {err.code}: {err.reason}",
            }

        except Exception as err:
            elapsed_ms = int((time.time() - start_time) * 1000)
            return {
                "service": "Timetable Builder (TTB)",
                "status": "Down",
                "http_status": 0,
                "latency_ms": elapsed_ms,
                "checked_at": checked_at,
                "error": str(err),
            }

    # -------------------------------------------------------------------------
    # View / Formatter Methods
    # -------------------------------------------------------------------------

    def view_health(self) -> None:
        """Display a formatted status report for the Timetable Builder API."""
        report = self.check_health()
        print("=" * 60)
        print("TTB API Health Status Report")
        print("=" * 60)
        print(f"Service:     {report['service']}")
        print(f"Status:      [{report['status'].upper()}]")
        print(f"HTTP Code:   {report['http_status']}")
        print(f"Latency:     {report['latency_ms']} ms")
        print(f"Checked At:  {report['checked_at']}")
        if report["error"]:
            print(f"Error:       {report['error']}")
        print("=" * 60)

    def view_current_session(self) -> None:
        """Display active academic sessions in a human-readable format."""
        data = self.get_current_session()
        sessions = data.get("payload", [])
        print("-" * 60)
        print("Current Academic Sessions")
        print("-" * 60)
        for s in sessions:
            label = s.get("label", "N/A")
            val = s.get("value", "N/A")
            is_header = s.get("header", False)
            if is_header:
                print(f"Category: {label} (Value: {val})")
            else:
                print(f"  - {label:<25} [Code: {val}]")
        print("-" * 60)

    def view_divisions(self) -> None:
        """Display recognized university divisions in a table."""
        divisions = self.get_matching_divisions()
        print("-" * 75)
        print(f"{'Division Code':<15} | {'Division Name'}")
        print("-" * 75)
        for div in divisions:
            code = div.get("value", "N/A")
            name = div.get("label", "N/A")
            print(f"{code:<15} | {name}")
        print("-" * 75)

    def view_departments(self, term: str, division: str = "ARTSC") -> None:
        """Search and display academic departments within a division."""
        departments = self.get_matching_departments(term=term, division=division)
        print("-" * 75)
        print(f"Departments matching '{term}' in {division} ({len(departments)} found)")
        print("-" * 75)
        for dept in departments:
            name = dept.get("name", "N/A")
            code = dept.get("code", "N/A")
            dept_type = dept.get("type", "N/A")
            print(f"[{code}] {name} ({dept_type})")
        print("-" * 75)

    def view_autocomplete(
        self,
        term: str,
        division: str = "ARTSC",
        session: str = "20269",
    ) -> None:
        """Display instant autocomplete matches for course codes or titles."""
        matches = self.autocomplete_courses(term=term, division=division, session=session)
        print("-" * 75)
        print(f"Autocomplete matches for '{term}' in {division} ({len(matches)} found)")
        print("-" * 75)
        for m in matches[:8]:
            code = m.get("code", "N/A")
            section = m.get("sectionCode", "")
            name = m.get("name", "N/A")
            rank = m.get("rank", 0)
            print(f"  [{code}{section}] {name} (Rank: {rank})")
        if len(matches) > 8:
            print(f"  ... and {len(matches) - 8} more match(es)")
        print("-" * 75)

    def view_course_details(
        self,
        course_code: str,
        section_code: Optional[str] = None,
    ) -> None:
        """Display detailed course offering info including meeting times and rooms."""
        courses = self.get_course_by_code(course_code=course_code, section_code=section_code)
        print("=" * 75)
        print(f"Detailed Course Offerings: {course_code}" + (f" ({section_code})" if section_code else ""))
        print("=" * 75)
        if not courses:
            print("No course offerings found.")
            return

        for course in courses:
            code = course.get("code", "N/A")
            sec_code = course.get("sectionCode", "")
            name = course.get("name", "N/A")
            campus = course.get("campus", "N/A")
            sections = course.get("sections", [])
            print(f"Course:   {code}{sec_code} - {name}")
            print(f"Campus:   {campus}")
            print(f"Sections: {len(sections)} activity section(s)")
            print()

            for sec in sections:
                sec_name = sec.get("name", "N/A")
                sec_type = sec.get("type", "N/A")
                instructors = sec.get("instructors", [])
                inst_names = []
                for inst in instructors:
                    if isinstance(inst, dict):
                        fn = inst.get("firstName", "")
                        ln = inst.get("lastName", "")
                        full_name = f"{fn} {ln}".strip()
                        if full_name:
                            inst_names.append(full_name)
                    elif isinstance(inst, str):
                        inst_names.append(inst)

                inst_str = ", ".join(inst_names) if inst_names else "TBA"
                meetings = sec.get("meetingTimes", [])

                print(f"  Section {sec_name} ({sec_type}) | Instructor: {inst_str}")
                for m in meetings:
                    day = m.get("start", {}).get("day", "N/A")
                    bldg = m.get("building", {}).get("buildingCode", "")
                    room = m.get("building", {}).get("buildingRoomNumber", "")
                    loc = f"{bldg} {room}".strip() if (bldg or room) else "Online/TBA"
                    print(f"    * Day {day} | Location: {loc}")
            print("-" * 75)

    def view_courses(
        self,
        query: str = "",
        division: str = "ARTSC",
        session: str = "20269",
        page_size: int = 5,
    ) -> None:
        """Search and display course offerings in a readable summary format.

        Args:
            query: Course code or keyword filter (e.g. "CSC108", "Computer Science").
            division: Division code (e.g. "ARTSC").
            session: Session code (e.g. "20269").
            page_size: Number of courses to display.
        """
        result = self.search_courses(
            query=query,
            division=division,
            session=session,
            page=1,
            page_size=page_size,
        )

        pageable = result.get("payload", {}).get("pageableCourse", {})
        total = pageable.get("total", 0)
        courses = pageable.get("courses", [])

        print("-" * 75)
        print(f"Search Results for '{query or 'all'}': Found {total} courses (Showing top {len(courses)})")
        print("-" * 75)

        for course in courses:
            code = course.get("code", "N/A")
            section = course.get("sectionCode", "")
            name = course.get("name", "N/A")
            campus = course.get("campus", "N/A")
            sections = course.get("sections", [])

            print(f"[{code}{section}] {name} ({campus})")

            for sec in sections[:3]:
                sec_name = sec.get("name", "N/A")
                sec_type = sec.get("type", "N/A")
                meetings = sec.get("meetingTimes", [])
                meeting_strs = []
                for m in meetings:
                    bldg = m.get("building", {}).get("buildingCode", "")
                    room = m.get("building", {}).get("buildingRoomNumber", "")
                    loc = f"{bldg} {room}".strip() if (bldg or room) else "Online/TBA"
                    meeting_strs.append(loc)

                loc_summary = ", ".join(meeting_strs) if meeting_strs else "TBA"
                print(f"    * {sec_name} ({sec_type}) - Location: {loc_summary}")

            if len(sections) > 3:
                print(f"    * ... and {len(sections) - 3} more section(s)")
            print()


if __name__ == "__main__":
    client = TimetableBuilderAPI()

    # 1. Health Status Check
    client.view_health()
    print()

    # 2. View Active Academic Sessions
    client.view_current_session()
    print()

    # 3. View Divisions
    client.view_divisions()
    print()

    # 4. Search Departments (GET /getMatchingDepartments)
    client.view_departments(term="computer", division="ARTSC")
    print()

    # 5. Course Autocomplete (GET /getOptimizedMatchingCourseTitles)
    client.view_autocomplete(term="CSC", division="ARTSC", session="20269")
    print()

    # 6. Detailed Course by Code and Section (GET /getCoursesByCodeAndSectionCode/{code})
    client.view_course_details(course_code="CSC258H1", section_code="F")
    print()

    # 7. Timetable State Persistence (POST /tiny/shorten and GET /tiny/retrieve)
    print("Testing Timetable Shortener and Retrieval:")
    sample_timetable = {"sessions": ["20269"], "timetables": []}
    shorten_res = client.create_share_link(sample_timetable)
    share_id = shorten_res.get("id")
    print(f"Created Share ID: {share_id}")

    if share_id:
        retrieved = client.retrieve_shared_timetable(share_id)
        print(f"Retrieved Share Payload: {retrieved.get('url')}")
    print()
