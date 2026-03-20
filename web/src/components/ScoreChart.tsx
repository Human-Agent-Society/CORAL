import { useRef, useState } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  LogarithmicScale,
  TimeScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import zoomPlugin from "chartjs-plugin-zoom";
import "chartjs-adapter-date-fns";
import { Line } from "react-chartjs-2";
import type { Attempt } from "../lib/api";

ChartJS.register(
  CategoryScale,
  LinearScale,
  LogarithmicScale,
  TimeScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
  Filler,
  zoomPlugin
);

type ScaleMode = "linear" | "log";
type ViewMode = "all" | "last50" | "last20" | "custom";
type XAxisMode = "index" | "time";

const AGENT_PALETTE = [
  "#374151", // gray-700
  "#1e3a5f", // dark slate blue
  "#5b4a6a", // dark mauve
  "#4a5240", // dark olive
  "#7c4a3a", // dark rust
  "#2d5a5a", // dark teal
  "#5a4630", // dark bronze
  "#3b4f7a", // muted cobalt
  "#6b4050", // muted berry
  "#2e5e4e", // muted forest
];

function agentColor(index: number): string {
  if (index < AGENT_PALETTE.length) return AGENT_PALETTE[index];
  const hue = ((index - AGENT_PALETTE.length) * 137.5) % 360;
  return `hsl(${hue}, 35%, 40%)`;
}

function stripCommonPrefix(id: string, all: string[]): string {
  if (all.length <= 1) return id;
  let prefix = all[0];
  for (const s of all) {
    while (!s.startsWith(prefix)) prefix = prefix.slice(0, -1);
  }
  const stripped = id.slice(prefix.length).replace(/^[-_]/, "");
  return stripped || id;
}

function percentile(arr: number[], p: number): number {
  const s = [...arr].sort((a, b) => a - b);
  const idx = Math.floor(s.length * p);
  return s[Math.min(idx, s.length - 1)];
}

function formatNum(n: number): string {
  if (Math.abs(n) >= 1000) return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
  if (Math.abs(n) >= 1) return n.toFixed(2);
  return n.toFixed(6);
}

interface Props {
  attempts: Attempt[];
  height?: number | string;
  direction?: "maximize" | "minimize";
  expanded?: boolean;
  animationDuration?: number;
}

export default function ScoreChart({
  attempts,
  height = 280,
  direction = "maximize",
  expanded = false,
  animationDuration,
}: Props) {
  const chartRef = useRef<ChartJS<"line"> | null>(null);
  const [scaleMode, setScaleMode] = useState<ScaleMode>("linear");
  const [viewMode, setViewMode] = useState<ViewMode>("all");
  const [xAxisMode, setXAxisMode] = useState<XAxisMode>("index");
  const [rangeText, setRangeText] = useState("");
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());
  const [scoreMin, setScoreMin] = useState("");
  const [scoreMax, setScoreMax] = useState("");
  const [hideCrashed, setHideCrashed] = useState(false);
  const [improvedOnly, setImprovedOnly] = useState(false);

  // Filter and sort
  let filtered = [...attempts]
    .filter((a) => a.score !== null)
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp));

  if (expanded && hideCrashed) {
    filtered = filtered.filter((a) => a.status !== "crashed");
  }
  if (expanded && improvedOnly) {
    filtered = filtered.filter((a) => a.status === "improved");
  }

  const sorted = filtered;
  const agents = [...new Set(sorted.map((a) => a.agent_id))].sort();

  const toggleAgent = (id: string) => {
    setSelectedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  if (sorted.length === 0) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-fg font-mono text-sm">
        No scored attempts yet
      </div>
    );
  }

  // Apply view mode
  let sliced: typeof sorted;
  if (viewMode === "custom") {
    const [start, end] = parseRange(rangeText, sorted.length);
    sliced = sorted.slice(start, end);
  } else if (viewMode === "last20") {
    sliced = sorted.slice(-20);
  } else if (viewMode === "last50") {
    sliced = sorted.slice(-50);
  } else {
    sliced = sorted;
  }

  if (sliced.length === 0) sliced = sorted;

  // Compute running best (direction-aware)
  const minimize = direction === "minimize";
  const runningBest = sliced.reduce<number[]>((acc, a) => {
    const prev = acc.length > 0 ? acc[acc.length - 1] : (minimize ? Infinity : -Infinity);
    acc.push(minimize ? Math.min(prev, a.score!) : Math.max(prev, a.score!));
    return acc;
  }, []);

  // For log scale, ensure all values are positive
  const scores = sliced.map((a) => a.score!);
  const allPositive = scores.every((s) => s > 0) && runningBest.every((s) => s > 0);
  const effectiveScale = scaleMode === "log" && allPositive ? "logarithmic" : "linear";

  const useTime = xAxisMode === "time";

  // Figure out the global index offset for labels
  const offset = sorted.indexOf(sliced[0]);
  const labels: unknown[] = useTime
    ? sliced.map((a) => new Date(a.timestamp).getTime())
    : sliced.map((_, i) => `#${offset + i + 1}`);

  const showPerAgent = selectedAgents.size > 0;

  const ptRadius = expanded ? 3 : 4;
  const lineWidth = 2;

  const agentDatasets = showPerAgent
    ? agents
        .filter((id) => selectedAgents.has(id))
        .map((id) => {
          const color = agentColor(agents.indexOf(id));
          return {
            label: id,
            data: sliced.map((a) => (a.agent_id === id ? a.score! : null)),
            borderColor: color,
            backgroundColor: "transparent",
            borderWidth: lineWidth,
            pointRadius: ptRadius,
            pointBackgroundColor: color,
            pointBorderColor: color,
            pointBorderWidth: 2,
            fill: false,
            tension: 0,
            spanGaps: true,
          };
        })
    : [
        {
          label: "Score",
          data: scores,
          borderColor: "#1a1d1e",
          backgroundColor: "rgba(26, 29, 30, 0.08)",
          borderWidth: lineWidth,
          pointRadius: ptRadius,
          pointBackgroundColor: sliced.map((a) =>
            a.status === "improved" ? "#1a1d1e" : "#eff0f0"
          ),
          pointBorderColor: "#1a1d1e",
          pointBorderWidth: 2,
          fill: true,
          tension: 0,
          spanGaps: false,
        },
      ];

  const data = {
    labels,
    datasets: [
      ...agentDatasets,
      {
        label: "Best",
        data: runningBest,
        borderColor: showPerAgent ? "#a0a3a5" : "#1a1d1e",
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        fill: false,
        tension: 0,
      },
    ],
  };

  const xScale = useTime
    ? {
        type: "time" as const,
        time: {
          tooltipFormat: "MMM d, HH:mm",
          displayFormats: {
            minute: "HH:mm",
            hour: "HH:mm",
            day: "MMM d",
          },
        },
        grid: { color: "#d0d3d5", lineWidth: 1 },
        ticks: {
          font: { family: "'JetBrains Mono', monospace", size: 10 },
          color: "#727879",
          maxRotation: 0,
        },
      }
    : {
        type: "category" as const,
        grid: { color: "#d0d3d5", lineWidth: 1 },
        ticks: {
          font: { family: "'JetBrains Mono', monospace", size: 10 },
          color: "#727879",
        },
      };

  // Y-axis score range
  const yMin = scoreMin.trim() ? parseFloat(scoreMin) : undefined;
  const yMax = scoreMax.trim() ? parseFloat(scoreMax) : undefined;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const options: any = {
    responsive: true,
    maintainAspectRatio: false,
    ...(animationDuration !== undefined && {
      animation: { duration: animationDuration },
    }),
    plugins: {
      legend: {
        display: true,
        position: "top" as const,
        labels: {
          font: { family: "'JetBrains Mono', monospace", size: 11 },
          boxWidth: 20,
          boxHeight: 2,
          color: "#1a1d1e",
        },
      },
      tooltip: {
        backgroundColor: "#1a1d1e",
        titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
        bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
        callbacks: {
          label: (ctx: {
            dataset: { label?: string };
            parsed: { y: number | null };
          }) => {
            const val = ctx.parsed.y;
            return `${ctx.dataset.label}: ${val !== null ? val.toFixed(6) : "N/A"}`;
          },
        },
      },
      zoom: expanded
        ? {
            zoom: {
              wheel: { enabled: true, speed: 0.05 },
              pinch: { enabled: true },
              mode: "xy" as const,
            },
            pan: {
              enabled: true,
              mode: "xy" as const,
            },
          }
        : false,
    },
    scales: {
      x: xScale,
      y: {
        type: effectiveScale as "linear" | "logarithmic",
        grid: { color: "#d0d3d5", lineWidth: 1 },
        ticks: {
          font: { family: "'JetBrains Mono', monospace", size: 10 },
          color: "#727879",
        },
        ...(yMin !== undefined && !isNaN(yMin) ? { min: yMin } : {}),
        ...(yMax !== undefined && !isNaN(yMax) ? { max: yMax } : {}),
      },
    },
  };

  const resetZoom = () => {
    chartRef.current?.resetZoom();
  };

  // Percentile helpers
  const setPercentileMax = (p: number) => {
    const val = percentile(scores, p);
    setScoreMax(String(Math.ceil(val * 1.1))); // 10% margin
    setScoreMin("");
  };

  // Stats
  const statsMin = Math.min(...scores);
  const statsMax = Math.max(...scores);
  const statsMedian = percentile(scores, 0.5);
  const statsP95 = percentile(scores, 0.95);

  const btnClass = (active: boolean) =>
    `px-2 py-0.5 font-mono text-[10px] tracking-wider uppercase border border-border rounded-sm transition-colors duration-100 ${
      active
        ? "bg-foreground text-background"
        : "bg-background text-foreground hover:bg-muted"
    }`;

  const inputClass =
    "w-20 px-2 py-0.5 font-mono text-[10px] border border-border rounded-sm bg-background text-foreground placeholder:text-muted-fg/50 outline-none focus:ring-1 focus:ring-border-strong";

  return (
    <div className={expanded ? "h-full flex flex-col" : ""}>
      {/* Row 1: Core controls */}
      <div className={`flex items-center gap-4 ${expanded ? "mb-2" : "mb-4 pr-16"} flex-wrap`}>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-2">
            Scale
          </span>
          <button
            className={btnClass(scaleMode === "linear")}
            onClick={() => setScaleMode("linear")}
          >
            Linear
          </button>
          <button
            className={btnClass(scaleMode === "log")}
            onClick={() => setScaleMode("log")}
            title={allPositive ? "" : "Log scale requires all positive values"}
          >
            Log
          </button>
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-2">
            X-Axis
          </span>
          <button
            className={btnClass(xAxisMode === "index")}
            onClick={() => setXAxisMode("index")}
          >
            Index
          </button>
          <button
            className={btnClass(xAxisMode === "time")}
            onClick={() => setXAxisMode("time")}
          >
            Time
          </button>
        </div>
        <div className="flex items-center gap-1">
          <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-2">
            View
          </span>
          <button
            className={btnClass(viewMode === "all")}
            onClick={() => setViewMode("all")}
          >
            All
          </button>
          <button
            className={btnClass(viewMode === "last50")}
            onClick={() => setViewMode("last50")}
          >
            Last 50
          </button>
          <button
            className={btnClass(viewMode === "last20")}
            onClick={() => setViewMode("last20")}
          >
            Last 20
          </button>
        </div>
        {agents.length > 1 && (
          <div className="flex items-center gap-1 shrink-0">
            <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-2 shrink-0">
              Agents
            </span>
            <button
              className={btnClass(selectedAgents.size === agents.length)}
              onClick={() =>
                setSelectedAgents(
                  selectedAgents.size === agents.length
                    ? new Set()
                    : new Set(agents)
                )
              }
            >
              {selectedAgents.size === agents.length ? "None" : "All"}
            </button>
            <div className="flex items-center gap-1 overflow-x-auto">
              {agents.map((id, i) => {
                const color = agentColor(i);
                const label = stripCommonPrefix(id, agents);
                const isActive = selectedAgents.has(id);
                return (
                  <button
                    key={id}
                    className={`flex items-center px-1.5 py-0.5 font-mono text-[10px] tracking-wider border rounded-sm transition-colors duration-100 shrink-0 ${
                      isActive
                        ? "bg-foreground text-background border-foreground"
                        : "bg-background text-foreground hover:bg-muted border-border"
                    }`}
                    onClick={() => toggleAgent(id)}
                  >
                    <span
                      className="inline-block w-2 h-2 rounded-full mr-1 shrink-0"
                      style={{ backgroundColor: color }}
                    />
                    {label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
        <div className="flex items-center gap-1">
          <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-1">
            Range
          </span>
          <input
            type="text"
            value={rangeText}
            onChange={(e) => {
              setRangeText(e.target.value);
              if (e.target.value.trim()) {
                setViewMode("custom");
              }
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && rangeText.trim()) {
                setViewMode("custom");
              }
            }}
            placeholder={`1-${sorted.length}`}
            className={`w-24 ${inputClass} ${
              viewMode === "custom" ? "ring-1 ring-border-strong" : ""
            }`}
          />
        </div>
      </div>

      {/* Row 2: Expanded-only controls */}
      {expanded && (
        <div className="flex items-center gap-4 mb-2 flex-wrap">
          {/* Filter toggles */}
          <div className="flex items-center gap-1">
            <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-2">
              Filter
            </span>
            <button
              className={btnClass(hideCrashed)}
              onClick={() => setHideCrashed(!hideCrashed)}
            >
              Hide Crashed
            </button>
            <button
              className={btnClass(improvedOnly)}
              onClick={() => setImprovedOnly(!improvedOnly)}
            >
              Improved Only
            </button>
          </div>

          {/* Y-Range with percentile presets */}
          <div className="flex items-center gap-1">
            <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-1">
              Y-Range
            </span>
            <input
              type="text"
              value={scoreMin}
              onChange={(e) => setScoreMin(e.target.value)}
              placeholder="min"
              className={inputClass}
            />
            <input
              type="text"
              value={scoreMax}
              onChange={(e) => setScoreMax(e.target.value)}
              placeholder="max"
              className={inputClass}
            />
            <button
              className={`${btnClass(false)} ml-1`}
              onClick={() => { setScoreMin(""); setScoreMax(""); }}
              title="Clear Y-Range"
            >
              Clear
            </button>
          </div>

          {/* Percentile presets */}
          <div className="flex items-center gap-1">
            <span className="font-mono text-[10px] text-muted-fg uppercase tracking-widest mr-1">
              Clip
            </span>
            <button className={btnClass(false)} onClick={() => setPercentileMax(0.5)}>
              P50
            </button>
            <button className={btnClass(false)} onClick={() => setPercentileMax(0.9)}>
              P90
            </button>
            <button className={btnClass(false)} onClick={() => setPercentileMax(0.95)}>
              P95
            </button>
            <button className={btnClass(false)} onClick={() => setPercentileMax(0.99)}>
              P99
            </button>
          </div>

          {/* Reset zoom */}
          <button
            onClick={resetZoom}
            className={btnClass(false)}
          >
            Reset Zoom
          </button>
        </div>
      )}

      {/* Stats line (expanded only) */}
      {expanded && scores.length > 0 && (
        <div className="font-mono text-[10px] text-muted-fg mb-2 flex items-center gap-4">
          <span>n={scores.length}</span>
          <span>min={formatNum(statsMin)}</span>
          <span>median={formatNum(statsMedian)}</span>
          <span>P95={formatNum(statsP95)}</span>
          <span>max={formatNum(statsMax)}</span>
        </div>
      )}

      {/* Chart */}
      <div className={expanded ? "flex-1 min-h-0" : ""} style={expanded ? undefined : { height }}>
        <Line ref={chartRef} data={data} options={options} />
      </div>
    </div>
  );
}

/** Parse "5-20", "10-", "-30", or "15" into [startIdx, endIdx] (0-based, exclusive end). */
function parseRange(text: string, total: number): [number, number] {
  const trimmed = text.trim();
  if (!trimmed) return [0, total];

  if (trimmed.includes("-")) {
    const [a, b] = trimmed.split("-", 2);
    const start = a.trim() ? Math.max(0, parseInt(a, 10) - 1) : 0;
    const end = b.trim() ? Math.min(total, parseInt(b, 10)) : total;
    if (isNaN(start) || isNaN(end) || start >= end) return [0, total];
    return [start, end];
  }

  // Single number — show that one step and a few around it
  const n = parseInt(trimmed, 10);
  if (isNaN(n) || n < 1 || n > total) return [0, total];
  return [n - 1, n];
}
