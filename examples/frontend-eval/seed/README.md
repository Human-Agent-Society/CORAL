# Rijksstudio voor Moderne Kunst — Landing Page

This is the starter repo for the frontend-eval task. The generator agent's job is to build a self-contained landing page for a fictional Dutch contemporary art museum.

## Output

- **`index.html`** is the entry point and MUST exist after the first successful eval.
- Add CSS/JS in any layout you like (`styles.css`, `script.js`, a `css/` directory, inline, whatever).
- Static assets (SVGs, images) live alongside the HTML.
- No build step — the evaluator serves the directory directly with a static HTTP server.

## What the evaluator does

For each `coral eval`, the grader:

1. Starts a local HTTP server serving this directory
2. Spawns an evaluator agent with Playwright MCP
3. The evaluator browses your page, takes screenshots, interacts with UI
4. Scores against 4 criteria (Design Quality 3x, Originality 3x, Craft 0.5x, Functionality 0.25x)
5. Writes detailed critique you can read in the attempt feedback

## Tips

- Use the `frontend-design` skill before writing any code — it's seeded into
  this worktree's skills.
- Read the previous eval's `overall_critique` before iterating — that's where the most actionable advice lives.
- The criteria reward *taste* and *originality*, not just polish. A rough but distinctive page can beat a polished generic one.
- If a direction isn't working after 2-3 attempts, pivot rather than micro-optimizing.
