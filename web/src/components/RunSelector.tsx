import { useEffect, useRef, useState } from "react";
import { api, type RunsResponse } from "../lib/api";

export default function RunSelector() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<RunsResponse | null>(null);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const [switching, setSwitching] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.runs().then((d) => {
      setData(d);
      setSelectedTask(d.current.task);
    }).catch(() => {});
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const handleSwitch = async (task: string, run: string) => {
    if (data && task === data.current.task && run === data.current.run) {
      setOpen(false);
      return;
    }
    setSwitching(true);
    try {
      await api.switchRun(task, run);
      window.location.reload();
    } catch {
      setSwitching(false);
    }
  };

  if (!data) return null;

  const currentTask = data.tasks.find((t) => t.slug === data.current.task);
  const hasMultipleTasks = data.tasks.length > 1;
  const activeTask = data.tasks.find((t) => t.slug === selectedTask) ?? currentTask;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-1 rounded-md hover:bg-muted transition-colors duration-100"
        disabled={switching}
      >
        <span className="font-body text-[13px] text-muted-fg truncate max-w-[160px]">
          {data.current.task}
        </span>
        <span className="text-border-strong">/</span>
        <span className="font-mono text-[11px] text-muted-fg">
          {formatTimestamp(data.current.run)}
        </span>
        <svg
          className={`w-3 h-3 text-muted-fg transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          className={`absolute top-full left-0 mt-1 z-50 bg-background border border-border rounded-lg shadow-lg overflow-hidden ${
            hasMultipleTasks ? "w-[520px]" : "w-[340px]"
          }`}
        >
          {hasMultipleTasks ? (
            <div className="flex">
              {/* Left: task list */}
              <div className="w-[180px] border-r border-border bg-muted/50 overflow-y-auto max-h-[360px] shrink-0">
                {data.tasks.map((t) => (
                  <button
                    key={t.slug}
                    onClick={() => setSelectedTask(t.slug)}
                    title={t.slug}
                    className={`w-full text-left px-3 py-2 font-mono text-[10px] tracking-wider uppercase truncate border-b border-border last:border-b-0 transition-colors duration-100 ${
                      selectedTask === t.slug
                        ? "bg-foreground text-background"
                        : "text-muted-fg hover:text-foreground hover:bg-muted"
                    }`}
                  >
                    {t.slug}
                  </button>
                ))}
              </div>

              {/* Right: run list */}
              <div className="flex-1 max-h-[360px] overflow-y-auto">
                <RunList
                  task={activeTask}
                  currentTask={data.current.task}
                  currentRun={data.current.run}
                  switching={switching}
                  onSwitch={handleSwitch}
                />
              </div>
            </div>
          ) : (
            <div className="max-h-[360px] overflow-y-auto">
              <RunList
                task={activeTask}
                currentTask={data.current.task}
                currentRun={data.current.run}
                switching={switching}
                onSwitch={handleSwitch}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RunList({
  task,
  currentTask,
  currentRun,
  switching,
  onSwitch,
}: {
  task: { slug: string; runs: { timestamp: string; status: string; attempts: number; is_latest: boolean }[] } | undefined;
  currentTask: string;
  currentRun: string;
  switching: boolean;
  onSwitch: (task: string, run: string) => void;
}) {
  if (!task || task.runs.length === 0) {
    return (
      <p className="py-4 text-center font-mono text-[11px] text-muted-fg">
        No runs found.
      </p>
    );
  }

  return (
    <>
      {task.runs.map((run) => {
        const isCurrent =
          task.slug === currentTask && run.timestamp === currentRun;
        return (
          <button
            key={run.timestamp}
            onClick={() => onSwitch(task.slug, run.timestamp)}
            disabled={switching}
            className={`w-full text-left px-3 py-2 flex items-center gap-2 transition-colors duration-100 border-b border-border last:border-b-0 ${
              isCurrent ? "bg-foreground/5" : "hover:bg-muted/50"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                run.status === "running" ? "bg-green-500" : "bg-border-strong"
              }`}
            />
            <span className="font-mono text-[11px] flex-1">
              {formatTimestamp(run.timestamp)}
            </span>
            <span className="font-mono text-[10px] text-muted-fg">
              {run.attempts} att
            </span>
            {run.is_latest && (
              <span className="font-mono text-[9px] text-muted-fg bg-muted px-1 py-0.5 rounded">
                latest
              </span>
            )}
            {isCurrent && (
              <span className="font-mono text-[9px] text-background bg-foreground px-1 py-0.5 rounded">
                current
              </span>
            )}
          </button>
        );
      })}
    </>
  );
}

/** Format "2026-03-14_183040" → "Mar 14, 18:30" */
function formatTimestamp(ts: string): string {
  const match = ts.match(/^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})(\d{2})$/);
  if (!match) return ts;
  const [, , month, day, hour, minute] = match;
  const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const m = months[parseInt(month, 10) - 1] || month;
  return `${m} ${parseInt(day, 10)}, ${hour}:${minute}`;
}
