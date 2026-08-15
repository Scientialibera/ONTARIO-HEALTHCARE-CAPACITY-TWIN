"""Capture current dashboard and placed-facility screenshots for the README."""
from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOTS = ROOT / "docs" / "screenshots"
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
)


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def chrome_path() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


def wait_for_server(url: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{url}/api/health", timeout=1).is_success:
                return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError("The screenshot server did not start.")


def main() -> None:
    port = available_port()
    url = f"http://127.0.0.1:{port}"
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_server(url)
        SCREENSHOTS.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            browser_path = chrome_path()
            browser = playwright.chromium.launch(
                executable_path=str(browser_path) if browser_path else None,
                headless=True,
            )
            page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
            page.goto(url, wait_until="domcontentloaded")
            page.locator("#metricPopulation").wait_for(state="visible")
            page.wait_for_function("document.querySelector('#metricPopulation').textContent !== '—'")
            page.screenshot(path=SCREENSHOTS / "dashboard.png")

            page.get_by_role("button", name="Place new hospital").click()
            map_box = page.locator("#map").bounding_box()
            if map_box is None:
                raise RuntimeError("Map did not render for scenario screenshot.")
            page.mouse.click(map_box["x"] + map_box["width"] * 0.52, map_box["y"] + map_box["height"] * 0.53)
            page.locator("#scenarioStatus").wait_for(state="visible")
            page.wait_for_function("document.querySelector('#scenarioStatus').textContent === 'ACTIVE'")
            page.screenshot(path=SCREENSHOTS / "placed-facility.png")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
