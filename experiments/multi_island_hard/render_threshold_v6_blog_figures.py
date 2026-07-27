"""Render the registered multi-island v6 results used by the research blog.

The renderer deliberately uses only the Python standard library.  The source
JSON files are the registered analysis artifacts; SVG and CSV are presentation
derivatives and can be regenerated with::

    uv run python experiments/multi_island_hard/render_threshold_v6_blog_figures.py

The figures are small, self-contained SVGs so the published blog has no
runtime plotting dependency.
"""

from __future__ import annotations

import csv
import html
import json
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent
OUT = ROOT / "blog"

BG = "#FFFFFF"
INK = "#1D2939"
MUTED = "#667085"
GRID = "#EAECF0"
GLOBAL = "#667085"
PARTITION = "#D97706"
MULTI = "#0F766E"
DISCOVERY = "#7C3AED"
CONFIRMATION = "#2563EB"
FOLLOWUP = "#0F766E"


def read_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}".replace("-0.00", "0.00")


def svg_document(width: int, height: int, title: str, description: str, body: Iterable[str]) -> str:
    return "\n".join(
        [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{esc(title)}</title>',
            f'<desc id="desc">{esc(description)}</desc>',
            '<style>text{font-family:Arial,Helvetica,sans-serif;fill:#1D2939} .small{font-size:11px} .label{font-size:12px;font-weight:600} .muted{fill:#667085} .grid{stroke:#EAECF0;stroke-width:1} .axis{stroke:#98A2B3;stroke-width:1} .value{font-size:12px;font-weight:600} .note{font-size:10px;fill:#667085}</style>',
            *body,
            "</svg>",
            "",
        ]
    )


def mix(start: tuple[int, int, int], end: tuple[int, int, int], amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    rgb = tuple(round(a + (b - a) * amount) for a, b in zip(start, end))
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def diverging(value: float, low: float, high: float) -> str:
    if value < 0:
        return mix((255, 247, 237), (217, 119, 6), min(1.0, abs(value) / max(abs(low), 1e-9)))
    return mix((240, 253, 250), (15, 118, 110), min(1.0, value / max(high, 1e-9)))


def phase_surface(phase: dict) -> str:
    rows = phase["rugged_phase_map"]
    ks = [32, 64, 96, 120]
    budgets = [16384, 32768, 65536]
    panels = [
        ("Multi − global", "multi_minus_global", 0.0, 0.5),
        ("Multi − partition", "multi_minus_partition", -0.05, 0.16),
    ]
    width, height = 820, 490
    body: list[str] = [
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        '<text x="410" y="25" text-anchor="middle" class="label">Exploratory rugged-landscape phase surface (random-reference SD)</text>',
        '<text x="410" y="43" text-anchor="middle" class="note">Each cell is a fresh paired block; outline = both effect gates pass, × = progress gate fails</text>',
    ]
    for panel_idx, (title, key, low, high) in enumerate(panels):
        left = 55 + panel_idx * 395
        top = 80
        cell_w, cell_h = 88, 62
        body.append(f'<text x="{left + 145}" y="66" text-anchor="middle" class="label">{esc(title)}</text>')
        body.append(f'<text x="{left + 145}" y="{top + 4 * cell_h + 31}" text-anchor="middle" class="small muted">budget</text>')
        body.append(f'<text x="{left - 22}" y="{top + 2 * cell_h}" text-anchor="middle" transform="rotate(-90 {left - 22} {top + 2 * cell_h})" class="small muted">ruggedness K</text>')
        for col, budget in enumerate(budgets):
            x = left + col * cell_w
            body.append(f'<text x="{x + cell_w / 2}" y="{top - 12}" text-anchor="middle" class="small muted">B={budget // 1024}k</text>')
            body.append(f'<line x1="{x}" y1="{top}" x2="{x}" y2="{top + len(ks) * cell_h}" class="grid"/>')
        for row_idx, k in enumerate(ks):
            y = top + row_idx * cell_h
            body.append(f'<text x="{left - 8}" y="{y + cell_h / 2 + 4}" text-anchor="end" class="small muted">{k}</text>')
            body.append(f'<line x1="{left}" y1="{y}" x2="{left + len(budgets) * cell_w}" y2="{y}" class="grid"/>')
            for col, budget in enumerate(budgets):
                row = next(item for item in rows if item["k"] == k and item["budget"] == budget)
                contrast = row["contrasts"][key]
                value = contrast["mean_random_z_difference"]
                x = left + col * cell_w
                fill = diverging(value, low, high)
                stroke = INK if row["passes"] else "#FFFFFF"
                stroke_width = 2.5 if row["passes"] else 1
                body.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell_w - 2}" height="{cell_h - 2}" rx="5" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width}"/>')
                text_fill = "#FFFFFF" if value > high * 0.58 else INK
                body.append(f'<text x="{x + cell_w / 2}" y="{y + cell_h / 2 + 4}" text-anchor="middle" class="value" style="fill:{text_fill}">{fmt(value, 2)}</text>')
                if not row["search_progress_gate"]:
                    body.append(f'<text x="{x + cell_w - 10}" y="{y + 15}" text-anchor="middle" style="font-size:16px;fill:#B42318">×</text>')
        legend_y = top + 4 * cell_h + 52
        body.append(f'<rect x="{left}" y="{legend_y}" width="12" height="12" rx="2" fill="{MULTI}"/><text x="{left + 18}" y="{legend_y + 10}" class="note">positive multi effect</text>')
        body.append(f'<rect x="{left + 135}" y="{legend_y}" width="12" height="12" rx="2" fill="{PARTITION}"/><text x="{left + 153}" y="{legend_y + 10}" class="note">negative effect</text>')
        body.append(f'<rect x="{left + 260}" y="{legend_y - 1}" width="14" height="14" rx="3" fill="none" stroke="{INK}" stroke-width="2"/><text x="{left + 281}" y="{legend_y + 10}" class="note">full-pass cell</text>')
    body.append('<text x="410" y="473" text-anchor="middle" class="note">The apparent positive region is concentrated at K=32; it is a discovery surface, not a pooled estimate.</text>')
    return svg_document(width, height, "Exploratory rugged-landscape phase surface", "Heatmaps show multi-island minus global and multi-island minus partition effects in random-reference standard deviations across ruggedness and budget.", body)


def forest_plot(confirmation: dict, followup: dict, phase: dict) -> str:
    rows = []
    for budget in (32768, 65536):
        source = next(item for item in phase["rugged_phase_map"] if item["k"] == 32 and item["budget"] == budget)
        for key, label in (("multi_minus_global", "multi − global"), ("multi_minus_partition", "multi − partition")):
            c = source["contrasts"][key]
            rows.append({"stage": "Discovery", "budget": budget, "key": key, "label": label, "mean": c["mean_random_z_difference"], "lo": c["descriptive_random_z_ci"][0], "hi": c["descriptive_random_z_ci"][1], "color": DISCOVERY})
    source = confirmation["contrasts"]
    for key, label in (("multi_minus_global", "multi − global"), ("multi_minus_partition", "multi − partition")):
        c = source[key]
        rows.append({"stage": "Independent confirmation", "budget": 65536, "key": key, "label": label, "mean": c["mean_random_z_difference"], "lo": c["descriptive_random_z_ci"][0], "hi": c["descriptive_random_z_ci"][1], "color": CONFIRMATION})
    for cell in followup["cells"]:
        for key, label in (("multi_minus_global", "multi − global"), ("multi_minus_partition", "multi − partition")):
            c = cell["contrasts"][key]
            rows.append({"stage": "Sequential follow-up", "budget": cell["budget"], "key": key, "label": label, "mean": c["mean_random_z_difference"], "lo": c["descriptive_random_z_ci"][0], "hi": c["descriptive_random_z_ci"][1], "color": FOLLOWUP})
    width, height = 820, 500
    body: list[str] = [
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        '<text x="410" y="25" text-anchor="middle" class="label">Selected-cell effect estimates and fresh replications</text>',
        '<text x="410" y="43" text-anchor="middle" class="note">K=32; points are means and whiskers are descriptive 95% CIs (each replication n=192 paired blocks)</text>',
    ]
    panels = [("multi_minus_global", "Multi − global", 0.25, 0.58), ("multi_minus_partition", "Multi − partition", 0.10, 0.28)]
    for idx, (key, title, floor, xmax) in enumerate(panels):
        left = 65 + idx * 390
        right = left + 320
        top = 91
        body.append(f'<text x="{left + 160}" y="68" text-anchor="middle" class="label">{title}</text>')
        for tick in (-0.1, 0.0, floor, xmax):
            x = left + (tick + 0.1) / (xmax + 0.1) * 320
            body.append(f'<line x1="{x:.1f}" y1="{top - 5}" x2="{x:.1f}" y2="{top + 5 * 52 + 5}" class="grid"/>')
            body.append(f'<text x="{x:.1f}" y="{top + 5 * 52 + 23}" text-anchor="middle" class="small muted">{fmt(tick, 2)}</text>')
        floor_x = left + (floor + 0.1) / (xmax + 0.1) * 320
        body.append(f'<line x1="{floor_x:.1f}" y1="{top - 8}" x2="{floor_x:.1f}" y2="{top + 5 * 52 + 5}" stroke="#B42318" stroke-width="1.5" stroke-dasharray="4 3"/>')
        body.append(f'<text x="{floor_x + 4:.1f}" y="{top - 11}" class="note" style="fill:#B42318">floor {floor:.2f}</text>')
        subset = [row for row in rows if row["key"] == key]
        for row_idx, row in enumerate(subset):
            y = top + row_idx * 52 + 20
            x0 = left + (row["lo"] + 0.1) / (xmax + 0.1) * 320
            x1 = left + (row["hi"] + 0.1) / (xmax + 0.1) * 320
            xm = left + (row["mean"] + 0.1) / (xmax + 0.1) * 320
            body.append(f'<line x1="{left}" y1="{y + 17}" x2="{right}" y2="{y + 17}" class="grid"/>')
            body.append(f'<line x1="{x0:.1f}" y1="{y}" x2="{x1:.1f}" y2="{y}" stroke="{row["color"]}" stroke-width="3" stroke-linecap="round"/>')
            body.append(f'<line x1="{x0:.1f}" y1="{y - 6}" x2="{x0:.1f}" y2="{y + 6}" stroke="{row["color"]}" stroke-width="1.5"/><line x1="{x1:.1f}" y1="{y - 6}" x2="{x1:.1f}" y2="{y + 6}" stroke="{row["color"]}" stroke-width="1.5"/>')
            body.append(f'<circle cx="{xm:.1f}" cy="{y}" r="5" fill="{row["color"]}" stroke="#FFFFFF" stroke-width="1.5"/>')
            stage = {"Discovery": "Disc.", "Independent confirmation": "Confirm.", "Sequential follow-up": "Follow-up"}[row["stage"]]
            body.append(f'<text x="{left - 9}" y="{y + 4}" text-anchor="end" class="small">{esc(stage)} · B={row["budget"] // 1024}k</text>')
            body.append(f'<text x="{xm + 8:.1f}" y="{y - 8}" class="note">{fmt(row["mean"], 2)}</text>')
        body.append(f'<text x="{left + 160}" y="{top + 5 * 52 + 43}" text-anchor="middle" class="small muted">effect in random-reference SD</text>')
    body.extend([
        f'<circle cx="82" cy="475" r="5" fill="{DISCOVERY}"/><text x="92" y="479" class="note">discovery</text>',
        f'<circle cx="164" cy="475" r="5" fill="{CONFIRMATION}"/><text x="174" y="479" class="note">independent confirmation</text>',
        f'<circle cx="327" cy="475" r="5" fill="{FOLLOWUP}"/><text x="337" y="479" class="note">outcome-aware sequential follow-up</text>',
    ])
    return svg_document(width, height, "Selected-cell effect estimates and fresh replications", "Forest plots compare discovery, independent confirmation, and outcome-aware sequential follow-up effects against practical floors.", body)


def smooth_surface(phase: dict) -> str:
    rows = phase["smooth_phase_map"]
    ns = [2048, 4096, 8192]
    budgets = [16384, 32768, 65536]
    width, height = 550, 330
    left, top, cell_w, cell_h = 92, 72, 110, 58
    values = [row["mean_global_minus_multi_prefix"] for row in rows]
    vmax = max(values)
    body: list[str] = [
        '<rect width="100%" height="100%" fill="#FFFFFF"/>',
        '<text x="275" y="25" text-anchor="middle" class="label">Hard smooth control: global − multi prefix score</text>',
        '<text x="275" y="43" text-anchor="middle" class="note">All 9 cells remain unsolved: 0/64 exact solutions in every topology/cell</text>',
    ]
    for col, budget in enumerate(budgets):
        x = left + col * cell_w
        body.append(f'<text x="{x + cell_w / 2}" y="{top - 12}" text-anchor="middle" class="small muted">B={budget // 1024}k</text>')
    for row_idx, n in enumerate(ns):
        y = top + row_idx * cell_h
        body.append(f'<text x="{left - 10}" y="{y + cell_h / 2 + 4}" text-anchor="end" class="small muted">N={n}</text>')
        for col, budget in enumerate(budgets):
            row = next(item for item in rows if item["n"] == n and item["budget"] == budget)
            value = row["mean_global_minus_multi_prefix"]
            x = left + col * cell_w
            fill = mix((239, 246, 255), (37, 99, 235), value / vmax)
            body.append(f'<rect x="{x + 1}" y="{y + 1}" width="{cell_w - 2}" height="{cell_h - 2}" rx="5" fill="{fill}" stroke="#FFFFFF" stroke-width="2"/>')
            text_fill = "#FFFFFF" if value > vmax * 0.56 else INK
            body.append(f'<text x="{x + cell_w / 2}" y="{y + cell_h / 2 + 4}" text-anchor="middle" class="value" style="fill:{text_fill}">{fmt(value, 2)}</text>')
    body.append(f'<text x="{left + 165}" y="{top + 3 * cell_h + 32}" text-anchor="middle" class="small muted">mean best-prefix difference (score units)</text>')
    return svg_document(width, height, "Hard smooth control", "Heatmap of the global minus multi-island mean best-prefix score difference for the three hard smooth sizes and budgets.", body)


def rows_for_csv(construct: dict, phase: dict, confirmation: dict, followup: dict) -> tuple[list[str], list[dict[str, object]]]:
    rows: list[dict[str, object]] = []
    fields = ["study", "stage", "condition", "n", "k", "budget", "comparison", "metric", "effect", "ci_low", "ci_high", "one_sided_lower", "practical_floor", "passes", "progress_gate", "blocks", "notes"]

    for row in construct["smooth_scale"]:
        rows.append({"study": "extreme-v6", "stage": "construct", "condition": "smooth", "n": row["n"], "k": "", "budget": row["budget"], "comparison": "construct-validity", "metric": "budget_over_n2", "effect": row["budget_over_n_squared"], "ci_low": "", "ci_high": "", "one_sided_lower": "", "practical_floor": "", "passes": construct["construct_gates"]["construct_validity_passes"], "progress_gate": "", "blocks": 1, "notes": "one strict one-bit local optimum; unique global optimum"})
    for row in construct["rugged_summary"]:
        rows.append({"study": "extreme-v6", "stage": "construct", "condition": "rugged", "n": "", "k": row["k"], "budget": "", "comparison": "construct-validity", "metric": "one_bit_autocorrelation", "effect": row["mean_one_bit_autocorrelation"], "ci_low": "", "ci_high": "", "one_sided_lower": "", "practical_floor": "", "passes": construct["construct_gates"]["construct_validity_passes"], "progress_gate": "", "blocks": row["blocks"], "notes": f'affected fraction={row["affected_fraction"]:.6f}'})
    for row in phase["smooth_phase_map"]:
        rows.append({"study": "extreme-v6", "stage": "discovery", "condition": "smooth", "n": row["n"], "k": "", "budget": row["budget"], "comparison": "global-minus-multi", "metric": "mean_best_prefix", "effect": row["mean_global_minus_multi_prefix"], "ci_low": row["descriptive_global_minus_multi_prefix_ci"][0], "ci_high": row["descriptive_global_minus_multi_prefix_ci"][1], "one_sided_lower": row["multiplicity_controlled_global_minus_multi_prefix_lower"], "practical_floor": "", "passes": row["global_advantage_passes"], "progress_gate": "", "blocks": 64, "notes": "all topologies exact_solutions=0"})
    for row in phase["rugged_phase_map"]:
        for comparison, key in (("multi-minus-global", "multi_minus_global"), ("multi-minus-partition", "multi_minus_partition")):
            c = row["contrasts"][key]
            rows.append({"study": "extreme-v6", "stage": "discovery", "condition": "rugged", "n": 128, "k": row["k"], "budget": row["budget"], "comparison": comparison, "metric": "random_reference_z", "effect": c["mean_random_z_difference"], "ci_low": c["descriptive_random_z_ci"][0], "ci_high": c["descriptive_random_z_ci"][1], "one_sided_lower": c["multiplicity_controlled_random_z_lower"], "practical_floor": c["practical_floor_random_z"], "passes": row["passes"], "progress_gate": row["search_progress_gate"], "blocks": 64, "notes": "64 fresh paired blocks; full pass requires both contrasts"})
    for comparison, key in (("multi-minus-global", "multi_minus_global"), ("multi-minus-partition", "multi_minus_partition")):
        c = confirmation["contrasts"][key]
        rows.append({"study": "extreme-v6", "stage": "independent-confirmation", "condition": "rugged", "n": 128, "k": confirmation["selected_cell"]["k"], "budget": confirmation["selected_cell"]["budget"], "comparison": comparison, "metric": "random_reference_z", "effect": c["mean_random_z_difference"], "ci_low": c["descriptive_random_z_ci"][0], "ci_high": c["descriptive_random_z_ci"][1], "one_sided_lower": c["one_sided_95pct_random_z_lower"], "practical_floor": c["practical_floor_random_z"], "passes": c["passes"], "progress_gate": confirmation["search_progress_gate"]["passes"], "blocks": 192, "notes": "frozen selected cell; completely fresh paired blocks"})
    for cell in followup["cells"]:
        for comparison, key in (("multi-minus-global", "multi_minus_global"), ("multi-minus-partition", "multi_minus_partition")):
            c = cell["contrasts"][key]
            rows.append({"study": "extreme-v6", "stage": "sequential-follow-up", "condition": "rugged", "n": 128, "k": cell["k"], "budget": cell["budget"], "comparison": comparison, "metric": "random_reference_z", "effect": c["mean_random_z_difference"], "ci_low": c["descriptive_random_z_ci"][0], "ci_high": c["descriptive_random_z_ci"][1], "one_sided_lower": c["one_sided_95pct_random_z_lower"], "practical_floor": c["practical_floor_random_z"], "passes": c["passes"], "progress_gate": cell["search_progress_gate"]["passes"], "blocks": 192, "notes": "outcome-aware sequential follow-up; not pooled with confirmation"})
    return fields, rows


def main() -> None:
    construct = read_json("threshold_v6_extreme_construct_diagnostics_v2.json")
    phase = read_json("threshold_v6_extreme_phase_analysis.json")
    confirmation = read_json("threshold_v6_extreme_confirmation_analysis.json")
    followup = read_json("threshold_v6_extreme_window_followup_analysis.json")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "multi-island-extreme-surface.svg").write_text(phase_surface(phase), encoding="utf-8")
    (OUT / "multi-island-extreme-replication.svg").write_text(forest_plot(confirmation, followup, phase), encoding="utf-8")
    (OUT / "multi-island-extreme-smooth.svg").write_text(smooth_surface(phase), encoding="utf-8")
    fields, rows = rows_for_csv(construct, phase, confirmation, followup)
    with (OUT / "multi-island-extreme-results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Rendered 3 SVG figures and {len(rows)} CSV rows in {OUT}")


if __name__ == "__main__":
    main()
