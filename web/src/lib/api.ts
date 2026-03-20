const BASE = "/api";

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { signal });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/* Types */

export interface Attempt {
  commit_hash: string;
  agent_id: string;
  title: string;
  score: number | null;
  status: string;
  parent_hash: string | null;
  timestamp: string;
  feedback: string;
}

export interface Note {
  date: string;
  title: string;
  body: string;
  creator?: string;
  filename?: string;
  index: number;
}

export interface Skill {
  name: string;
  description: string;
  creator: string;
  created: string;
  path: string;
}

export interface SkillDetail {
  content: string;
  metadata: Record<string, string>;
  body: string;
  files: string[];
}

export interface AgentStatus {
  agent_id: string;
  status: "active" | "idle" | "stopped";
  sessions: number;
  last_activity: number;
  attempts: number;
  best_score: number | null;
}

export interface RunStatus {
  manager_alive: boolean;
  manager_pid: number | null;
  eval_count: number;
  total_attempts: number;
  scored_attempts: number;
  crashed_attempts: number;
  best_score: number | null;
  best_title: string | null;
  agents: AgentStatus[];
}

export interface LogEntry {
  type:
    | "thinking" | "tool_call" | "tool_result" | "text" | "system" | "error"
    | "coral_prompt" | "subagent_start" | "subagent_progress" | "subagent_done"
    | "compact" | "result";
  content: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  details: Record<string, any>;
  timestamp: string;
}

export interface LogTurn {
  index: number;
  entries: LogEntry[];
  usage: {
    input_tokens?: number;
    output_tokens?: number;
    cache_creation?: number;
    cache_read?: number;
  };
  timestamp: string;
}

export interface SessionMeta {
  total_cost_usd?: number;
  duration_ms?: number;
  duration_api_ms?: number;
  num_turns?: number;
  stop_reason?: string;
  session_id?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  usage?: Record<string, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  model_usage?: Record<string, any>;
}

export interface LogSession {
  session_index: number;
  turns: LogTurn[];
  meta?: SessionMeta;
}

export interface LogData {
  agent_id: string;
  log_files: Array<{
    path: string;
    index: number;
    size_bytes: number;
    modified: number;
  }>;
  turns: LogTurn[];
  sessions?: LogSession[];
  agent_meta?: {
    total_cost_usd?: number;
    duration_ms?: number;
    duration_api_ms?: number;
    num_turns?: number;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    usage?: Record<string, any>;
  };
}

export interface RunInfo {
  timestamp: string;
  status: "running" | "stopped";
  attempts: number;
  is_latest: boolean;
}

export interface TaskRuns {
  slug: string;
  runs: RunInfo[];
}

export interface RunsResponse {
  current: { task: string; run: string };
  tasks: TaskRuns[];
}

export interface TaskConfig {
  task: {
    name: string;
    description: string;
    files?: string[];
    tips?: string[];
  };
  grader: {
    type: string;
    timeout?: number;
    direction?: "maximize" | "minimize";
  };
  agents: {
    count: number;
    model: string;
    max_turns: number;
    reflect_every: number;
  };
}

/* API functions */

export const api = {
  config: () => get<TaskConfig>("/config"),
  attempts: () => get<Attempt[]>("/attempts"),
  leaderboard: (top = 20) => get<Attempt[]>(`/leaderboard?top=${top}`),
  attempt: (hash: string) => get<Attempt>(`/attempts/${hash}`),
  agentAttempts: (id: string) => get<Attempt[]>(`/attempts/agent/${id}`),
  notes: () => get<Note[]>("/notes"),
  skills: () => get<Skill[]>("/skills"),
  skill: (name: string) => get<SkillDetail>(`/skills/${name}`),
  logs: (agentId: string, signal?: AbortSignal) => get<LogData>(`/logs/${agentId}`, signal),
  logsList: () => get<Record<string, Array<{ path: string; index: number; size_bytes: number; modified: number }>>>("/logs"),
  status: () => get<RunStatus>("/status"),
  runs: () => get<RunsResponse>("/runs"),
  switchRun: (task: string, run: string) =>
    post<{ ok: boolean; task: string; run: string }>("/runs/switch", { task, run }),
};
