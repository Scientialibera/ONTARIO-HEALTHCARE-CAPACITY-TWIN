from __future__ import annotations

import re

from playwright.sync_api import expect


def load_dashboard(page, app_url):
    page.goto(app_url, wait_until="domcontentloaded")
    expect(page.locator("#map")).to_be_visible()
    expect(page.locator("#metricPopulation")).not_to_have_text("—", timeout=30_000)
    expect(page.locator("#topScope")).to_contain_text("hospital sites", timeout=30_000)


def place_hospital(page):
    page.get_by_role("button", name="Place new hospital").click()
    expect(page.get_by_role("button", name="Click map to place")).to_be_visible()
    map_box = page.locator("#map").bounding_box()
    assert map_box is not None
    page.mouse.click(map_box["x"] + map_box["width"] * 0.52, map_box["y"] + map_box["height"] * 0.53)
    expect(page.locator("#scenarioStatus")).to_have_text("ACTIVE", timeout=45_000)
    expect(page.locator("#metricShifted")).not_to_have_text("—")


def test_dashboard_loads_with_live_model(page, app_url):
    load_dashboard(page, app_url)
    expect(page.locator(".leaflet-container")).to_be_visible()
    expect(page.locator("#metricCoverage")).to_have_text(re.compile(r"\d+\.\d%"))


def test_place_hospital_with_map_overlay(page, app_url):
    load_dashboard(page, app_url)
    place_hospital(page)
    expect(page.locator("#scenarioDelta")).to_be_visible()
    expect(page.locator("#hospitalSelect")).to_contain_text("Proposed acute-care hospital")


def test_optimizer_returns_ranked_sites(page, app_url):
    load_dashboard(page, app_url)
    page.get_by_role("button", name="Find best candidate sites").click()
    expect(page.get_by_role("button", name="Optimizing Ontario demand…")).to_be_disabled()
    expect(page.locator("#recommendationList .reco-card")).to_have_count(5, timeout=75_000)
    expect(page.locator("#recommendationList .reco-card").first).to_contain_text("avg")
