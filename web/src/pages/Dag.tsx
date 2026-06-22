import { useEffect, useMemo, useState } from "react";
import { api, type DagNode, type DagResponse, type RunStatus, type SteeringResponse } from "../lib/api";
import { useSSE } from "../hooks/useSSE";

/* Status → fill color (Tailwind utility classes on SVG elements). */
const STATUS_FILL: Record<string, string> = {
  improved: "fill-green-500",
  baseline: "fill-border-strong",
  regressed: "fill-amber-500",
  reverted: "fill-muted-fg",
  crashed: "fill-red-500",
  timeout: "fill-red-500",
  pending: "fill-blue-500",
};

const COL_W = 200;
const ROW_H = 64;
const R = 9;
const PAD = 32;

interface Placed extends DagNode {
  x: number;
  y: number;
}

/** Layer the DAG: x by depth from a root, y by sibling order within depth. */
function layout(data: DagResponse): { placed: Placed[]; width: number; height: number } {
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const children = new Map<string, string[]>();
  for (const e of data.edges) {
    if (!children.has(e.from)) children.set(e.from, []);
    children.get(e.from)!.push(e.to);
  }

  const depth = new Map<string, number>();
  const roots = data.nodes.filter((n) => n.parent === null);
  const queue: string[] = roots.map((n) => n.id);
  roots.forEach((n) => depth.set(n.id, 0));
  while (queue.length) {
    const id = queue.shift()!;
    const d = depth.get(id)!;
    for (const c of children.get(id) ?? []) {
      if (!depth.has(c)) {
        depth.set(c, d + 1);
        queue.push(c);
      }
    }
  }
  // Any node never reached (dangling) gets depth 0 so it still renders.
  for (const n of data.nodes) if (!depth.has(n.id)) depth.set(n.id, 0);

  const rowCursor = new Map<number, number>();
  const placed: Placed[] = [];
  // Stable order: by timestamp keeps lineage roughly top-to-bottom.
  const ordered = [...data.nodes].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  for (const n of ordered) {
    const d = depth.get(n.id)!;
    const row = rowCursor.get(d) ?? 0;
    rowCursor.set(d, row + 1);
    placed.push({ ...byId.get(n.id)!, x: PAD + d * COL_W + R, y: PAD + row * ROW_H + R });
  }

  const maxDepth = Math.max(0, ...[...depth.values()]);
  const maxRow = Math.max(0, ...[...rowCursor.values()]);
  return {
    placed,
    width: PAD * 2 + maxDepth * COL_W + COL_W,
    height: PAD * 2 + maxRow * ROW_H,
  };
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

  const { placed, width, height } = useMemo(() => layout(data), [data]);
  const posById = useMemo(() => new Map(placed.map((p) => [p.id, p])), [placed]);
  const sel = selected ? posById.get(selected) : null;

  return (
    <div className="col-span-2 flex min-h-0">
      <div className="flex-1 overflow-auto p-4">
        {placed.length === 0 ? (
          <div className="text-muted-fg text-sm p-4">No experiments yet.</div>
        ) : (
          <svg width={width} height={height} className="font-mono">
            {/* edges */}
            {data.edges.map((e) => {
              const a = posById.get(e.from);
              const b = posById.get(e.to);
              if (!a || !b) return null;
              return (
                <line
                  key={`${e.from}-${e.to}`}
                  x1={a.x + R}
                  y1={a.y}
                  x2={b.x - R}
                  y2={b.y}
                  className="stroke-border-strong"
                  strokeWidth={1.5}
                />
              );
            })}
            {/* nodes */}
            {placed.map((n) => (
              <g
                key={n.id}
                transform={`translate(${n.x},${n.y})`}
                className="cursor-pointer"
                onClick={() => setSelected(n.id)}
              >
                {n.is_best && (
                  <circle r={R + 4} className="fill-none stroke-amber-400" strokeWidth={2} />
                )}
                <circle
                  r={R}
                  className={`${STATUS_FILL[n.status] ?? "fill-border-strong"} ${
                    selected === n.id ? "stroke-foreground" : "stroke-background"
                  }`}
                  strokeWidth={2}
                />
                <text
                  x={R + 6}
                  y={4}
                  className="fill-foreground text-[11px]"
                  style={{ fontSize: 11 }}
                >
                  {n.id.slice(0, 7)}
                  {n.score != null ? `  ${n.score.toFixed(3)}` : ""}
                </text>
              </g>
            ))}
          </svg>
        )}
      </div>

      {/* detail panel */}
      <aside className="w-80 shrink-0 border-l border-border p-5 overflow-y-auto">
        {steering.pending_count > 0 && (
          <div className="mb-4 border border-border bg-muted/50 px-3 py-2 text-xs">
            <div className="font-mono text-[10px] uppercase tracking-wider text-muted-fg">
              Queued steering
            </div>
            <div className="mt-1">{steering.pending_count} pending, applies on resume.</div>
          </div>
        )}
        {message && <div className="mb-4 text-xs text-muted-fg">{message}</div>}
        {sel ? (
          <NodeDetail
            node={sel}
            running={Boolean(status?.manager_alive)}
            busy={busy === sel.id}
            onContinue={async () => {
              setBusy(sel.id);
              setMessage(null);
              try {
                await api.steer({ kind: "continue_from", hash: sel.id, instruction: "" });
                await api.steering().then(setSteering);
                setMessage("Queued. Stop the run, then resume to apply it.");
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
          <div className="text-muted-fg text-sm">Select an experiment to see details.</div>
        )}
      </aside>
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
  node: Placed;
  running: boolean;
  busy: boolean;
  onContinue: () => void;
  onMarkBest: () => void;
}) {
  const disabled = running || busy;
  return (
    <div className="space-y-4">
      <div>
        <div className="font-mono text-xs text-muted-fg">{node.id.slice(0, 12)}</div>
        <div className="text-sm font-medium mt-1">{node.title}</div>
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
        {running && <div className="text-xs text-muted-fg">Stop the run to steer.</div>}
        <button
          type="button"
          disabled={disabled}
          onClick={onContinue}
          className="w-full border border-border px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wider disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted transition-colors"
        >
          Continue from here
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={onMarkBest}
          className="w-full border border-border px-3 py-2 text-left font-mono text-[11px] uppercase tracking-wider disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted transition-colors"
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
