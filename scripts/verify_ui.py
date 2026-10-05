"""End-to-end UI verification for NEXUS.

Drives the real interface in Chrome (via Playwright) through the signature demo
and asserts the agent's answers and the graph updates are visible on screen.
Screenshots are written to ``docs/screenshots``.

Usage (with the backend running on :8000 and serving the built frontend):
    backend/.venv/Scripts/python scripts/verify_ui.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("NEXUS_UI_URL", "http://127.0.0.1:8000")
ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)


def reset_graph() -> None:
    """Reseed so the run is deterministic (baseline must be HIGH, not CRITICAL)."""
    req = urllib.request.Request(
        f"{BASE_URL}/api/seed",
        data=json.dumps({"reset": True}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        stats = json.loads(resp.read())
    print(f"reseeded: {stats['nodes']} nodes / {stats['relationships']} relationships")


def main() -> int:
    console_errors: list[str] = []
    failures: list[str] = []

    reset_graph()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

        page.goto(BASE_URL, wait_until="networkidle")

        # 1. Shell renders and the graph is online.
        expect(page.get_by_text("GRAPH ONLINE")).to_be_visible(timeout=15_000)
        expect(page.get_by_text("Knowledge graph", exact=True)).to_be_visible()
        page.wait_for_timeout(2500)  # let the force simulation settle

        # The force graph is a <canvas>; make sure it actually painted nodes
        # rather than rendering an empty background.
        distinct_colors = page.evaluate(
            """() => {
                const c = document.querySelector('canvas');
                if (!c) return 0;
                const ctx = c.getContext('2d');
                const d = ctx.getImageData(0, 0, c.width, c.height).data;
                const seen = new Set();
                for (let i = 0; i < d.length; i += 4 * 499) {
                    seen.add(`${d[i]},${d[i+1]},${d[i+2]}`);
                }
                return seen.size;
            }"""
        )
        if distinct_colors < 5:
            failures.append(
                f"graph canvas looks empty (only {distinct_colors} distinct sampled colours)"
            )

        page.screenshot(path=str(SHOTS / "01-initial-graph.png"))

        # Suggestions live in the command panel; scope so graph nodes that
        # happen to share the same label cannot be clicked by mistake.
        suggestions = page.get_by_test_id("suggestions")

        # 2. Most dangerous unresolved incident.
        suggestions.get_by_role(
            "button", name="What is the most dangerous unresolved incident?", exact=True
        ).click()
        expect(page.get_by_text("INC-142", exact=False).first).to_be_visible(timeout=30_000)
        expect(page.get_by_text("HIGH", exact=False).first).to_be_visible()
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SHOTS / "02-most-dangerous.png"))

        # 3. Evidence path is rendered in the bottom panel.
        hops = page.locator("text=/AFFECTS|DEPENDS_ON|CAUSED/").count()
        if hops < 3:
            failures.append(f"evidence path did not render enough hops (found {hops})")
        page.screenshot(path=str(SHOTS / "03-evidence-path.png"))

        # 4. New information is written into the graph.
        suggestions.get_by_role("button", name="Checkout traffic increased 34%.", exact=True).click()
        expect(page.get_by_text("Stored in the graph", exact=False).first).to_be_visible(
            timeout=30_000
        )
        expect(page.get_by_text("Graph updated", exact=False).first).to_be_visible()
        page.wait_for_timeout(800)
        page.screenshot(path=str(SHOTS / "04-memory-write.png"))

        # 5. Re-evaluation changes the decision because the graph changed.
        suggestions.get_by_role("button", name="Re-evaluate the incident.", exact=True).click()
        expect(page.get_by_text("CRITICAL", exact=False).first).to_be_visible(timeout=30_000)
        expect(page.get_by_text("HUMAN REVIEW", exact=False).first).to_be_visible(timeout=15_000)
        page.wait_for_timeout(2000)
        page.screenshot(path=str(SHOTS / "05-reevaluated-critical.png"))

        # 6. Explain why the recommendation changed.
        suggestions.get_by_role(
            "button", name="Why did your recommendation change?", exact=True
        ).click()
        expect(page.get_by_text("delta of +20", exact=False).first).to_be_visible(timeout=30_000)
        expect(page.get_by_text("Decision changed", exact=False).first).to_be_visible(
            timeout=15_000
        )
        page.wait_for_timeout(1500)
        page.screenshot(path=str(SHOTS / "06-why-it-changed.png"))

        # 7. Observability panel exposes the real Cypher that ran.
        page.get_by_role("button", name="Decision trace / observability", exact=True).click()
        expect(page.get_by_text("Executed Cypher")).to_be_visible()
        expect(page.get_by_text("Retrieved relationships")).to_be_visible()
        page.wait_for_timeout(600)
        page.screenshot(path=str(SHOTS / "07-observability.png"))

        # 8. Clicking an entity opens the inspector.
        page.get_by_role("button", name="Evidence path", exact=True).click()
        first_hop = page.locator("button", has_text="Payment Service").first
        if first_hop.count() > 0:
            first_hop.click()
            expect(page.get_by_text("Entity inspector")).to_be_visible(timeout=15_000)
            page.wait_for_timeout(900)
            page.screenshot(path=str(SHOTS / "08-entity-inspector.png"))

        browser.close()

    print(f"screenshots written to {SHOTS}")
    if console_errors:
        print("\nBrowser console errors:")
        for e in console_errors[:20]:
            print("  -", e)
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    if console_errors:
        print("\nFAILED: browser console reported errors")
        return 1
    print("\nOK: signature demo verified in the browser")
    return 0


if __name__ == "__main__":
    sys.exit(main())
