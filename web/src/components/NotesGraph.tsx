import { useMemo } from "react";
import type { NoteGraphNode, NoteGraphEdge } from "../lib/api";

/* Status → node fill (Tailwind utility classes on SVG, mirroring Dag.tsx). */
const STATUS_FILL: Record<string, string> = {
  confirmed: "fill-green-500",
  refuted: "fill-red-500",
  untested: "fill-blue-500",
};

/* Edge kind → stroke / arrowhead / dash. Edges are directed (from → to). */
const EDGE_STYLE: Record<
  string,
  { stroke: string; arrow: string; marker: string; dash?: string }
> = {
  supersedes: { stroke: "stroke-amber-500", arrow: "fill-amber-500", marker: "ng-arw-sup", dash: "7 5" },
  refutes: { stroke: "stroke-red-500", arrow: "fill-red-500", marker: "ng-arw-rfu" },
  references: { stroke: "stroke-border-strong", arrow: "fill-border-strong", marker: "ng-arw-rfc", dash: "1 6" },
};

const VW = 1100;
const VH = 640;
const PAD = 44;
const LABEL_W = 150; // reserve room on the right so labels don't clip

interface Placed {
  id: string;
  x: number;
  y: number;
}

/** Force-lay out a single connected component; returns local positions + size. */
function forceComponent(
  ids: string[],
  links: [number, number][],
): { pts: { id: string; x: number; y: number }[]; w: number; h: number } {
  const n = ids.length;
  if (n === 1) return { pts: [{ id: ids[0], x: 0, y: 0 }], w: 0, h: 0 };

  const R = 240;
  const pts = ids.map((id, i) => {
    const a = (2 * Math.PI * i) / n;
    return { id, x: Math.cos(a) * R, y: Math.sin(a) * R, vx: 0, vy: 0 };
  });
  const k = Math.max(110, R / Math.sqrt(n)) * 1.7; // ideal edge length
  const ITER = 400;

  for (let it = 0; it < ITER; it++) {
    const cool = 1 - it / ITER;
    for (let i = 0; i < n; i++) {
      pts[i].vx = 0;
      pts[i].vy = 0;
    }
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = pts[i].x - pts[j].x;
        const dy = pts[i].y - pts[j].y;
        const d = Math.hypot(dx, dy) || 0.01;
        const rep = (k * k) / d;
        pts[i].vx += (dx / d) * rep;
        pts[i].vy += (dy / d) * rep;
        pts[j].vx -= (dx / d) * rep;
        pts[j].vy -= (dy / d) * rep;
      }
    }
    for (const [a, b] of links) {
      const dx = pts[a].x - pts[b].x;
      const dy = pts[a].y - pts[b].y;
      const d = Math.hypot(dx, dy) || 0.01;
      const att = (d * d) / k;
      pts[a].vx -= (dx / d) * att;
      pts[a].vy -= (dy / d) * att;
      pts[b].vx += (dx / d) * att;
      pts[b].vy += (dy / d) * att;
    }
    const maxStep = 30 * cool + 1;
    for (let i = 0; i < n; i++) {
      const sp = Math.hypot(pts[i].vx, pts[i].vy) || 0.01;
      const step = Math.min(sp, maxStep);
      pts[i].x += (pts[i].vx / sp) * step;
      pts[i].y += (pts[i].vy / sp) * step;
    }
  }

  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  for (const p of pts) {
    p.x -= minX;
    p.y -= minY;
  }
  return {
    pts: pts.map((p) => ({ id: p.id, x: p.x, y: p.y })),
    w: Math.max(...xs) - minX,
    h: Math.max(...ys) - minY,
  };
}

/**
 * Deterministic component-aware layout. Each connected component is force-laid
 * out on its own (so a disconnected cluster can't fling itself across the canvas
 * and crush everything else), then components are packed row-major and the whole
 * thing is fit to the viewBox. Seeded by index — no randomness, stable across
 * refreshes.
 */
function layout(nodes: NoteGraphNode[], edges: NoteGraphEdge[]): Map<string, Placed> {
  const out = new Map<string, Placed>();
  const N = nodes.length;
  if (N === 0) return out;

  const idx = new Map(nodes.map((n, i) => [n.id, i]));

  // union-find → connected components (undirected)
  const par = nodes.map((_, i) => i);
  const find = (x: number): number => {
    while (par[x] !== x) {
      par[x] = par[par[x]];
      x = par[x];
    }
    return x;
  };
  const elinks: [number, number][] = [];
  for (const e of edges) {
    const a = idx.get(e.from);
    const b = idx.get(e.to);
    if (a != null && b != null) {
      elinks.push([a, b]);
      par[find(a)] = find(b);
    }
  }
  const groups = new Map<number, number[]>();
  for (let i = 0; i < N; i++) {
    const r = find(i);
    const g = groups.get(r);
    if (g) g.push(i);
    else groups.set(r, [i]);
  }

  // lay out each component independently
  const comps = [...groups.values()].map((members) => {
    const local = new Map(members.map((gi, li) => [gi, li]));
    const ids = members.map((gi) => nodes[gi].id);
    const links = elinks
      .filter(([a, b]) => local.has(a) && local.has(b))
      .map(([a, b]) => [local.get(a)!, local.get(b)!] as [number, number]);
    return forceComponent(ids, links);
  });

  // pack components row-major within a target row width
  comps.sort((a, b) => b.w * b.h - a.w * a.h);
  const totalArea = comps.reduce((s, c) => s + Math.max(c.w, 60) * Math.max(c.h, 60), 1);
  const targetRow = Math.sqrt(totalArea) * 1.7;
  const GAP = 90;
  let cx = 0;
  let cy = 0;
  let rowH = 0;
  for (const c of comps) {
    const w = Math.max(c.w, 30);
    const h = Math.max(c.h, 30);
    if (cx > 0 && cx + w > targetRow) {
      cx = 0;
      cy += rowH + GAP;
      rowH = 0;
    }
    for (const p of c.pts) out.set(p.id, { id: p.id, x: cx + p.x, y: cy + p.y });
    cx += w + GAP;
    rowH = Math.max(rowH, h);
  }

  // fit to the padded viewBox (reserve LABEL_W on the right for node labels)
  const placed = [...out.values()];
  const xs = placed.map((p) => p.x);
  const ys = placed.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const sx = (VW - PAD - LABEL_W) / (maxX - minX || 1);
  const sy = (VH - 2 * PAD) / (maxY - minY || 1);
  const s = Math.min(sx, sy);
  for (const p of placed) {
    out.set(p.id, { id: p.id, x: PAD + (p.x - minX) * s, y: PAD + (p.y - minY) * s });
  }
  return out;
}

function radius(n: NoteGraphNode): number {
  const c = typeof n.confidence === "number" ? Math.max(0, Math.min(1, n.confidence)) : null;
  return c == null ? 7 : 5 + c * 6; // 5..11 by confidence
}

/** Gentle quadratic-bezier arc between two node boundaries, leaving room for
 *  the arrowhead at the target end. */
function edgePath(a: Placed, b: Placed, ra: number, rb: number): string {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const d = Math.hypot(dx, dy) || 1;
  const ux = dx / d;
  const uy = dy / d;
  const sx = a.x + ux * (ra + 2);
  const sy = a.y + uy * (ra + 2);
  const tx = b.x - ux * (rb + 8);
  const ty = b.y - uy * (rb + 8);
  const curve = Math.min(38, d * 0.12);
  const cx = (sx + tx) / 2 - uy * curve;
  const cy = (sy + ty) / 2 + ux * curve;
  return `M${sx.toFixed(1)},${sy.toFixed(1)} Q${cx.toFixed(1)},${cy.toFixed(1)} ${tx.toFixed(1)},${ty.toFixed(1)}`;
}

export default function NotesGraph({
  nodes,
  edges,
  selected,
  onSelect,
}: {
  nodes: NoteGraphNode[];
  edges: NoteGraphEdge[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  // layout() is a pure, deterministic function of the node/edge order (seeded
  // by index, no randomness), so memoizing on the data is enough — identical
  // input yields identical positions, no jump across refreshes.
  const pos = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const rById = useMemo(() => new Map(nodes.map((n) => [n.id, radius(n)])), [nodes]);

  if (nodes.length === 0) {
    return <div className="text-muted-fg text-sm p-4">No notes to graph yet.</div>;
  }

  return (
    <div className="w-full overflow-hidden rounded-xl border border-border bg-muted/20">
      <svg viewBox={`0 0 ${VW} ${VH}`} className="block w-full" style={{ maxHeight: "70vh" }}>
        <defs>
          <pattern id="ng-dots" width="24" height="24" patternUnits="userSpaceOnUse">
            <circle cx="1.5" cy="1.5" r="1.1" className="fill-border-strong" opacity={0.16} />
          </pattern>
          {Object.values(EDGE_STYLE).map((st) => (
            <marker
              key={st.marker}
              id={st.marker}
              markerWidth="8"
              markerHeight="8"
              refX="6.5"
              refY="3"
              orient="auto"
              markerUnits="userSpaceOnUse"
            >
              <path d="M0,0 L7,3 L0,6 Z" className={st.arrow} />
            </marker>
          ))}
        </defs>

        <rect x={0} y={0} width={VW} height={VH} fill="url(#ng-dots)" />

        {/* edges (directed, curved) */}
        {edges.map((e, i) => {
          const a = pos.get(e.from);
          const b = pos.get(e.to);
          if (!a || !b) return null;
          const st = EDGE_STYLE[e.kind] ?? EDGE_STYLE.references;
          const dim = selected && selected !== e.from && selected !== e.to;
          return (
            <path
              key={i}
              d={edgePath(a, b, rById.get(e.from) ?? 7, rById.get(e.to) ?? 7)}
              fill="none"
              className={st.stroke}
              strokeWidth={1.6}
              strokeLinecap="round"
              strokeDasharray={st.dash}
              markerEnd={`url(#${st.marker})`}
              opacity={dim ? 0.1 : 0.85}
            />
          );
        })}

        {/* nodes */}
        {nodes.map((n) => {
          const p = pos.get(n.id);
          if (!p) return null;
          const r = rById.get(n.id) ?? 7;
          const isSel = selected === n.id;
          const dim = selected && !isSel;
          const label = n.title.length > 26 ? n.title.slice(0, 25) + "…" : n.title;
          const fill = STATUS_FILL[n.status ?? ""] ?? "fill-border-strong";
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              className="cursor-pointer"
              opacity={dim ? 0.28 : 1}
              onClick={() => onSelect(n.id)}
            >
              {isSel && (
                <circle r={r + 6} className="fill-none stroke-foreground" strokeWidth={1.5} opacity={0.45} />
              )}
              {/* background halo so the node reads cleanly over edges + dots */}
              <circle r={r + 3} className="fill-background" />
              <circle r={r} className={fill} />
              <text
                x={r + 9}
                y={4}
                className="fill-foreground stroke-background font-body"
                strokeWidth={3.5}
                style={{ fontSize: 12, paintOrder: "stroke", fontWeight: isSel ? 600 : 500 }}
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>

      {/* legend footer */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border bg-background px-4 py-2.5 font-mono text-[10px] tracking-wide text-muted-fg">
        <LegendDot cls="fill-green-500" label="confirmed" />
        <LegendDot cls="fill-red-500" label="refuted" />
        <LegendDot cls="fill-blue-500" label="untested" />
        <LegendDot cls="fill-border-strong" label="no status" />
        <span className="opacity-30">|</span>
        <LegendEdge cls="amber-500" dash="6 4" label="supersedes" />
        <LegendEdge cls="red-500" label="refutes" />
        <LegendEdge cls="border-strong" dash="1 4" label="references" />
        <span className="ml-auto opacity-70">● size = confidence · → direction</span>
      </div>
    </div>
  );
}

function LegendDot({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width={10} height={10} className="inline-block">
        <circle cx={5} cy={5} r={4} className={cls} />
      </svg>
      {label}
    </span>
  );
}

function LegendEdge({ cls, dash, label }: { cls: string; dash?: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <svg width={20} height={6} className="inline-block">
        <line x1={0} y1={3} x2={14} y2={3} className={`stroke-${cls}`} strokeWidth={1.6} strokeDasharray={dash} />
        <path d="M14,0 L20,3 L14,6 Z" className={`fill-${cls}`} />
      </svg>
      {label}
    </span>
  );
}
