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

---

## 3. Quercus / Canvas REST API (Tenant)

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

## 4. TSpace / Scholaris DSpace REST API

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

## 5. Borealis (U of T Dataverse)

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
