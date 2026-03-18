"""Convert coral_diagram_alphaevolve.html to PNG using Playwright."""

from pathlib import Path
from playwright.sync_api import sync_playwright

HTML_FILE = Path(__file__).parent / "coral_diagram_alphaevolve.html"
PNG_FILE = HTML_FILE.with_suffix(".png")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1020, "height": 800})
    page.goto(HTML_FILE.as_uri())
    page.wait_for_timeout(1000)
    page.query_selector(".diagram").screenshot(path=str(PNG_FILE))
    browser.close()

print(f"Saved {PNG_FILE}")
