import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type DagNode, type DagResponse, type RunStatus, type SteeringResponse } from "../lib/api";
import { useSSE } from "../hooks/useSSE";

/* Card geometry — wide enough for a short hash, score, title and agent. */
const CARD_W = 220;
const CARD_H = 92;
const GAP_X = 80;
const GAP_Y = 28;
const PAD = 28;

const MIN_SCALE = 0.3;
const MAX_SCALE = 2.5;

/* status → swatch class for the small status dot on each card */
const STATUS_DOT: Record<string, string> = {
  improved: "bg-emerald-500",
  baseline: "bg-border-strong",
  regressed: "bg-amber-500",
  reverted: "bg-muted-fg",
  crashed: "bg-red-500",
  timeout: "bg-red-500",
  pending: "bg-blue-500",
};

interface NodePosition {
  node: DagNode;
  col: number;
  row: number;
}

interface Override {
  x: number;
  y: number;
}

/* Tree layout: x by depth from a root, y by stable timestamp order. */
function computeLayout(data: DagResponse): {
  positions: Map<string, NodePosition>;
  cols: number;
  rows: number;
} {
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const children = new Map<string, string[]>();
  for (const e of data.edges) {
    if (!children.has(e.from)) children.set(e.from, []);
    children.get(e.from)!.push(e.to);
  }
  for (const list of children.values()) {
    list.sort((a, b) => {
      const ta = byId.get(a)?.timestamp ?? "";
      const tb = byId.get(b)?.timestamp ?? "";
      return ta.localeCompare(tb);
    });
  }

  const positions = new Map<string, NodePosition>();
  let nextRow = 0;
  let maxCol = 0;

  const roots = data.nodes
    .filter((n) => n.parent === null || !byId.has(n.parent))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  function walk(id: string, col: number) {
    if (positions.has(id)) return;
    const node = byId.get(id);
    if (!node) return;
    const row = nextRow++;
    positions.set(id, { node, col, row });
    maxCol = Math.max(maxCol, col);
    for (const c of children.get(id) ?? []) walk(c, col + 1);
  }
  for (const r of roots) walk(r.id, 0);
  // any disconnected nodes get appended at col 0
  for (const n of data.nodes) if (!positions.has(n.id)) walk(n.id, 0);

  return { positions, cols: maxCol + 1, rows: nextRow };
}

export default function Dag() {
  const [data, setData] = useState<DagResponse>({ nodes: [], edges: [] });
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [steering, setSteering] = useState<SteeringResponse>({ actions: [], pending_count: 0 });
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const refresh = () => {
    api.dag().then(setData).catch(() => {});
    api.status().then(setStatus).catch(() => {});
    api.steering().then(setSteering).catch(() => {});
  };
  useEffect(refresh, []);
  useSSE({ "attempt:new": refresh, "attempt:update": refresh });

  const sel = selected ? data.nodes.find((n) => n.id === selected) ?? null : null;
  const running = Boolean(status?.manager_alive);

  return (
    <div className="col-span-2 flex min-h-0">
      <div className="flex-1 min-w-0 p-4">
        <LineageCanvas
          data={data}
          selectedHash={selected}
          onSelect={setSelected}
        />
      </div>

      <aside className="w-80 shrink-0 border-l border-border p-5 overflow-y-auto">
        {steering.pending_count > 0 && (
          <div className="mb-4 border border-border rounded-lg bg-muted/50 px-3 py-2 text-xs">
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted-fg">
              Queued steering
            </div>
            <div className="mt-1">
              {steering.pending_count} pending — applies on next resume.
            </div>
          </div>
        )}
        {message && (
          <div className="mb-4 rounded-lg border border-border bg-muted/30 px-3 py-2 text-xs">
            {message}
          </div>
        )}
        {sel ? (
          <NodeDetail
            node={sel}
            running={running}
            busy={busy === sel.id}
            onContinue={async () => {
              setBusy(sel.id);
              setMessage(null);
              try {
                await api.steer({ kind: "continue_from", hash: sel.id, instruction: "" });
                await api.steering().then(setSteering);
                setMessage(
                  running
                    ? "Queued. Will apply on the next resume."
                    : "Queued. Run `coral resume` to apply.",
                );
              } catch (err) {
                setMessage(err instanceof Error ? err.message : "Unable to queue steering.");
              } finally {
                setBusy(null);
              }
            }}
            onMarkBest={async () => {
              setBusy(sel.id);
              setMessage(null);
              try {
                await api.steer({ kind: "mark_best", hash: sel.id });
                await api.dag().then(setData);
                setMessage("Marked as best.");
              } catch (err) {
                setMessage(err instanceof Error ? err.message : "Unable to mark best.");
              } finally {
                setBusy(null);
              }
            }}
          />
        ) : (
          <div className="text-muted-fg text-sm">Select an attempt to see details.</div>
        )}
      </aside>
    </div>
  );
}

function LineageCanvas({
  data,
  selectedHash,
  onSelect,
}: {
  data: DagResponse;
  selectedHash: string | null;
  onSelect: (id: string | null) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [scale, setScale] = useState(1);
  const [isPanning, setIsPanning] = useState(false);
  const panRef = useRef<{ mx: number; my: number; px: number; py: number } | null>(null);
  const dragRef = useRef<{
    hash: string;
    startMouse: { x: number; y: number };
    startNode: { x: number; y: number };
  } | null>(null);
  const dragMovedRef = useRef(false);
  const [draggingHash, setDraggingHash] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Map<string, Override>>(() => new Map());

  const layout = useMemo(() => computeLayout(data), [data]);

  const contentW = layout.cols * (CARD_W + GAP_X) + GAP_X + PAD * 2;
  const contentH = layout.rows * (CARD_H + GAP_Y) + GAP_Y + PAD * 2;

  const byHash = useMemo(
    () => new Map(data.nodes.map((n) => [n.id, n])),
    [data.nodes],
  );

  const lineage = useMemo(() => {
    if (!selectedHash) return null;
    const chain = new Set<string>();
    let cur: string | null = selectedHash;
    while (cur && byHash.has(cur) && !chain.has(cur)) {
      chain.add(cur);
      cur = byHash.get(cur)!.parent;
    }
    return chain;
  }, [selectedHash, byHash]);

  const displayPos = useCallback(
    (hash: string, pos: NodePosition): { x: number; y: number } => {
      const o = overrides.get(hash);
      if (o) return o;
      return {
        x: PAD + pos.col * (CARD_W + GAP_X),
        y: PAD + pos.row * (CARD_H + GAP_Y),
      };
    },
    [overrides],
  );

  const setNodeOverride = useCallback((hash: string, pos: Override) => {
    setOverrides((prev) => {
      const next = new Map(prev);
      next.set(hash, pos);
      return next;
    });
  }, []);

  const resetView = () => {
    setPan({ x: 0, y: 0 });
    setScale(1);
    setOverrides(new Map());
  };

  const handleBgMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsPanning(true);
    panRef.current = { mx: e.clientX, my: e.clientY, px: pan.x, py: pan.y };
    onSelect(null);
  };

  const handleNodeMouseDown =
    (hash: string, pos: NodePosition) => (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      const p = displayPos(hash, pos);
      dragRef.current = {
        hash,
        startMouse: { x: e.clientX, y: e.clientY },
        startNode: { x: p.x, y: p.y },
      };
      dragMovedRef.current = false;
      setDraggingHash(hash);
    };

  useEffect(() => {
    function onMove(e: MouseEvent) {
      if (dragRef.current) {
        const dx = e.clientX - dragRef.current.startMouse.x;
        const dy = e.clientY - dragRef.current.startMouse.y;
        if (Math.hypot(dx, dy) > 3) dragMovedRef.current = true;
        setNodeOverride(dragRef.current.hash, {
          x: dragRef.current.startNode.x + dx / scale,
          y: dragRef.current.startNode.y + dy / scale,
        });
      } else if (panRef.current) {
        setPan({
          x: panRef.current.px + (e.clientX - panRef.current.mx),
          y: panRef.current.py + (e.clientY - panRef.current.my),
        });
      }
    }
    function onUp() {
      dragRef.current = null;
      panRef.current = null;
      setIsPanning(false);
      setDraggingHash(null);
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [scale, setNodeOverride]);

  // non-passive wheel listener so preventDefault() actually works
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    function handleWheel(e: WheelEvent) {
      e.preventDefault();
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor));
      if (newScale === scale) return;
      const newPanX = mx - (mx - pan.x) * (newScale / scale);
      const newPanY = my - (my - pan.y) * (newScale / scale);
      setScale(newScale);
      setPan({ x: newPanX, y: newPanY });
    }
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
    };
  }, [scale, pan]);

  if (data.nodes.length === 0) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 text-muted-fg text-sm">
        Waiting for the first attempt…
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full select-none overflow-hidden rounded-xl border border-border bg-muted/20"
      style={{
        cursor: isPanning || draggingHash ? "grabbing" : "grab",
        backgroundImage:
          "radial-gradient(circle, rgba(60,60,70,0.10) 1px, transparent 1px)",
        backgroundSize: "20px 20px",
      }}
      onMouseDown={handleBgMouseDown}
      onDoubleClick={resetView}
    >
      <div
        className="absolute left-0 top-0 origin-top-left"
        style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale})` }}
      >
        <div style={{ width: contentW, height: contentH, position: "relative" }}>
          <svg
            className="pointer-events-none absolute inset-0"
            width={contentW}
            height={contentH}
          >
            {[...layout.positions.values()].map((pos) => {
              const n = pos.node;
              if (!n.parent) return null;
              const parent = layout.positions.get(n.parent);
              if (!parent) return null;
              const from = displayPos(parent.node.id, parent);
              const to = displayPos(n.id, pos);
              const x1 = from.x + CARD_W;
              const y1 = from.y + CARD_H / 2;
              const x2 = to.x;
              const y2 = to.y + CARD_H / 2;
              const dx = x2 - x1;
              const cx1 = x1 + Math.max(40, dx * 0.5);
              const cx2 = x2 - Math.max(40, dx * 0.5);
              const path = `M ${x1} ${y1} C ${cx1} ${y1}, ${cx2} ${y2}, ${x2} ${y2}`;
              const inLineage =
                lineage != null &&
                lineage.has(n.id) &&
                lineage.has(parent.node.id);
              const dimmed = lineage != null && !inLineage;
              return (
                <g key={n.id} opacity={dimmed ? 0.2 : 1}>
                  <path
                    d={path}
                    fill="none"
                    stroke={
                      inLineage
                        ? "var(--color-foreground)"
                        : "var(--color-border-strong)"
                    }
                    strokeWidth={(inLineage ? 2 : 1.2) / scale}
                  />
                  <circle
                    cx={x2}
                    cy={y2}
                    r={3 / scale}
                    fill={
                      inLineage
                        ? "var(--color-foreground)"
                        : "var(--color-border-strong)"
                    }
                  />
                </g>
              );
            })}
          </svg>
          {[...layout.positions.values()].map((pos) => {
            const n = pos.node;
            const display = displayPos(n.id, pos);
            const isSelected = selectedHash === n.id;
            const dimmed = lineage != null && !lineage.has(n.id);
            const parentNode = n.parent ? byHash.get(n.parent) : null;
            const delta =
              n.score != null && parentNode?.score != null
                ? n.score - parentNode.score
                : null;
            return (
              <button
                key={n.id}
                type="button"
                onMouseDown={handleNodeMouseDown(n.id, pos)}
                onClick={(e) => {
                  e.stopPropagation();
                  if (dragMovedRef.current) {
                    dragMovedRef.current = false;
                    return;
                  }
                  onSelect(n.id);
                }}
                onDoubleClick={(e) => e.stopPropagation()}
                className="absolute text-left transition-transform duration-100 ease-out hover:scale-[1.02] active:scale-[0.99]"
                style={{
                  left: display.x,
                  top: display.y,
                  width: CARD_W,
                  height: CARD_H,
                  cursor: draggingHash === n.id ? "grabbing" : "grab",
                }}
              >
                <NodeCard
                  node={n}
                  delta={delta}
                  selected={isSelected}
                  dimmed={Boolean(dimmed)}
                />
              </button>
            );
          })}
        </div>
      </div>

      {/* zoom + reset controls */}
      <div className="pointer-events-auto absolute bottom-3 left-3 flex flex-col gap-1">
        <button
          type="button"
          onClick={() => setScale((s) => Math.min(MAX_SCALE, s * 1.2))}
          onMouseDown={(e) => e.stopPropagation()}
          className="rounded-md border border-border bg-background px-2 py-1 font-mono text-xs text-muted-fg hover:text-foreground hover:border-border-strong"
          title="Zoom in"
        >
          +
        </button>
        <button
          type="button"
          onClick={() => setScale((s) => Math.max(MIN_SCALE, s / 1.2))}
          onMouseDown={(e) => e.stopPropagation()}
          className="rounded-md border border-border bg-background px-2 py-1 font-mono text-xs text-muted-fg hover:text-foreground hover:border-border-strong"
          title="Zoom out"
        >
          −
        </button>
        <button
          type="button"
          onClick={resetView}
          onMouseDown={(e) => e.stopPropagation()}
          className="rounded-md border border-border bg-background px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-muted-fg hover:text-foreground hover:border-border-strong"
          title="Reset view (double-click background)"
        >
          fit
        </button>
      </div>
      <div className="pointer-events-none absolute bottom-3 right-3 font-mono text-[10px] text-muted-fg">
        {Math.round(scale * 100)}%
      </div>
    </div>
  );
}

function NodeCard({
  node,
  delta,
  selected,
  dimmed,
}: {
  node: DagNode;
  delta: number | null;
  selected: boolean;
  dimmed: boolean;
}) {
  const title = node.title?.trim() || "(no message)";
  const score = node.score != null ? node.score.toFixed(3) : "—";
  const dot = STATUS_DOT[node.status] ?? "bg-border-strong";
  const isBest = node.user_best || node.is_best;
  const borderClass = selected
    ? "border-foreground"
    : isBest
      ? "border-foreground/60"
      : "border-border";
  return (
    <div
      className={`flex h-full flex-col justify-between rounded-lg border bg-background px-2.5 py-2 shadow-sm transition-opacity ${
        dimmed ? "opacity-30" : ""
      } ${borderClass}`}
    >
      <div className="flex items-center justify-between gap-1.5">
        <span className="font-mono text-[10.5px] font-medium text-muted-fg">
          {node.id.slice(0, 7)}
        </span>
        <span
          className={`inline-block h-[7px] w-[7px] rounded-full ${dot}`}
          title={node.status}
        />
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="font-mono text-[15px] font-semibold text-foreground">
          {score}
        </span>
        {delta != null && (
          <span
            className={`font-mono text-[10px] ${
              delta > 0
                ? "text-emerald-600"
                : delta < 0
                  ? "text-red-600"
                  : "text-muted-fg"
            }`}
          >
            {delta > 0 ? "+" : ""}
            {delta.toFixed(3)}
          </span>
        )}
      </div>
      <p
        className="overflow-hidden text-[11px] leading-tight text-foreground"
        style={{
          display: "-webkit-box",
          WebkitBoxOrient: "vertical",
          WebkitLineClamp: 1,
        }}
        title={title}
      >
        {title}
      </p>
      <p className="truncate font-mono text-[10px] text-muted-fg">
        {node.agent_id}
      </p>
      {isBest && (
        <span className="absolute -top-2 right-2 rounded-full bg-foreground px-1.5 py-0.5 font-mono text-[8.5px] font-semibold uppercase tracking-wider text-background shadow-sm">
          {node.user_best ? "user best" : "best"}
        </span>
      )}
    </div>
  );
}

function NodeDetail({
  node,
  running,
  busy,
  onContinue,
  onMarkBest,
}: {
  node: DagNode;
  running: boolean;
  busy: boolean;
  onContinue: () => void;
  onMarkBest: () => void;
}) {
  return (
    <div className="space-y-4">
      <div>
        <div className="font-mono text-xs text-muted-fg">{node.id.slice(0, 12)}</div>
        <div className="text-sm font-medium mt-1">{node.title || "(no message)"}</div>
      </div>
      <dl className="text-[13px] space-y-1.5">
        <Row k="agent" v={node.agent_id} />
        <Row k="status" v={node.status} />
        <Row k="score" v={node.score != null ? node.score.toFixed(4) : "—"} />
        <Row k="best" v={node.user_best ? "user" : node.is_best ? "score" : "no"} />
        <Row k="parent" v={node.parent ? node.parent.slice(0, 12) : "(root)"} />
        <Row k="time" v={node.timestamp} />
      </dl>
      <div className="space-y-2">
        {running && (
          <div className="text-[11px] text-muted-fg">
            Run is live — actions will be queued and applied on the next resume.
          </div>
        )}
        <button
          type="button"
          disabled={busy}
          onClick={onContinue}
          className="w-full rounded-lg border border-border px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wider transition-colors hover:bg-muted hover:border-border-strong disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Continue from here
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onMarkBest}
          className="w-full rounded-lg border border-border px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wider transition-colors hover:bg-muted hover:border-border-strong disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Mark as best
        </button>
      </div>
      <div>
        <div className="text-xs text-muted-fg mb-1">Export as a git branch</div>
        <code className="block bg-muted rounded-lg p-2.5 text-[11px] font-mono break-all">
          coral export {node.id.slice(0, 12)} --branch coral/from-{node.id.slice(0, 7)}
        </code>
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-fg">{k}</dt>
      <dd className="font-mono text-right break-all">{v}</dd>
    </div>
  );
}
