import { useEffect, useState } from "react";
import { api, type Attempt, type TaskConfig, type RunStatus, type Note, type Skill, type LogData, type LogEntry } from "../lib/api";
import { useSSE } from "../hooks/useSSE";
import ScoreChart from "../components/ScoreChart";
import ChartModal from "../components/ChartModal";
import AttemptRow from "../components/AttemptRow";
import StatusBadge from "../components/StatusBadge";

type SortKey = "score" | "agent_id" | "timestamp";

export default function Overview() {
  const [config, setConfig] = useState<TaskConfig | null>(null);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [notes, setNotes] = useState<Note[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [agentLogs, setAgentLogs] = useState<Record<string, LogData>>({});
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortAsc, setSortAsc] = useState(false);
  const [expandedHash, setExpandedHash] = useState<string | null>(null);
  const [expandedNote, setExpandedNote] = useState<number | null>(null);
  const [chartExpanded, setChartExpanded] = useState(false);

  const refresh = () => {
    api.config().then(setConfig).catch(() => {});
    api.attempts().then(setAttempts).catch(() => {});
    api.status().then(setStatus).catch(() => {});
    api.notes().then(setNotes).catch(() => {});
    api.skills().then(setSkills).catch(() => {});
  };

  const refreshLogs = () => {
    if (!status) return;
    for (const agent of status.agents) {
      api.logs(agent.agent_id).then((data) => {
        setAgentLogs((prev) => ({ ...prev, [agent.agent_id]: data }));
      }).catch(() => {});
    }
  };

  useEffect(refresh, []);
  useEffect(refreshLogs, [status]);
  useSSE({
    "attempt:new": refresh,
    "attempt:update": refresh,
    "eval:update": refresh,
    "note:update": () => {
      api.notes().then(setNotes).catch(() => {});
      api.skills().then(setSkills).catch(() => {});
    },
    "log:update": refreshLogs,
  });

  const scored = attempts.filter((a) => a.score !== null);

  const allSorted = [...attempts].sort((a, b) => {
    // Null scores always sort to the bottom, regardless of direction
    if (sortKey === "score") {
      if (a.score === null && b.score === null) return 0;
      if (a.score === null) return 1;
      if (b.score === null) return -1;
    }
    let cmp = 0;
    switch (sortKey) {
      case "score":
        cmp = a.score! - b.score!;
        break;
      case "agent_id":
        cmp = a.agent_id.localeCompare(b.agent_id);
        break;
      case "timestamp":
        cmp = a.timestamp.localeCompare(b.timestamp);
        break;
    }
    return sortAsc ? cmp : -cmp;
  });

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc(!sortAsc);
    else {
      setSortKey(key);
      setSortAsc(key === "timestamp" || key === "agent_id");
    }
  };

  const direction =
    config?.grader?.direction === "minimize" ? "minimize" : "maximize";

  // Get last 3 tool_call/text entries across all turns for an agent
  const getRecentEntries = (agentId: string): { turnIndex: number; entry: LogEntry }[] => {
    const data = agentLogs[agentId];
    if (!data || data.turns.length === 0) return [];
    const results: { turnIndex: number; entry: LogEntry }[] = [];
    for (let i = data.turns.length - 1; i >= 0 && results.length < 3; i--) {
      const turn = data.turns[i];
      for (let j = turn.entries.length - 1; j >= 0 && results.length < 3; j--) {
        const e = turn.entries[j];
        if (e.type === "tool_call" || e.type === "text") {
          results.push({ turnIndex: turn.index, entry: e });
        }
      }
    }
    return results;
  };

  return (
    <>
      {/* LEFT COLUMN */}
      <div className="overflow-y-auto border-r border-border p-5">
        {/* Score chart — always shown */}
        <div className="mb-5">
          <div className="border border-border rounded-xl p-4 relative">
            <button
              onClick={() => setChartExpanded(true)}
              className="absolute top-2.5 right-2.5 w-6 h-6 flex items-center justify-center rounded-md hover:bg-muted transition-colors duration-100 text-muted-fg hover:text-foreground z-10"
              title="Expand chart"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
            </button>
            <ScoreChart attempts={attempts} height={200} direction={direction} />
          </div>
        </div>

        {chartExpanded && (
          <ChartModal
            attempts={attempts}
            direction={direction}
            onClose={() => setChartExpanded(false)}
          />
        )}

        {/* Leaderboard */}
        <div className="mb-6">
          <div className="flex items-baseline justify-between mb-3">
            <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg">
              Attempts
            </p>
            <p className="font-mono text-[11px] text-muted-fg">
              {scored.length} scored / {attempts.length} total
            </p>
          </div>

          <div className="border border-border rounded-xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-muted/50">
                  <Th label="#" />
                  <Th
                    label="Score"
                    active={sortKey === "score"}
                    asc={sortAsc}
                    onClick={() => toggleSort("score")}
                  />
                  <Th
                    label="Agent"
                    active={sortKey === "agent_id"}
                    asc={sortAsc}
                    onClick={() => toggleSort("agent_id")}
                  />
                  <Th label="Status" />
                  <Th
                    label="Time"
                    active={sortKey === "timestamp"}
                    asc={sortAsc}
                    onClick={() => toggleSort("timestamp")}
                  />
                </tr>
              </thead>
              <tbody>
                {allSorted.map((a, i) => (
                  <AttemptRow
                    key={a.commit_hash}
                    attempt={a}
                    rank={i + 1}
                    expanded={expandedHash === a.commit_hash}
                    onToggle={() =>
                      setExpandedHash(
                        expandedHash === a.commit_hash ? null : a.commit_hash
                      )
                    }
                  />
                ))}
              </tbody>
            </table>

            {allSorted.length === 0 && (
              <p className="py-8 text-center font-mono text-xs text-muted-fg">
                No attempts yet.
              </p>
            )}
          </div>
        </div>

        {/* Notes */}
        <div className="mb-6">
          <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
            Notes ({notes.length})
          </p>
          {notes.length === 0 ? (
            <p className="font-mono text-xs text-muted-fg">No notes yet.</p>
          ) : (
            <div className="border border-border rounded-xl overflow-hidden">
              {[...notes].reverse().slice(0, 5).map((note) => (
                <div key={note.index} className="border-b border-border last:border-b-0">
                  <button
                    onClick={() =>
                      setExpandedNote(
                        expandedNote === note.index ? null : note.index
                      )
                    }
                    className="w-full text-left py-2.5 px-3 hover:bg-muted/50 transition-colors duration-100 flex items-start gap-2"
                  >
                    <div className="mt-1 shrink-0">
                      <div className="w-2 h-2 border-2 border-foreground bg-background rounded-full" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="font-mono text-[10px] text-muted-fg">
                        {note.date}
                      </p>
                      <p className="font-display text-[13px] font-semibold leading-snug truncate">
                        {note.title}
                      </p>
                    </div>
                    <span className="font-mono text-xs text-muted-fg shrink-0">
                      {expandedNote === note.index ? "−" : "+"}
                    </span>
                  </button>
                  {expandedNote === note.index && (
                    <div className="pb-3 pl-7 pr-3">
                      <div className="border-l-2 border-border pl-3">
                        <p className="font-body text-[12px] leading-relaxed text-muted-fg whitespace-pre-wrap">
                          {note.body}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Skills */}
        <div>
          <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
            Skills ({skills.length})
          </p>
          {skills.length === 0 ? (
            <p className="font-mono text-xs text-muted-fg">No skills yet.</p>
          ) : (
            <div className="space-y-2">
              {skills.map((skill) => (
                <div
                  key={skill.name}
                  className="p-3 border border-border rounded-lg hover:bg-muted/50 transition-colors duration-100"
                >
                  <p className="font-display text-[13px] font-semibold mb-0.5">
                    {skill.name}
                  </p>
                  {skill.description && (
                    <p className="font-body text-[12px] text-muted-fg truncate">
                      {skill.description}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* RIGHT COLUMN */}
      <div className="overflow-y-auto p-5 space-y-6">
        {/* Agent cards */}
        {status && status.agents.length > 0 && (
          <div>
            <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
              Agents
            </p>
            <div className="space-y-2">
              {status.agents.map((agent) => (
                <div
                  key={agent.agent_id}
                  className="p-3 border border-border rounded-lg bg-muted/50"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-[12px] font-medium">
                      {agent.agent_id}
                    </span>
                    <StatusBadge status={agent.status} />
                  </div>
                  <div className="font-mono text-[11px] text-muted-fg flex gap-3">
                    <span>{agent.attempts} att</span>
                    <span>{agent.sessions} sess</span>
                    <span>
                      best{" "}
                      {agent.best_score != null
                        ? agent.best_score.toFixed(4)
                        : "---"}
                    </span>
                  </div>
                  {agentLogs[agent.agent_id] && (() => {
                    const data = agentLogs[agent.agent_id];
                    let input = 0, output = 0, cacheRead = 0, cacheCreation = 0;
                    for (const t of data.turns) {
                      input += t.usage.input_tokens || 0;
                      output += t.usage.output_tokens || 0;
                      cacheRead += t.usage.cache_read || 0;
                      cacheCreation += t.usage.cache_creation || 0;
                    }
                    const totalIn = input + cacheRead + cacheCreation;
                    return (
                      <div className="font-mono text-[11px] text-muted-fg flex gap-3 mt-1">
                        <span>{totalIn.toLocaleString()} in</span>
                        <span>{output.toLocaleString()} out</span>
                      </div>
                    );
                  })()}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent Agent Logs — last 3 entries per agent */}
        {status && status.agents.length > 0 && (
          <div>
            <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
              Recent Activity
            </p>
            <div className="space-y-3">
              {status.agents.map((agent) => {
                const entries = getRecentEntries(agent.agent_id);
                if (entries.length === 0) return (
                  <div key={agent.agent_id} className="p-3 border border-border rounded-lg">
                    <span className="font-mono text-[11px] font-medium">{agent.agent_id}</span>
                    <p className="font-mono text-[10px] text-muted-fg mt-1">Waiting for activity...</p>
                  </div>
                );
                return (
                  <div
                    key={agent.agent_id}
                    className="p-3 border border-border rounded-lg"
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-mono text-[11px] font-medium">
                        {agent.agent_id}
                      </span>
                    </div>
                    <div className="space-y-1.5">
                      {entries.map(({ turnIndex, entry }, i) => (
                        <div key={i} className="flex items-center gap-2">
                          <span className="font-mono text-[9px] text-muted-fg shrink-0">
                            T{turnIndex + 1}
                          </span>
                          {entry.type === "tool_call" && (
                            <>
                              <span className="font-mono text-[10px] bg-foreground text-background px-1.5 py-0.5 rounded-md shrink-0">
                                {entry.content}
                              </span>
                              <span className="font-mono text-[10px] text-muted-fg truncate">
                                {entry.details?.input_summary}
                              </span>
                            </>
                          )}
                          {entry.type === "text" && (
                            <p className="font-body text-[11px] text-muted-fg truncate">
                              {entry.content}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function Th({
  label,
  active,
  asc,
  onClick,
}: {
  label: string;
  active?: boolean;
  asc?: boolean;
  onClick?: () => void;
}) {
  return (
    <th
      className={`py-2 px-3 text-left font-mono text-[10px] tracking-widest uppercase ${
        onClick ? "cursor-pointer hover:bg-muted select-none" : ""
      } ${active ? "text-foreground" : "text-muted-fg"}`}
      onClick={onClick}
    >
      {label}
      {active && <span className="ml-1">{asc ? "↑" : "↓"}</span>}
    </th>
  );
}
