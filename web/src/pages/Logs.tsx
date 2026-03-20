import { useCallback, useEffect, useRef, useState } from "react";
import { api, type LogData, type LogTurn, type LogSession, type LogEntry, type RunStatus, type Attempt } from "../lib/api";
import { useSSE } from "../hooks/useSSE";
import StatusBadge from "../components/StatusBadge";

export default function Logs() {
  const [agentList, setAgentList] = useState<string[]>([]);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [logData, setLogData] = useState<LogData | null>(null);
  const [agentAttempts, setAgentAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(false);
  const logPanelRef = useRef<HTMLDivElement>(null);
  const userHasScrolled = useRef(false);
  const prevSelectedAgent = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fetchInFlight = useRef(false);

  // Track when user scrolls away from bottom
  useEffect(() => {
    const el = logPanelRef.current;
    if (!el) return;
    const onScroll = () => {
      const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
      userHasScrolled.current = !atBottom;
    };
    el.addEventListener("scroll", onScroll);
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Load agent list + status
  useEffect(() => {
    api.logsList().then((data) => {
      const agents = Object.keys(data).sort();
      setAgentList(agents);
      setSelectedAgent((prev) => prev ?? (agents.length > 0 ? agents[0] : null));
    }).catch(() => {});
    api.status().then(setStatus).catch(() => {});
  }, []);

  // Fetch logs + attempts for selected agent (debounced, with abort)
  const fetchAgentData = useCallback((agentId: string) => {
    if (fetchInFlight.current) return; // skip if already fetching
    fetchInFlight.current = true;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    api.logs(agentId, ac.signal)
      .then(setLogData)
      .catch(() => {})
      .finally(() => { fetchInFlight.current = false; });
    api.agentAttempts(agentId).then(setAgentAttempts).catch(() => setAgentAttempts([]));
  }, []);

  // Reset and load when agent changes
  useEffect(() => {
    if (!selectedAgent) return;
    abortRef.current?.abort();
    const ac = new AbortController();
    abortRef.current = ac;
    fetchInFlight.current = false;
    setLogData(null); // eslint-disable-line react-hooks/set-state-in-effect -- reset before fetch
    setLoading(true);
    api.logs(selectedAgent, ac.signal).then((data) => {
      setLogData(data);
      setLoading(false);
    }).catch(() => setLoading(false));
    api.agentAttempts(selectedAgent).then(setAgentAttempts).catch(() => setAgentAttempts([]));
    return () => ac.abort();
  }, [selectedAgent]);

  // Scroll to bottom only on initial load or agent switch
  useEffect(() => {
    if (!logData) return;
    const agentChanged = selectedAgent !== prevSelectedAgent.current;
    if (agentChanged) {
      prevSelectedAgent.current = selectedAgent;
      userHasScrolled.current = false;
    }
    if (!userHasScrolled.current) {
      requestAnimationFrame(() => {
        logPanelRef.current?.scrollTo({ top: logPanelRef.current.scrollHeight });
      });
    }
  }, [logData, selectedAgent]);

  useSSE({
    "log:update": () => {
      // Debounce: coalesce rapid SSE updates into one fetch
      if (refreshTimer.current) clearTimeout(refreshTimer.current);
      refreshTimer.current = setTimeout(() => {
        if (selectedAgent) fetchAgentData(selectedAgent);
      }, 2000);
    },
    "attempt:new": () => {
      api.status().then(setStatus).catch(() => {});
      if (selectedAgent) api.agentAttempts(selectedAgent).then(setAgentAttempts).catch(() => {});
    },
  });

  const getAgentStatus = (id: string) =>
    status?.agents.find((a) => a.agent_id === id);

  return (
    <>
      {/* LEFT COLUMN — Agent list + per-agent attempts */}
      <div className="overflow-y-auto border-r border-border p-5">
        <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
          Agents
        </p>

        {agentList.length === 0 ? (
          <p className="font-mono text-xs text-muted-fg">No agents</p>
        ) : (
          <div className="space-y-2">
            {agentList.map((id) => {
              const agent = getAgentStatus(id);
              const isSelected = selectedAgent === id;
              return (
                <button
                  key={id}
                  onClick={() => setSelectedAgent(id)}
                  className={`w-full text-left p-4 rounded-lg transition-colors duration-100 border ${
                    isSelected
                      ? "bg-foreground text-background border-foreground"
                      : "border-border hover:bg-muted/50"
                  }`}
                >
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-mono text-[13px] font-medium truncate">
                      {id}
                    </span>
                    {agent && <StatusBadge status={agent.status} />}
                  </div>
                  {agent && (
                    <div
                      className={`font-mono text-[11px] grid grid-cols-2 gap-y-1 gap-x-4 ${
                        isSelected ? "text-background/60" : "text-muted-fg"
                      }`}
                    >
                      <span>{agent.attempts} attempts</span>
                      <span>{agent.sessions} sessions</span>
                      <span>
                        best{" "}
                        {agent.best_score != null
                          ? agent.best_score.toFixed(4)
                          : "---"}
                      </span>
                      <span>
                        {agent.last_activity
                          ? new Date(agent.last_activity * 1000).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "---"}
                      </span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* Per-agent recent attempts */}
        {selectedAgent && agentAttempts.length > 0 && (
          <div className="mt-6">
            <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
              Recent Attempts
            </p>
            <div className="border border-border rounded-xl overflow-hidden">
              {[...agentAttempts].sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, 10).map((a) => (
                <div
                  key={a.commit_hash}
                  className="flex items-center gap-3 py-2.5 px-3 border-b border-border last:border-b-0"
                >
                  <span className="font-mono text-[12px] font-medium shrink-0">
                    {a.score != null ? String(a.score) : "---"}
                  </span>
                  <span className="shrink-0"><StatusBadge status={a.status} /></span>
                  <span className="font-mono text-[10px] text-muted-fg ml-auto whitespace-nowrap">
                    {formatRelativeTime(a.timestamp)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* RIGHT COLUMN — Log content */}
      <div ref={logPanelRef} className="overflow-y-auto p-5">
        {!selectedAgent ? (
          <p className="font-mono text-xs text-muted-fg py-6">
            Select an agent to view logs.
          </p>
        ) : loading && !logData ? (
          <p className="font-mono text-xs text-muted-fg py-6">Loading logs...</p>
        ) : !logData || logData.turns.length === 0 ? (
          <p className="font-mono text-xs text-muted-fg py-6">No log entries.</p>
        ) : (
          <>
            {/* Stats bar */}
            <div className="flex items-center gap-4 mb-4 font-mono text-[11px] text-muted-fg flex-wrap">
              <span>{logData.turns.length} turns</span>
              <span>{logData.sessions?.length ?? 1} session{(logData.sessions?.length ?? 1) !== 1 ? "s" : ""}</span>
              {logData.agent_meta ? (
                <AgentMetaSummary meta={logData.agent_meta} />
              ) : (
                <TokenSummary turns={logData.turns} />
              )}
            </div>

            {/* Sessions + turns */}
            {(logData.sessions || [{ session_index: 0, turns: logData.turns }]).map(
              (session, i, arr) => (
                <SessionBlock
                  key={session.session_index}
                  session={session as LogSession}
                  totalSessions={logData.sessions?.length || 1}
                  defaultCollapsed={i < arr.length - 1}
                />
              )
            )}
          </>
        )}
      </div>
    </>
  );
}

function formatRelativeTime(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
  } catch {
    return iso.slice(0, 16);
  }
}

function TokenSummary({ turns }: { turns: LogTurn[] }) {
  let input = 0, output = 0, cacheRead = 0, cacheCreation = 0;
  for (const t of turns) {
    input += t.usage.input_tokens || 0;
    output += t.usage.output_tokens || 0;
    cacheRead += t.usage.cache_read || 0;
    cacheCreation += t.usage.cache_creation || 0;
  }
  const totalIn = input + cacheRead + cacheCreation;
  return (
    <>
      <span>in {totalIn.toLocaleString()}</span>
      <span>out {output.toLocaleString()}</span>
      {(cacheRead > 0 || cacheCreation > 0) && (
        <span className="opacity-60">
          (cache r {cacheRead.toLocaleString()} / w {cacheCreation.toLocaleString()})
        </span>
      )}
    </>
  );
}

function SessionBlock({
  session,
  totalSessions,
  defaultCollapsed = false,
}: {
  session: LogSession;
  totalSessions: number;
  defaultCollapsed?: boolean;
}) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <div className="mb-1.5">
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 py-2 px-3 bg-foreground text-background font-mono text-[11px] tracking-widest uppercase hover:opacity-90 transition-opacity rounded-t-lg"
      >
        <span>
          Session {session.session_index + 1}
          {totalSessions > 1 ? ` / ${totalSessions}` : ""}
        </span>
        <span className="opacity-60">{session.turns.length} turns</span>
        {session.meta?.duration_ms != null && session.meta.duration_ms > 0 && (
          <span className="opacity-60 normal-case tracking-normal">
            {(session.meta.duration_ms / 1000).toFixed(0)}s
          </span>
        )}
        <span className="ml-auto">{collapsed ? "▼" : "▲"}</span>
      </button>
      <div
        className="grid transition-[grid-template-rows] duration-300 ease-in-out"
        style={{ gridTemplateRows: collapsed ? "0fr" : "1fr" }}
      >
        <div className="overflow-hidden">
          {session.turns.map((turn) => (
            <TurnCard key={turn.index} turn={turn} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TurnCard({ turn }: { turn: LogTurn }) {
  const [expandThinking, setExpandThinking] = useState(false);

  return (
    <div className="py-4 border-b border-border">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-mono text-[11px] bg-foreground text-background px-1.5 py-0.5 rounded-md">
          T{turn.index + 1}
        </span>
        {(turn.usage.output_tokens || turn.usage.input_tokens) && (
          <span className="font-mono text-[11px] text-muted-fg">
            {((turn.usage.input_tokens || 0) + (turn.usage.cache_read || 0) + (turn.usage.cache_creation || 0)).toLocaleString()} in · {(turn.usage.output_tokens || 0).toLocaleString()} out
          </span>
        )}
      </div>

      {turn.entries.map((entry, i) => (
        <div key={i} className="mb-2">
          {entry.type === "thinking" && (
            <div className="border-l-2 border-border pl-3">
              <div className="font-mono text-[11px] text-muted-fg flex items-center gap-1.5">
                <span className="tracking-widest uppercase">Think</span>
                <button
                  onClick={() => setExpandThinking(!expandThinking)}
                  className="hover:text-foreground underline decoration-dotted underline-offset-2"
                >
                  {expandThinking ? "▲" : "▼"}
                </button>
              </div>
              {expandThinking && (
                <pre className="mt-1.5 font-mono text-[11px] text-muted-fg leading-relaxed whitespace-pre-wrap max-h-80 overflow-y-auto">
                  {entry.content}
                </pre>
              )}
              {!expandThinking && (
                <p className="mt-0.5 font-mono text-[11px] text-muted-fg truncate opacity-50">
                  {entry.content.split("\n")[0]}
                </p>
              )}
            </div>
          )}

          {entry.type === "tool_call" && (
            <div className="flex items-start gap-2 p-2 border border-border bg-muted/50 rounded-lg">
              <span className="font-mono text-[11px] bg-foreground text-background px-1.5 py-0.5 rounded-md shrink-0">
                {entry.content}
              </span>
              <span className="font-mono text-[11px] text-muted-fg truncate">
                {entry.details?.input_summary}
              </span>
            </div>
          )}

          {entry.type === "tool_result" && (
            <ToolResult content={entry.content} />
          )}

          {entry.type === "text" && (
            <div className="font-body text-[13px] leading-relaxed pl-1">
              {entry.content}
            </div>
          )}

          {entry.type === "system" && (
            <SystemInit entry={entry} />
          )}

          {entry.type === "coral_prompt" && (
            <CoralPrompt
              content={entry.content}
              source={entry.details?.source}
              taskName={entry.details?.task_name}
            />
          )}

          {entry.type === "subagent_start" && (
            <SubagentStart entry={entry} />
          )}

          {entry.type === "subagent_progress" && (
            <SubagentProgress entry={entry} />
          )}

          {entry.type === "subagent_done" && (
            <SubagentDone entry={entry} />
          )}

          {entry.type === "compact" && (
            <CompactBoundary entry={entry} />
          )}

          {entry.type === "result" && (
            <ResultEntry entry={entry} />
          )}
        </div>
      ))}
    </div>
  );
}

function CoralPrompt({ content, source, taskName }: {
  content: string;
  source?: string;
  taskName?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLong = content.split("\n").length > 5;

  const label =
    source?.startsWith("heartbeat:") ? source.replace("heartbeat:", "").toUpperCase()
    : source === "start" ? "START"
    : source === "restart" ? "RESTART"
    : (source || "CORAL").toUpperCase();

  const accentClass =
    source?.includes("reflect") ? "border-amber-500/60 bg-amber-500/5"
    : source?.includes("consolidate") ? "border-blue-500/60 bg-blue-500/5"
    : source === "start" ? "border-emerald-500/60 bg-emerald-500/5"
    : "border-purple-500/60 bg-purple-500/5";

  const badgeClass =
    source?.includes("reflect") ? "bg-amber-500 text-white"
    : source?.includes("consolidate") ? "bg-blue-500 text-white"
    : source === "start" ? "bg-emerald-500 text-white"
    : "bg-purple-500 text-white";

  return (
    <div className={`border-l-2 rounded-r-lg p-3 ${accentClass}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className={`font-mono text-[10px] tracking-widest px-1.5 py-0.5 rounded-md ${badgeClass}`}>
          {label}
        </span>
        {taskName && (
          <span className="font-mono text-[11px] font-medium">{taskName}</span>
        )}
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="font-mono text-[11px] text-muted-fg hover:text-foreground underline decoration-dotted underline-offset-2"
          >
            {expanded ? "▲" : "▼"}
          </button>
        )}
      </div>
      <pre
        className={`font-mono text-[11px] leading-relaxed whitespace-pre-wrap ${
          !expanded && isLong ? "max-h-24 overflow-hidden relative" : ""
        }`}
      >
        {content}
      </pre>
    </div>
  );
}

function ToolResult({ content }: { content: string }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = content.split("\n").length > 5;

  return (
    <div className="ml-4 border-l border-border pl-3">
      <div className="font-mono text-[11px] text-muted-fg flex items-center gap-1.5">
        <span>Result {isLong && `(${content.split("\n").length}L)`}</span>
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="hover:text-foreground underline decoration-dotted underline-offset-2"
          >
            {expanded ? "▲" : "▼"}
          </button>
        )}
      </div>
      <pre
        className={`mt-0.5 font-mono text-[11px] text-muted-fg leading-relaxed whitespace-pre-wrap ${
          !expanded && isLong ? "max-h-20 overflow-hidden" : ""
        }`}
      >
        {content}
      </pre>
    </div>
  );
}

function SystemInit({ entry }: { entry: LogEntry }) {
  const [expanded, setExpanded] = useState(false);
  const skills = entry.details?.skills as string[] | undefined;
  const agents = entry.details?.agents as string[] | undefined;
  const tools = entry.details?.tools as string[] | undefined;
  const version = entry.details?.claude_code_version as string | undefined;
  const hasDetails = (skills && skills.length > 0) || (agents && agents.length > 0);

  return (
    <div className="font-mono text-[11px] text-muted-fg">
      <div className="flex items-center gap-2">
        <span className="italic">{entry.content}</span>
        {version && <span className="opacity-50">v{version}</span>}
        {hasDetails && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="hover:text-foreground underline decoration-dotted underline-offset-2"
          >
            {expanded ? "▲" : "▼"}
          </button>
        )}
      </div>
      {expanded && (
        <div className="mt-1.5 ml-2 space-y-1">
          {skills && skills.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-muted-fg/60 shrink-0">skills:</span>
              {skills.map((s) => (
                <span key={s} className="bg-muted px-1.5 py-0.5 rounded text-[10px]">{s}</span>
              ))}
            </div>
          )}
          {agents && agents.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-muted-fg/60 shrink-0">agents:</span>
              {agents.map((a) => (
                <span key={a} className="bg-muted px-1.5 py-0.5 rounded text-[10px]">{a}</span>
              ))}
            </div>
          )}
          {tools && tools.length > 0 && (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-muted-fg/60 shrink-0">tools:</span>
              {tools.map((t) => (
                <span key={t} className="bg-muted px-1.5 py-0.5 rounded text-[10px]">{t}</span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function SubagentStart({ entry }: { entry: LogEntry }) {
  return (
    <div className="flex items-start gap-2 p-2 border border-border bg-muted/50 rounded-lg">
      <span className="font-mono text-[11px] bg-foreground text-background px-1.5 py-0.5 rounded-md shrink-0">
        Subagent
      </span>
      <span className="font-mono text-[11px] text-muted-fg truncate">
        {entry.content}
      </span>
    </div>
  );
}

function SubagentProgress({ entry }: { entry: LogEntry }) {
  const description = entry.details?.description as string | undefined;

  return (
    <div className="ml-4 flex items-center gap-2 py-0.5">
      <span className="w-1 h-1 rounded-full bg-cyan-500/60 shrink-0" />
      <span className="font-mono text-[10px] bg-cyan-500/20 text-cyan-700 dark:text-cyan-300 px-1.5 py-0.5 rounded shrink-0">
        {entry.content}
      </span>
      {description && (
        <span className="font-mono text-[10px] text-muted-fg truncate">
          {description}
        </span>
      )}
    </div>
  );
}

function SubagentDone({ entry }: { entry: LogEntry }) {
  const totalTokens = entry.details?.total_tokens as number | undefined;
  const toolUses = entry.details?.tool_uses as number | undefined;
  const durationMs = entry.details?.duration_ms as number | undefined;

  const stats = [
    toolUses != null ? `${toolUses} tools` : null,
    totalTokens != null ? `${totalTokens.toLocaleString()} tok` : null,
    durationMs != null ? `${(durationMs / 1000).toFixed(1)}s` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className="flex items-start gap-2 p-2 border border-border bg-muted/50 rounded-lg">
      <span className="font-mono text-[11px] bg-foreground text-background px-1.5 py-0.5 rounded-md shrink-0">
        Done
      </span>
      <span className="font-mono text-[11px] text-muted-fg truncate">
        {entry.content}{stats ? ` — ${stats}` : ""}
      </span>
    </div>
  );
}

function CompactBoundary({ entry }: { entry: LogEntry }) {
  const preTokens = entry.details?.pre_tokens as number | undefined;

  return (
    <div className="flex items-center gap-3 py-1">
      <div className="flex-1 border-t border-dashed border-amber-500/40" />
      <span className="font-mono text-[10px] text-amber-600 dark:text-amber-400 shrink-0">
        {entry.content}
        {preTokens ? ` — ${preTokens.toLocaleString()} tokens` : ""}
      </span>
      <div className="flex-1 border-t border-dashed border-amber-500/40" />
    </div>
  );
}

function ResultEntry({ entry }: { entry: LogEntry }) {
  const duration = entry.details?.duration_ms as number | undefined;
  const numTurns = entry.details?.num_turns as number | undefined;
  const stopReason = entry.details?.stop_reason as string | undefined;

  return (
    <div className="border border-border rounded-lg p-2.5 bg-muted/30">
      <div className="flex items-center gap-3 font-mono text-[11px] flex-wrap">
        <span className="font-medium">Session Complete</span>
        {stopReason && <span className="text-muted-fg">{stopReason}</span>}
        <span className="text-muted-fg ml-auto flex gap-3">
          {numTurns != null && <span>{numTurns} turns</span>}
          {duration != null && <span>{(duration / 1000).toFixed(0)}s</span>}
        </span>
      </div>
      {entry.content && (
        <p className="font-body text-[12px] text-muted-fg mt-1.5 truncate">
          {entry.content}
        </p>
      )}
    </div>
  );
}

function AgentMetaSummary({ meta }: { meta: NonNullable<LogData["agent_meta"]> }) {
  const usage = meta.usage || {};
  const totalIn = (usage.input_tokens || 0) + (usage.cache_read_input_tokens || 0) + (usage.cache_creation_input_tokens || 0);
  const totalOut = usage.output_tokens || 0;

  return (
    <>
      <span>in {totalIn.toLocaleString()}</span>
      <span>out {totalOut.toLocaleString()}</span>
      {meta.duration_ms != null && meta.duration_ms > 0 && (
        <span>{(meta.duration_ms / 60000).toFixed(1)}min</span>
      )}
    </>
  );
}
