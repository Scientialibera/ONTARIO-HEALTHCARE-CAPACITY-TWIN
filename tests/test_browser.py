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
    expect(page).to_have_title("Ontario Capacity Twin | Health System Planning")
    expect(page.locator(".eyebrow")).to_have_text("ONTARIO / HEALTH SYSTEM PLANNING")
    expect(page.locator('link[rel="icon"][href="/assets/favicon.svg?v=2"]')).to_have_count(1)
    expect(page.locator('link[rel="shortcut icon"]')).to_have_count(1)
    expect(page.locator(".leaflet-container")).to_be_visible()
    expect(page.locator("#metricCoverage")).to_have_text(re.compile(r"\d+\.\d%"))


def test_place_hospital_with_map_overlay(page, app_url):
    load_dashboard(page, app_url)
    place_hospital(page)
    expect(page.locator("#scenarioDelta")).to_be_visible()
    expect(page.locator("#hospitalSelect")).to_contain_text("Proposed acute-care hospital")
    expect(page.locator("#copyScenarioButton")).to_be_enabled()
    assert "lat=" in page.url and "lon=" in page.url
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("#scenarioStatus")).to_have_text("ACTIVE", timeout=60_000)
    expect(page.locator("#scenarioDelta")).to_be_visible()


def test_optimizer_returns_ranked_sites(page, app_url):
    load_dashboard(page, app_url)
    page.get_by_role("button", name="Find best candidate sites").click()
    expect(page.get_by_role("button", name="Optimizing Ontario demand…")).to_be_disabled()
    expect(page.locator("#activityPanel")).to_be_visible()
    expect(page.locator("#activityStage")).to_have_text("SITE OPTIMIZER")
    expect(page.locator("#recommendationList .reco-card")).to_have_count(5, timeout=75_000)
    expect(page.locator("#recommendationList .reco-card").first).to_contain_text("avg")
    expect(page.locator("#activityPanel")).to_be_hidden()


def test_responsive_control_and_detail_drawers(page, app_url):
    page.set_viewport_size({"width": 760, "height": 900})
    load_dashboard(page, app_url)
    page.get_by_role("button", name="Controls").click()
    expect(page.locator("#controlsPanel")).to_have_class(re.compile(r"\bopen\b"))
    page.keyboard.press("Escape")
    expect(page.locator("#controlsPanel")).not_to_have_class(re.compile(r"\bopen\b"))
    page.get_by_role("button", name="Toggle insights panel").click()
    expect(page.locator("#detailsPanel")).to_have_class(re.compile(r"\bopen\b"))
