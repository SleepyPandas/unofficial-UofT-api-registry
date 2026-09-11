# Unofficial UofT API Registry

> **Work in progress.** This registry is incomplete. Only Timetable Builder and Degree Explorer are health-checked so far. Endpoints here are unofficial unless marked otherwise. Do not treat this as a University of Toronto service.

A simple index and uptime monitor for University of Toronto APIs, machine-readable services, and data endpoints.

This tracks APIs that U of T uses which might be useful to students and developers. Reliability of those APIs is not guaranteed, and neither is this registry. It is a start.

## Overview

This repository catalogs known public and authenticated University of Toronto endpoints, documents their access requirements, and tracks availability with automated health checks.

Health checks run safe, read-only requests via GitHub Actions every 12 hours. For authenticated services, a login redirect (for example HTTP 302 to UTORauth) is enough to show the service is online. A successful logged-in GET can upgrade the badge to operational; a failed logged-in GET does not mark the service down if that redirect still works.

Student payloads are never committed. Status files record HTTP codes, latency, and a short detail string only.

## Questions this repo answers

- What is the endpoint?
- What does it return?
- Does it currently work?
- Do you need authentication?
- Does U of T officially support it?

## API Registry

<!-- registry:start -->

_Last checked: 2026-09-11T03:25:23Z (UTC)._

| Service | Status | Auth | Method | Endpoint | Notes |
|---|---|---|---|---|---|
| Degree Explorer | ![auth required](https://img.shields.io/badge/auth_required-blue?style=for-the-badge) | UTORid | GET | [`/dxStudent/getAcademicHistory`](https://degreeexplorer.utoronto.ca/degreeExplorer/rest/dxStudent/getAcademicHistory) | Unofficial. Student academic history and planner. Undocumented internal web API, not a supported public contract. Open the site root; after UTORauth/Duo the app redirects to Current Status, then REST calls work from that session. |
| Timetable Builder (TTB) | ![operational](https://img.shields.io/badge/operational-brightgreen?style=for-the-badge) | None | GET | [`/current-session`](https://api.easi.utoronto.ca/ttb/current-session) | Unofficial. Course schedules, timetable sections, room assignments, and instructors. Public and unauthenticated. |

<!-- registry:end -->

## Status definitions

- ![operational](https://img.shields.io/badge/operational-brightgreen?style=for-the-badge) Endpoint responds with the expected status and a valid JSON shape after login.
- ![auth required](https://img.shields.io/badge/auth_required-blue?style=for-the-badge) Service is reachable and asks for UTORid (or another credential). The unauthenticated probe succeeded.
- ![degraded](https://img.shields.io/badge/degraded-yellow?style=for-the-badge) Service is responding, but the status or payload was unexpected.
- ![down](https://img.shields.io/badge/down-red?style=for-the-badge) Timeout, DNS failure, or an error from the host itself.
- ![deprecated](https://img.shields.io/badge/deprecated-lightgrey?style=for-the-badge) Known decommissioned or retired service.
- ![unknown](https://img.shields.io/badge/unknown-lightgrey?style=for-the-badge) Endpoint has not been tested yet.

## Degree Explorer

- Human UI: https://degreeexplorer.utoronto.ca/
- REST base: `https://degreeexplorer.utoronto.ca/degreeExplorer/rest`
- Confirmed read: `GET /dxStudent/getAcademicHistory`
- Auth: UTORid via UTORauth SAML (`idpz.utorauth.utoronto.ca`)
- Official support: no. This is an internal web API used by the Degree Explorer frontend.
- Detailed Catalog: [`json/degree_explorer.json`](json/degree_explorer.json)

`get_academic_history()` returns academic history JSON (facultyCourses, sessions, courses, marks). `view_academic_history()` returns counts and top-level keys only, so it is safe to print.

## Timetable Builder (TTB)

- Human UI: https://ttb.utoronto.ca/
- REST base: `https://api.easi.utoronto.ca/ttb`
- Confirmed read: `GET /current-session`, `GET /reference-data`, `GET /getCoursesByCodeAndSectionCode/{code}`
- Auth: None (Public and unauthenticated)
- Official support: no. This is the JSON API used by the official Timetable Builder frontend.
- Detailed Catalog: [`json/timetable_builder.json`](json/timetable_builder.json)

See [`api_doc.md`](api_doc.md) for the complete endpoint tables, parameters, and schemas.

## Local testing

1. Copy `.env.example` to `.env` if you do not already have `.env`.
2. Put your UTORid and password in `.env`. That file is gitignored.
3. Install dependencies, Chromium (needed for Duo), and run the checker:

```text
pip install -r requirements.txt
python -m playwright install chromium
python src/check_all_api.py
```

On Windows with the repo venv:

```text
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe src/check_all_api.py
```

Degree Explorer login hits Duo. A Chromium window opens. Enter a Duo Mobile passcode in the terminal or in that window (push also works). GitHub Actions cannot complete Duo, so the runner keeps the unauthenticated **auth required** probe unless you are testing locally.

## GitHub Actions

The workflow `.github/workflows/api-health.yml` runs every 12 hours and on manual dispatch.

Put `UOFT_UTORID` and `UOFT_PASSWORD` in **repository secrets** (Settings → Secrets and variables → Actions). This job has no GitHub Environment, so environment secrets are not read.

The names match `.env`. The runner can submit UTORid and password, but it cannot finish Duo, so Degree Explorer stays **auth required** when the unauthenticated 302 is healthy. Do not add `UOFT_MFA_CODE` on GitHub.

## Repository layout

```text
unofficial-UofT-api-registry/
|-- README.md
|-- api_doc.md
|-- data/
|   |-- apis.json
|   `-- status.json
|-- json/
|   |-- degree_explorer.json
|   `-- timetable_builder.json
|-- src/
|   `-- apis/
|       |-- degree_explorer.py
|       `-- timetable_builder.py
|-- scripts/
|   `-- check_apis.py
`-- .github/
    `-- workflows/
        `-- api-health.yml
```
