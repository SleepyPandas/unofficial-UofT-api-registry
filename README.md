# Unofficial UofT API Registry

A simple index and uptime monitor for University of Toronto APIs, machine-readable services, and data endpoints.

This is intended to track the APIs that UofT uses for things that might be useful, the reliability of APIs may not be guaranteed thus the reliability of this github repository. But it is a start.

## Overview

This repository catalogs known public and authenticated University of Toronto endpoints, documents their access requirements, and tracks their availability via automated daily health checks.

Daily health checks run safe, read-only requests via GitHub Actions. Services are evaluated against expected response codes (for example, a 401 response on an authenticated endpoint confirms the service is online and reachable).

## API Registry

| Service | Status | Auth | Method | Endpoint / Docs | Notes |
|---|---|---|---|---|---|
| Timetable Builder (TTB) | Operational | None | GET | [Endpoint Placeholder] | Course schedules and listings |
| Quercus (Canvas LMS) | Auth Required | API Token | GET | [Endpoint Placeholder] | Canvas REST API |
| Degree Explorer | Auth Required | UTORid | GET | [Endpoint Placeholder] | Academic history and planner |
| ACORN | Auth Required | UTORid + MFA | GET | [Endpoint Placeholder] | Student records and enrolment |
| TSpace | Operational | None | GET | [Endpoint Placeholder] | Research repository |
| Borealis | Operational | None | GET | [Endpoint Placeholder] | Dataverse research data repository |
| Cobalt | Deprecated | None | N/A | [Archived Docs] | Legacy community API (offline) |

## Status Definitions

- Operational: Endpoint responds with expected status and valid schema.
- Auth Required: Service is reachable and functional, but requires user credentials or an API token.
- Degraded: Service is responding, but returns unexpected status codes or payloads.
- Down: Endpoint timed out, encountered DNS failure, or returned 5xx errors.
- Deprecated: Known decommissioned or retired service.
- Unknown: Endpoint cannot be safely checked automatically or has not been tested.

## Planned Repository Structure

```text
unofficial-UofT-api-registry/
|-- README.md
|-- data/
|   |-- apis.json
|   `-- status.json
|-- scripts/
|   `-- check-apis.py
`-- .github/
    `-- workflows/
        `-- api-health.yml
```

