"""Finish UTORauth Duo in a real browser so a one-time code can be entered.

Duo's current prompt is a JavaScript app on duosecurity.com, not a static
HTML form. A headed Chromium window is the reliable way to complete it
locally. GitHub Actions should not call this helper.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

DUO_WAIT_MS = 180_000

FETCH_JS = """async (url) => {
    const response = await fetch(url, {
        method: 'GET',
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


class DuoMfaError(RuntimeError):
    """Duo MFA could not be completed in the browser."""


@dataclass(frozen=True)
class DuoBrowserConfig:
    """Per-app settings for the post-Duo browser session."""

    success_url_pattern: str
    rest_path_fragment: str
    success_timeout_msg: str
    app_loaded_pattern: str | None = None

    @classmethod
    def degree_explorer(cls) -> DuoBrowserConfig:
        return cls(
            success_url_pattern=r"degreeexplorer\.utoronto\.ca/degreeExplorer(?!/rest)",
            app_loaded_pattern=r"degreeexplorer\.utoronto\.ca/degreeExplorer/.+",
            rest_path_fragment="/degreeExplorer/rest/",
            success_timeout_msg=(
                "Timed out waiting for Degree Explorer after Duo. "
                "Enter the passcode in the browser window and try again."
            ),
        )

    @classmethod
    def acorn(cls) -> DuoBrowserConfig:
        return cls(
            success_url_pattern=r"acorn\.utoronto\.ca",
            app_loaded_pattern=r"acorn\.utoronto\.ca/sws",
            rest_path_fragment="/sws/rest/",
            success_timeout_msg=(
                "Timed out waiting for ACORN after Duo. "
                "Enter the passcode in the browser window and try again."
            ),
        )


def complete_duo_in_browser(
    session: requests.Session,
    duo_url: str,
    mfa_code: str | None = None,
    utorid: str | None = None,
    password: str | None = None,
    rest_url: str | None = None,
    app_url: str | None = None,
    *,
    browser_config: DuoBrowserConfig | None = None,
    keep_open: bool = False,
    probe_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Open the Duo prompt and copy cookies back after MFA succeeds.

    Type a Duo Mobile passcode in the Chromium window, or approve a push.
    Optional mfa_code is filled when the passcode field is found.
    If rest_url is set, GET it from the same browser context after login.

    When keep_open is True the browser window stays up after authentication so
    additional probe_urls can be fetched from the live session. Press Enter in
    the terminal to close the browser and return.
    """
    config = browser_config or DuoBrowserConfig.degree_explorer()
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
                re.compile(config.success_url_pattern),
                timeout=DUO_WAIT_MS,
            )
        except PlaywrightTimeout as exc:
            browser.close()
            raise DuoMfaError(config.success_timeout_msg) from exc

        result = _fetch_rest_from_loaded_app(page, rest_url, app_url, config)
        _copy_playwright_cookies(context, session)

        urls_to_probe = list(probe_urls or [])
        already_fetched = rest_url if rest_url else None
        if already_fetched and already_fetched not in urls_to_probe:
            urls_to_probe.insert(0, already_fetched)
        skip_urls = {already_fetched} if already_fetched else set()
        probe_results = _probe_urls_in_browser(page, urls_to_probe, skip=skip_urls)
        if probe_results:
            result["probe_results"] = probe_results

        if keep_open:
            _print_session_summary(result)
            print("\nBrowser stays open so you can inspect the app or retry API calls.")
            print("Press Enter in this terminal to close the browser and continue...")
            try:
                input()
            except EOFError:
                page.wait_for_timeout(300_000)
        else:
            page.wait_for_timeout(2_000)

        browser.close()
        return result


def _probe_urls_in_browser(
    page: Any,
    urls: list[str],
    *,
    skip: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Fetch each URL from the authenticated browser context."""
    skip_urls = skip or set()
    results: dict[str, dict[str, Any]] = {}
    for url in urls:
        if url in skip_urls:
            continue
        results[url] = _browser_fetch_once(page, url)
    return results


def _browser_fetch_once(page: Any, url: str) -> dict[str, Any]:
    """Single fetch from the live browser session."""
    entry: dict[str, Any] = {
        "http_status": None,
        "content_type": None,
        "json": None,
        "error_text": None,
        "top_level_keys": None,
    }
    last: dict[str, Any] = {}
    for _ in range(3):
        last = page.evaluate(FETCH_JS, url)
        entry["http_status"] = last.get("status")
        entry["content_type"] = last.get("contentType")
        text = last.get("text") or ""
        if last.get("status") == 200:
            try:
                parsed = json.loads(text)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict):
                entry["json"] = parsed
                entry["top_level_keys"] = sorted(parsed.keys())
                entry["error_text"] = None
                return entry
            if isinstance(parsed, list):
                entry["json"] = parsed
                entry["top_level_keys"] = [f"[array len={len(parsed)}]"]
                entry["error_text"] = None
                return entry
        entry["error_text"] = text[:400]
        page.wait_for_timeout(1_500)
    return entry


def _print_session_summary(result: dict[str, Any]) -> None:
    print("\n--- Authenticated browser session ---")
    print(f"Final URL: {result.get('final_url')}")
    rest_calls = result.get("rest_calls") or []
    if rest_calls:
        print(f"Observed {len(rest_calls)} REST call(s) during page load:")
        for call in rest_calls:
            print(f"  {call['method']} {call['path']} -> HTTP {call['status']}")
    probe_results = result.get("probe_results") or {}
    for url, probe in probe_results.items():
        status = probe.get("http_status")
        keys = probe.get("top_level_keys")
        detail = f"keys={keys}" if keys else probe.get("error_text", "")[:80]
        print(f"Probe {url} -> HTTP {status} {detail}")


def _fetch_rest_from_loaded_app(
    page: Any,
    rest_url: str | None,
    app_url: str | None = None,
    config: DuoBrowserConfig | None = None,
) -> dict[str, Any]:
    """Wait for the app to redirect itself, record REST XHRs, then fetch JSON."""
    browser_config = config or DuoBrowserConfig.degree_explorer()
    result: dict[str, Any] = {
        "http_status": None,
        "content_type": None,
        "json": None,
        "error_text": None,
        "final_url": page.url,
        "rest_calls": [],
    }
    rest_calls: list[dict[str, Any]] = []
    rest_prefix = browser_config.rest_path_fragment

    def on_response(response: Any) -> None:
        url = response.url
        if rest_prefix not in url:
            return
        parsed = urlparse(url)
        path = parsed.path
        if rest_prefix in path:
            path = path.split(rest_prefix, 1)[1]
            path = "/" + path.lstrip("/")
        rest_calls.append(
            {
                "method": response.request.method,
                "path": path,
                "status": response.status,
            }
        )

    page.on("response", on_response)
    if browser_config.app_loaded_pattern:
        try:
            page.wait_for_url(
                re.compile(browser_config.app_loaded_pattern),
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

    probe = _browser_fetch_once(page, rest_url)
    result["http_status"] = probe.get("http_status")
    result["content_type"] = probe.get("content_type")
    result["json"] = probe.get("json")
    result["error_text"] = probe.get("error_text")
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
