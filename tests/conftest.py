from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def _available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _chrome_path() -> str | None:
    configured = os.environ.get("PLAYWRIGHT_CHROME_PATH")
    candidates = [
        configured,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


@pytest.fixture(scope="session")
def app_url():
    port = _available_port()
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{url}/api/health", timeout=1).is_success:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("The test server did not start.")
        yield url
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chrome_path(), headless=True)
        except Exception as error:
            pytest.fail(
                "Playwright could not launch a browser. Install one with "
                "`python -m playwright install chromium` or set PLAYWRIGHT_CHROME_PATH. "
                f"Details: {error}"
            )
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
    page.set_default_timeout(45_000)
    yield page
    page.close()
