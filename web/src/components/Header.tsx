import { useEffect, useState } from "react";
import { api, type RunStatus } from "../lib/api";
import { useSSE } from "../hooks/useSSE";
import RunSelector from "./RunSelector";

type Tab = "overview" | "knowledge" | "logs";

interface Props {
  activeTab: Tab;
  onTabChange: (tab: Tab) => void;
}

const tabs: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "knowledge", label: "Knowledge" },
  { key: "logs", label: "Logs" },
];

export default function Header({ activeTab, onTabChange }: Props) {
  const [status, setStatus] = useState<RunStatus | null>(null);

  const refresh = () => {
    api.status().then(setStatus).catch(() => {});
  };

  useEffect(refresh, []);
  useSSE({
    "attempt:new": refresh,
    "attempt:update": refresh,
    "eval:update": refresh,
  });

  const activeAgents = status?.agents.filter((a) => a.status === "active").length ?? 0;

  return (
    <header className="sticky top-0 z-50 bg-background border-b border-border px-6 py-2.5 flex items-center gap-6">
      {/* Branding + task */}
      <div className="flex items-center gap-3 shrink-0">
        <span className="font-display text-base font-bold tracking-tight">CORAL</span>
        <span className="text-border-strong">/</span>
        <RunSelector />
      </div>

      {/* Tab pills */}
      <nav className="flex items-center gap-1 ml-auto">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            className={`px-4 py-1.5 text-[13px] font-body rounded-lg transition-colors duration-100 ${
              activeTab === t.key
                ? "bg-foreground text-background font-medium"
                : "text-muted-fg hover:text-foreground hover:bg-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Live stats */}
      <div className="flex items-center gap-3 shrink-0 font-mono text-[11px] text-muted-fg">
        {status && (
          <>
            <span className="flex items-center gap-1.5">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  status.manager_alive ? "bg-green-500" : "bg-border-strong"
                }`}
              />
              {activeAgents > 0
                ? `${activeAgents} active`
                : status.manager_alive
                ? "idle"
                : "stopped"}
            </span>
            <span>{status.total_attempts} att</span>
            {status.best_score != null && (
              <span>best {status.best_score.toFixed(4)}</span>
            )}
            <span>#{status.eval_count}</span>
          </>
        )}
      </div>
    </header>
  );
}
