"""Finish UTORauth Duo in a real browser so a one-time code can be entered.

Duo's current prompt is a JavaScript app on duosecurity.com, not a static
HTML form. A headed Chromium window is the reliable way to complete it
locally. GitHub Actions should not call this helper.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qsl, urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

DUO_WAIT_MS = 180_000
KEEP_OPEN_WAIT_MS = 900_000


class DuoMfaError(RuntimeError):
    """Duo MFA could not be completed in the browser."""


def complete_duo_in_browser(
    session: requests.Session,
    duo_url: str,
    mfa_code: str | None = None,
    utorid: str | None = None,
    password: str | None = None,
    rest_url: str | None = None,
    app_url: str | None = None,
    keep_open: bool = False,
    keep_open_timeout_ms: int | None = None,
    on_ready: Callable[[Any, Any, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Open the Duo prompt and copy cookies back after MFA succeeds.

    Type a Duo Mobile passcode in the Chromium window, or approve a push.
    Optional mfa_code is filled when the passcode field is found.
    If rest_url is set, GET it from the same browser context after login.
    If keep_open is true, Chromium stays up after login until the window is
    closed or KEEP_OPEN_WAIT_MS elapses. on_ready runs while it is still open.
    """
    code = (mfa_code or "").strip()

    try:
        playwright_cm = sync_playwright()
    except Exception as exc:
        raise DuoMfaError(
            "Playwright is required for Duo. Run: python -m playwright install chromium"
        ) from exc

    with playwright_cm as playwright:
        try:
            browser = playwright.chromium.launch(headless=False)
        except Exception as exc:
            raise DuoMfaError(
                "Chromium is not installed for Playwright. Run: python -m playwright install chromium"
            ) from exc
        context = browser.new_context()
        try:
            context.add_cookies(_requests_cookies_to_playwright(session, duo_url))
        except Exception:
            pass
        page = context.new_page()
        rest_calls: list[dict[str, Any]] = []
        page.on("response", lambda response: _record_rest_call(response, rest_calls))
        page.goto(duo_url, wait_until="domcontentloaded")
        if page.locator("#username").count() and utorid and password:
            page.fill("#username", utorid)
            page.fill("#password", password)
            page.locator("#login-btn").click()
            page.wait_for_timeout(2_000)
        if code:
            _try_submit_passcode(page, code)
        print("Complete Duo in the browser window (passcode or push). Waiting...")
        try:
            page.wait_for_url(
                re.compile(r"degreeexplorer\.utoronto\.ca/degreeExplorer(?!/rest)"),
                timeout=DUO_WAIT_MS,
            )
        except PlaywrightTimeout as exc:
            browser.close()
            raise DuoMfaError(
                "Timed out waiting for Degree Explorer after Duo. "
                "Enter the passcode in the browser window and try again."
            ) from exc
        result = _fetch_rest_from_loaded_app(page, rest_url, rest_calls)
        _copy_playwright_cookies(context, session)
        if on_ready is not None:
            on_ready(page, context, result)
        if keep_open:
            print(
                "Chromium is staying open. Click around Degree Explorer if you want; "
                "close the window when you are done."
            )
            try:
                wait_ms = KEEP_OPEN_WAIT_MS if keep_open_timeout_ms is None else keep_open_timeout_ms
                page.wait_for_event("close", timeout=wait_ms)
            except PlaywrightTimeout:
                print("Keep-open wait timed out; closing Chromium.")
            except Exception:
                pass
        else:
            page.wait_for_timeout(2_000)
        try:
            browser.close()
        except Exception:
            pass
        return result


def _record_rest_call(response: Any, rest_calls: list[dict[str, Any]]) -> None:
    """Append a PII-free record for a Degree Explorer REST response."""
    url = response.url
    if "/degreeExplorer/rest/" not in url:
        return
    parsed = urlparse(url)
    try:
        headers = response.headers
        content_type = (headers.get("content-type") or "").split(";")[0]
        method = response.request.method
    except Exception:
        return
    rest_calls.append(
        {
            "method": method,
            "path": parsed.path.replace("/degreeExplorer/rest", "", 1),
            "query_keys": sorted({key for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}),
            "status": response.status,
            "content_type": content_type,
        }
    )


def _fetch_rest_from_loaded_app(
    page: Any,
    rest_url: str | None,
    rest_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Wait for the app to redirect itself, then fetch JSON in the page."""
    result: dict[str, Any] = {
        "http_status": None,
        "content_type": None,
        "json": None,
        "error_text": None,
        "final_url": page.url,
        "rest_calls": rest_calls,
    }
    # The real site sends / or /degreeExplorer/ to currentStatus itself.
    try:
        page.wait_for_url(
            re.compile(r"degreeexplorer\.utoronto\.ca/degreeExplorer/.+"),
            timeout=15_000,
        )
    except PlaywrightTimeout:
        pass
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(5_000)
    result["final_url"] = page.url
    result["rest_calls"] = rest_calls
    if not rest_url:
        return result

    fetch_js = """async (url) => {
        const response = await fetch(url, {
            credentials: 'include',
            headers: { Accept: 'application/json' },
        });
        const text = await response.text();
        return {
            status: response.status,
            contentType: response.headers.get('content-type') || '',
            text: text,
        };
    }"""
    last: dict[str, Any] = {}
    for _ in range(5):
        last = page.evaluate(fetch_js, rest_url)
        result["http_status"] = last.get("status")
        result["content_type"] = last.get("contentType")
        text = last.get("text") or ""
        if last.get("status") == 200:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                result["json"] = parsed
                result["error_text"] = None
                return result
        result["error_text"] = text[:400]
        page.wait_for_timeout(1_500)
    return result


def _try_submit_passcode(page: Any, code: str) -> None:
    """Best-effort fill of Duo Mobile passcode. Ignore failures; the user can type."""
    try:
        page.get_by_text("Duo Mobile passcode", exact=False).click(timeout=8_000)
    except PlaywrightTimeout:
        try:
            page.get_by_text("passcode", exact=False).click(timeout=3_000)
        except PlaywrightTimeout:
            return
    try:
        box = page.locator("input[type='tel'], input[type='text'], input[inputmode='numeric']").last
        box.fill(code, timeout=5_000)
        page.get_by_role("button", name=re.compile(r"Verify|Continue|Submit|Log in", re.I)).click(timeout=5_000)
    except PlaywrightTimeout:
        return


def _requests_cookies_to_playwright(session: requests.Session, fallback_url: str) -> list[dict[str, object]]:
    fallback_host = urlparse(fallback_url).hostname or ""
    cookies: list[dict[str, object]] = []
    for cookie in session.cookies:
        domain = (cookie.domain or fallback_host).lstrip(".")
        if not domain:
            continue
        cookies.append(
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": domain,
                "path": cookie.path or "/",
                "secure": bool(cookie.secure),
                "httpOnly": True,
            }
        )
    return cookies


def _copy_playwright_cookies(context: Any, session: requests.Session) -> None:
    for cookie in context.cookies():
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain") or "",
            path=cookie.get("path") or "/",
        )
