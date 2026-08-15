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
BASE_CALLOUTS = (
    ("#controlsPanel", 1),
    (".metric-strip", 2),
    (".map-toolbar", 3),
    ("#mapFrame", 4),
    ("#detailsPanel", 5),
    (".topbar-actions", 6),
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


def add_callouts(page, *, include_scenario: bool = False) -> None:
    """Overlay numbered documentation callouts without changing the app."""
    callouts = list(BASE_CALLOUTS)
    if include_scenario:
        callouts.append(("#scenarioDelta", 7))
    page.evaluate(
        """
        callouts => {
          document.querySelectorAll('[data-doc-callout]').forEach(node => node.remove());
          for (const [selector, number] of callouts) {
            const target = document.querySelector(selector);
            if (!target) continue;
            const rect = target.getBoundingClientRect();
            if (!rect.width || !rect.height) continue;

            const box = document.createElement('div');
            box.dataset.docCallout = number;
            Object.assign(box.style, {
              position: 'fixed', left: `${rect.left + 3}px`, top: `${rect.top + 3}px`,
              width: `${Math.max(0, rect.width - 6)}px`, height: `${Math.max(0, rect.height - 6)}px`,
              border: '2px solid #075fca', borderRadius: '9px', boxSizing: 'border-box',
              boxShadow: '0 0 0 3px rgba(7,95,202,.14)', pointerEvents: 'none', zIndex: '20000'
            });

            const marker = document.createElement('div');
            marker.dataset.docCallout = number;
            marker.textContent = number;
            Object.assign(marker.style, {
              position: 'fixed', left: `${Math.max(6, rect.left + 10)}px`,
              top: `${Math.max(6, rect.top + 10)}px`, width: '28px', height: '28px',
              borderRadius: '7px', display: 'grid', placeItems: 'center',
              background: '#075fca', color: '#fff', border: '2px solid #fff',
              boxShadow: '0 4px 12px rgba(7,54,104,.3)', font: '800 14px Inter, sans-serif',
              pointerEvents: 'none', zIndex: '20001'
            });
            document.body.append(box, marker);
          }
        }
        """,
        callouts,
    )


def clear_callouts(page) -> None:
    page.evaluate("document.querySelectorAll('[data-doc-callout]').forEach(node => node.remove())")


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
            add_callouts(page)
            page.screenshot(path=SCREENSHOTS / "dashboard.png")
            clear_callouts(page)

            page.get_by_role("button", name="Place new hospital").click()
            map_box = page.locator("#map").bounding_box()
            if map_box is None:
                raise RuntimeError("Map did not render for scenario screenshot.")
            page.mouse.click(map_box["x"] + map_box["width"] * 0.52, map_box["y"] + map_box["height"] * 0.53)
            page.locator("#scenarioStatus").wait_for(state="visible")
            page.wait_for_function("document.querySelector('#scenarioStatus').textContent === 'ACTIVE'")
            add_callouts(page, include_scenario=True)
            page.screenshot(path=SCREENSHOTS / "placed-facility.png")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
