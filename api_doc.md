# University of Toronto API Catalog

This document provides a technical reference of known University of Toronto APIs, endpoints, authentication schemes, and observed schemas.

---

## 1. Timetable Builder (TTB) API

Operated by U of T Enterprise Applications and Solutions Integration (EASI). Serves course timetable information, meeting times, room locations, and instructor assignments across all three campuses (St. George, UTM, UTSC).

- Base URL: `https://api.easi.utoronto.ca/ttb`
- Web UI: `https://ttb.utoronto.ca/`
- Authentication: None (Public, unauthenticated)
- Required Header: `Accept: application/json` (defaults to XML if omitted)
- JSON Schema Catalog: [`json/timetable_builder.json`](json/timetable_builder.json)

### Endpoint Table

| Method | Endpoint | Query / Path Parameters | Purpose | Status |
|---|---|---|---|---|
| GET | `/current-session` | None | Active academic sessions (e.g. Fall 2026, Winter 2027) | Verified 200 |
| GET | `/reference-data` | None | Master reference tables (divisions, campuses, delivery modes) | Verified 200 |
| GET | `/getMatchingDivisions` | None | Recognized faculty divisions (ARTSC, APSC, UTM, UTSC, etc.) | Verified 200 |
| GET | `/getMatchingDepartments` | `term` (string), `divisions` (string) | Department search within a faculty division | Verified 200 |
| GET | `/getOptimizedMatchingCourseTitles` | `term` (string), `divisions` (string), `sessions` (string) | Instant course search and autocomplete with relevance ranks | Verified 200 |
| GET | `/getCoursesByCodeAndSectionCode/{courseCode}` | `courseCode` (path), optional `sectionCode` (query: F/S/Y) | Full course details with instructors, meeting times, and rooms | Verified 200 |
| POST | `/getPageableCourses` | Filter body (JSON) | Primary faceted paginated course search engine | Verified 200 |
| POST | `/getCourses` | `{}` (empty JSON object) | Full course dump (over 8,100 active courses, ~30 MB) | Verified 200 |
| POST | `/tiny/shorten` | URL-encoded JSON timetable | Generates a persistent shareable ID for a saved timetable | Verified 200 |
| GET | `/tiny/retrieve` | `id` (string) | Retrieves saved timetable state by share ID | Verified 200 |
| POST | `/generateYear` | Course/activity selections (JSON array) | Automatic timetable conflict solver and generator | Active route |

---

## 2. Degree Explorer API

Internal student planning tool providing academic history, marks, and program progression tracking.

- Base URL: `https://degreeexplorer.utoronto.ca/degreeExplorer/rest`
- Web UI: `https://degreeexplorer.utoronto.ca/`
- Authentication: UTORid via UTORauth SAML SSO (`idpz.utorauth.utoronto.ca`)
- Official Developer Support: None (Internal web API)
- JSON Schema Catalog: [`json/degree_explorer.json`](json/degree_explorer.json)

### Endpoint Table

| Method | Endpoint | Auth Required | Unauthenticated Behavior | Purpose |
|---|---|---|---|---|
| GET | `/dxStudent/getAcademicHistory` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Student course history, session marks, and requirements |
| GET | `/dxStudent/getStudentData` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Current Status student payload |
| GET | `/dxStudent/getStudentRecord` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Current Status student record |
| GET | `/dxMenu/getStudentUserData` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Menu/session user payload |
| GET | `/dxMenu/getStudentMenu` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Student navigation menu |
| GET | `/messages/getMessages` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | UI string catalog (not a student inbox) |
| GET | `/dxMenu/getSessionTimeouts` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Session timeout settings |
| GET | `/dxPlanner/getPlanner` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Planner timelines and primary-plan flags |
| GET | `/dxPlanner/getCellDetails` | Yes (UTORid SSO) | HTTP 302 redirect to UTORauth | Planner cell details after a timeline click |

Write/POST routes are not catalogued yet.

---

## 3. ACORN Student Web Services API

U of T course enrolment portal. After UTORauth SAML login and Duo, the web app calls JSON GET routes under `/sws/rest`. This catalog covers verified reads only. Mutation routes (for example `/enrolment/course/modify`) are not documented and must not be called.

- Base URL: `https://acorn.utoronto.ca/sws/rest`
- Web UI: `https://acorn.utoronto.ca/sws`
- Authentication: UTORid via UTORauth SAML SSO (`idpz.utorauth.utoronto.ca`) plus Duo MFA
- Official Developer Support: None (Internal web API)
- JSON Schema Catalog: [`json/acorn.json`](json/acorn.json)
- Unauthenticated REST GETs return HTTP 302 to UTORauth
- Enrolment, financial, and identity payloads must never be logged or committed

Later enrolment GETs reuse `registrationParams` (and candidacy codes) from `GET /enrolment/eligible-registrations`. Meeting times live in `meetings[].times[]` (`day.dayCode`, `startTime`, `endTime`, `buildingCode`, `room`, `instructors`). Waitlist rank is on `waitlistRank` from `/enrolment/course/view`.

### Endpoint Table

| Method | Endpoint | Query / Path Parameters | Purpose | Status |
|---|---|---|---|---|
| GET | `/enrolment/eligible-registrations` | None | Active registrations and `registrationParams` bundle | Verified 200 |
| GET | `/enrolment/current-registrations` | None | Currently active registration records | Verified 200 |
| GET | `/enrolment/course/enrolled-courses` | `registrationParams` query fields (`postCode`, `sessionCode`, org codes, `yearOfStudy`, ...) | Enrolled / waitlisted / dropped buckets (`APP` / `WAIT` / `DROP`) | Verified 200 |
| GET | `/dashboard/courseRegistration/enrolledCourses` | None | Dashboard enrolled-course list | Verified 200 |
| GET | `/enrolment/plan` | `candidacyPostCode`, `candidacySessionCode`, `sessionCode` | Enrolment cart (planned, not enrolled) | Verified 200 |
| GET | `/enrolment/course/view` | Course + `registrationParams` (`courseCode`, `courseSessionCode`, `sectionCode`, ...) | Single-course detail, waitlist rank, space | Verified 200 |
| GET | `/enrolment/start-times` | None | Enrolment start times / windows | Verified 200 |
| GET | `/enrolment/posts-with-invite-status` | None | Program/POSt invitations | Verified 200 |
| GET | `/profile/studentRegistrationInfo` | None | Registration and financial-hold status | Verified 200 |
| GET | `/notification` | None | Inbox notifications and action notices | Verified 200 |
| GET | `/acorn-check-list/items` | None | Pre-enrolment checklist items | Verified 200 |
| GET | `/acorn-check-list/todos` | None | Dashboard checklist todos | Verified 200 |
| GET | `/financial-account/tuitionPrepayment` | None | Tuition prepayment status | Verified 200 |
| GET | `/fee-payment/tuitionFeeAdmissionDeposits` | None | Admission deposits (empty array observed) | Verified 200 |
| GET | `/net-cost-view` | None | Net cost / financial-aid session view | Verified 200 |
| GET | `/dashboard/finance/dentalOptOutSessionCode` | None | Dental plan opt-out session code | Verified 200 |
| GET | `/dashboard/eventCalendar/getDashboardEvents/TODAY` | None | Dashboard events for today | Verified 200 |
| GET | `/awards` | None | Awards and scholarships | Observed 500 |

Guessed paths that are **not** real routes (HTTP 404): `/enrolment/course/search-courses`, `/student/summary`.

---

## 4. Quercus / Canvas REST API (Tenant)

University of Toronto learning management system tenant operated on Instructure Canvas.

- Base URL: `https://q.utoronto.ca/api/v1`
- Web UI: `https://q.utoronto.ca/`
- Authentication: Canvas API Access Token (scoped to user account)
- Official Support: Vendor supported (Standard Canvas REST API)

### Common Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/users/self/profile` | Current authenticated user profile |
| GET | `/courses` | List of enrolled courses for current user |
| GET | `/courses/{course_id}/assignments` | Assignments for a given course |
| GET | `/courses/{course_id}/modules` | Course syllabus modules |
| GET | `/courses/{course_id}/files` | Course files and downloads |

---

## 5. TSpace / Scholaris DSpace REST API

Open-access research repository for University of Toronto research publications, theses, and papers.

- Base URL: `https://utoronto.scholaris.ca/server/api`
- Web UI: `https://utoronto.scholaris.ca/`
- Authentication: None for public repository reads
- Official Support: Consortium supported (Standard DSpace REST API)

### Common Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | DSpace API discovery root and HAL links |
| GET | `/core/communities` | Top-level academic departments and faculties |
| GET | `/core/collections` | Paper and thesis collections |
| GET | `/core/items` | Repository research items and metadata |

---

## 6. Borealis (U of T Dataverse)

Shared research data repository for University of Toronto datasets and research data.

- Base URL: `https://borealisdata.ca/api`
- Web UI: `https://borealisdata.ca/dataverse/toronto`
- Authentication: None for public dataset reads; API Token for authenticated deposits
- Official Support: Consortium supported (Standard Dataverse Native API)

### Common Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/dataverses/toronto` | U of T Dataverse collection metadata |
| GET | `/dataverses/toronto/contents` | Datasets and sub-dataverses |
| GET | `/datasets/{dataset_id}` | Dataset details, citations, and file list |
