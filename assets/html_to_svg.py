"""Convert coral_diagram_alphaevolve.html to SVG by wrapping a PNG screenshot in an <image> tag."""

import base64
from pathlib import Path

from playwright.sync_api import sync_playwright

HTML_FILE = Path(__file__).parent / "coral_diagram_alphaevolve.html"
SVG_FILE = HTML_FILE.with_suffix(".svg")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1020, "height": 800}, device_scale_factor=2)
    page.goto(HTML_FILE.as_uri())
    page.wait_for_timeout(1000)
    el = page.query_selector(".diagram")
    box = el.bounding_box()
    png_bytes = el.screenshot()
    browser.close()

w, h = int(box["width"]), int(box["height"])
b64 = base64.b64encode(png_bytes).decode()

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" '
    f'xmlns:xlink="http://www.w3.org/1999/xlink" '
    f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
    f'  <image width="{w}" height="{h}" '
    f'xlink:href="data:image/png;base64,{b64}"/>\n'
    f'</svg>\n'
)

SVG_FILE.write_text(svg)
print(f"Saved {SVG_FILE}")
