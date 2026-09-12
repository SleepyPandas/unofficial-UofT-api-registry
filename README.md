# Unofficial UofT API Registry

> **Work in progress.** This registry is incomplete. Timetable Builder, Degree Explorer, and ACORN are health-checked so far. Endpoints here are unofficial unless marked otherwise. Do not treat this as a University of Toronto service.

A simple index and uptime monitor for University of Toronto APIs, machine-readable services, and data endpoints.

This tracks APIs that U of T uses which might be useful to students and developers. Reliability of those APIs is not guaranteed, and neither is this registry. It is a start.

> [!CAUTION]
> These endpoints are unofficial. They can break, move, or change shape without announcement. Paths, auth, and JSON fields may stop matching this catalog at any time.

## Overview

This repository catalogs known public and authenticated University of Toronto endpoints, documents their access requirements, and tracks availability with automated health checks.

Health checks run safe, read-only requests via GitHub Actions every 12 hours. For authenticated services, a login redirect (for example HTTP 302 to UTORauth) is enough to show the service is online. A successful logged-in GET can upgrade the badge to operational; a failed logged-in GET does not mark the service down if that redirect still works.

Student payloads are never published. The live status records HTTP codes, latency, and a short detail string only.

## Questions this repo answers

- What is the endpoint?
- What does it return?
- Does it currently work?
- Do you need authentication?
- Does U of T officially support it?

## API Registry

<!-- registry:start -->

<p>
  <a href="https://sleepypandas.github.io/unofficial-UofT-api-registry/status.json"><img alt="Last checked" height="32" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fsleepypandas.github.io%2Funofficial-UofT-api-registry%2Fbadges%2Fchecked-at.json&amp;style=for-the-badge"></a>
</p>

| Service | Status | Auth | Endpoint |
|---|---|---|---|
| Degree Explorer | <img alt="Degree Explorer status" height="28" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fsleepypandas.github.io%2Funofficial-UofT-api-registry%2Fbadges%2Fdegree-explorer.json&amp;style=for-the-badge"> | UTORid | [`/dxStudent/getAcademicHistory`](https://degreeexplorer.utoronto.ca/degreeExplorer/rest/dxStudent/getAcademicHistory) |
| ACORN | <img alt="ACORN status" height="28" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fsleepypandas.github.io%2Funofficial-UofT-api-registry%2Fbadges%2Facorn.json&amp;style=for-the-badge"> | UTORid | [`/enrolment/eligible-registrations`](https://acorn.utoronto.ca/sws/rest/enrolment/eligible-registrations) |
| Timetable Builder | <img alt="Timetable Builder status" height="28" src="https://img.shields.io/endpoint?url=https%3A%2F%2Fsleepypandas.github.io%2Funofficial-UofT-api-registry%2Fbadges%2Ftimetable-builder.json&amp;style=for-the-badge"> | None | [`/current-session`](https://api.easi.utoronto.ca/ttb/current-session) |

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

## ACORN

- Human UI: https://acorn.utoronto.ca/sws
- REST base: `https://acorn.utoronto.ca/sws/rest`
- Confirmed reads: `GET /enrolment/eligible-registrations`, `GET /enrolment/course/enrolled-courses`, `GET /enrolment/course/view`, plus dashboard finance/checklist/notification routes
- Auth: UTORid via UTORauth SAML (`idpz.utorauth.utoronto.ca`) plus Duo
- Official support: no. This is an internal web API used by the ACORN frontend. GET only; mutation routes are not cataloged.
- Detailed Catalog: [`json/acorn.json`](json/acorn.json)

Student enrolment and financial payloads are never published. Local helpers return counts and top-level keys only.

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

Degree Explorer and ACORN login hit Duo. A Chromium window opens. Enter a Duo Mobile passcode in the terminal or in that window (push also works). GitHub Actions cannot complete Duo, so the runner keeps the unauthenticated **auth required** probe unless you are testing locally.

## GitHub Actions

The workflow `.github/workflows/api-health.yml` runs every 12 hours and on manual dispatch.

Put `UOFT_UTORID` and `UOFT_PASSWORD` in **repository secrets** (Settings → Secrets and variables → Actions). This job has no GitHub Environment, so environment secrets are not read.

The names match `.env`. The runner can submit UTORid and password, but it cannot finish Duo, so Degree Explorer and ACORN stay **auth required** when the unauthenticated 302 is healthy. Do not add `UOFT_MFA_CODE` on GitHub.

The workflow publishes `status.json` and the badge endpoints as a GitHub Pages artifact. It does not commit generated status updates. Set **Settings → Pages → Source** to **GitHub Actions** once before the first deployment.

## Repository layout

```text
unofficial-UofT-api-registry/
|-- README.md
|-- api_doc.md
|-- data/
|   `-- apis.json
|-- json/
|   |-- acorn.json
|   |-- degree_explorer.json
|   `-- timetable_builder.json
|-- src/
|   |-- check_all_api.py
|   `-- apis/
|       |-- acorn.py
|       |-- degree_explorer.py
|       `-- timetable_builder.py
`-- .github/
    `-- workflows/
        `-- api-health.yml
```
