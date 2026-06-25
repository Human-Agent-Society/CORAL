import { useEffect, useRef, useState } from "react";
import { api, type ChatFrame } from "../lib/api";

interface Pending {
  prompt_id: string;
  tool_name: string;
  tool_input: Record<string, unknown>;
}

function textBlocks(frame: ChatFrame): string[] {
  const content = frame?.message?.content;
  if (!Array.isArray(content)) return [];
  return content.filter((b) => b?.type === "text").map((b) => String(b.text ?? ""));
}

function toolUses(frame: ChatFrame): { name: string; input: unknown }[] {
  const content = frame?.message?.content;
  if (!Array.isArray(content)) return [];
  return content
    .filter((b) => b?.type === "tool_use")
    .map((b) => ({ name: String(b.name ?? "tool"), input: b.input }));
}

function summarizeInput(input: unknown): string {
  if (input && typeof input === "object") {
    const obj = input as Record<string, unknown>;
    if (typeof obj.command === "string") return obj.command;
    if (typeof obj.file_path === "string") return obj.file_path;
  }
  const s = JSON.stringify(input ?? {});
  return s.length > 160 ? s.slice(0, 160) + "…" : s;
}

export default function Chat() {
  const [workdir, setWorkdir] = useState("");
  const [model, setModel] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [frames, setFrames] = useState<ChatFrame[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false);

  const [showScaffold, setShowScaffold] = useState(false);
  const [scaffoldName, setScaffoldName] = useState("");

  const scrollRef = useRef<HTMLDivElement>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [frames, pending]);

  useEffect(() => {
    if (!sessionId) return;
    const source = new EventSource(`/api/chat/${sessionId}/events`);
    esRef.current = source;
    source.addEventListener("frame", (e) => {
      try {
        const frame = JSON.parse((e as MessageEvent).data) as ChatFrame;
        if (frame.type === "awaiting_approval") {
          setPending({
            prompt_id: frame.prompt_id,
            tool_name: frame.tool_name,
            tool_input: frame.tool_input || {},
          });
        } else if (frame.type === "approval_resolved") {
          setPending((p) => (p && p.prompt_id === frame.prompt_id ? null : p));
        } else if (frame.type === "_closed") {
          setClosed(true);
        }
        setFrames((prev) => [...prev, frame]);
      } catch {
        // ignore malformed frames
      }
    });
    source.onerror = () => {};
    return () => {
      source.close();
      esRef.current = null;
    };
  }, [sessionId]);

  async function startSession() {
    setError(null);
    setBusy(true);
    try {
      const info = await api.chatStart(workdir.trim(), model.trim() || undefined);
      setFrames([]);
      setClosed(false);
      setPending(null);
      setSessionId(info.session_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function scaffold() {
    setError(null);
    setBusy(true);
    try {
      const res = await api.chatScaffold(workdir.trim(), scaffoldName.trim());
      setWorkdir(res.workdir);
      setShowScaffold(false);
      setScaffoldName("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function send() {
    if (!sessionId || !input.trim()) return;
    const text = input.trim();
    setInput("");
    setFrames((prev) => [...prev, { type: "_user_input", text }]);
    try {
      await api.chatSend(sessionId, text);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function resolve(decision: "allow" | "deny") {
    if (!sessionId || !pending) return;
    const pid = pending.prompt_id;
    setPending(null);
    try {
      await api.chatApprove(sessionId, pid, decision);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function stop() {
    if (!sessionId) return;
    try {
      await api.chatStop(sessionId);
    } catch {
      // ignore
    }
    esRef.current?.close();
    setSessionId(null);
    setFrames([]);
    setClosed(false);
    setPending(null);
  }

  if (!sessionId) {
    return (
      <div className="h-full flex items-center justify-center p-8 overflow-y-auto">
        <div className="w-full max-w-xl space-y-4">
          <h2 className="font-display text-xl">Chat</h2>
          <p className="text-sm text-muted-fg">
            Start a local Claude Code session in a working directory. It can author a
            task and launch <code className="font-mono">coral start</code> — you'll
            approve before any run launches.
          </p>
          <div className="space-y-1.5">
            <label className="text-xs font-mono text-muted-fg">Working directory (absolute)</label>
            <input
              value={workdir}
              onChange={(e) => setWorkdir(e.target.value)}
              placeholder="/Users/you/code/my-task"
              className="w-full px-3 py-2 text-sm font-mono bg-muted border border-border rounded-lg focus:outline-none focus:border-border-strong"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-mono text-muted-fg">Model (optional)</label>
            <input
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="opus"
              className="w-full px-3 py-2 text-sm font-mono bg-muted border border-border rounded-lg focus:outline-none focus:border-border-strong"
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={startSession}
              disabled={!workdir.trim() || busy}
              className="px-4 py-2 text-sm rounded-lg bg-foreground text-background font-medium disabled:opacity-40"
            >
              {busy ? "Starting…" : "Start session"}
            </button>
            <button
              onClick={() => setShowScaffold((s) => !s)}
              className="px-4 py-2 text-sm rounded-lg text-muted-fg hover:text-foreground hover:bg-muted"
            >
              New task…
            </button>
          </div>
          {showScaffold && (
            <div className="space-y-2 border-t border-border pt-3">
              <p className="text-xs text-muted-fg">
                Scaffold a new CORAL task (<code className="font-mono">coral init</code>)
                under the directory above, then start in it.
              </p>
              <div className="flex gap-2">
                <input
                  value={scaffoldName}
                  onChange={(e) => setScaffoldName(e.target.value)}
                  placeholder="task-name"
                  className="flex-1 px-3 py-2 text-sm font-mono bg-muted border border-border rounded-lg focus:outline-none focus:border-border-strong"
                />
                <button
                  onClick={scaffold}
                  disabled={!workdir.trim() || !scaffoldName.trim() || busy}
                  className="px-4 py-2 text-sm rounded-lg bg-foreground text-background font-medium disabled:opacity-40"
                >
                  Scaffold
                </button>
              </div>
            </div>
          )}
          {error && <div className="text-sm text-red-600 font-mono">{error}</div>}
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-3 px-4 py-2 border-b border-border text-[11px] font-mono text-muted-fg">
        <span>session {sessionId.slice(0, 8)}</span>
        <span className="truncate max-w-[40%]">cwd {workdir}</span>
        <span className="ml-auto flex items-center gap-1.5">
          <span className={`w-1.5 h-1.5 rounded-full ${closed ? "bg-border-strong" : "bg-green-500"}`} />
          {closed ? "ended" : "live"}
        </span>
        <button onClick={stop} className="px-2 py-1 rounded-md hover:bg-muted hover:text-foreground">
          Stop
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {frames.map((frame, i) => (
          <FrameView key={i} frame={frame} />
        ))}
      </div>

      {pending && (
        <div className="border-t border-amber-300 bg-amber-50 px-4 py-3">
          <div className="text-sm font-medium text-amber-900">
            Approve <code className="font-mono">{pending.tool_name}</code>?
          </div>
          <pre className="mt-1 text-xs font-mono text-amber-900 whitespace-pre-wrap break-all">
            {summarizeInput(pending.tool_input)}
          </pre>
          <div className="flex gap-2 mt-2">
            <button
              onClick={() => resolve("allow")}
              className="px-3 py-1.5 text-sm rounded-lg bg-green-600 text-white font-medium"
            >
              Approve
            </button>
            <button
              onClick={() => resolve("deny")}
              className="px-3 py-1.5 text-sm rounded-lg bg-muted text-foreground border border-border"
            >
              Deny
            </button>
          </div>
        </div>
      )}

      <div className="border-t border-border p-3 flex gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          disabled={closed}
          rows={1}
          placeholder={closed ? "Session ended" : "Message… (Enter to send, Shift+Enter for newline)"}
          className="flex-1 px-3 py-2 text-sm bg-muted border border-border rounded-lg resize-none focus:outline-none focus:border-border-strong disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={closed || !input.trim()}
          className="px-4 py-2 text-sm rounded-lg bg-foreground text-background font-medium disabled:opacity-40"
        >
          Send
        </button>
      </div>
      {error && <div className="px-4 pb-2 text-xs text-red-600 font-mono">{error}</div>}
    </div>
  );
}

function FrameView({ frame }: { frame: ChatFrame }) {
  const type = frame.type as string;

  if (type === "_user_input") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] px-3 py-2 text-sm rounded-2xl bg-foreground text-background whitespace-pre-wrap">
          {frame.text}
        </div>
      </div>
    );
  }

  if (type === "system" && frame.subtype === "init") {
    return (
      <div className="text-[11px] font-mono text-muted-fg">
        session started · {frame.model ?? "?"} · {frame.cwd ?? ""}
      </div>
    );
  }

  if (type === "assistant") {
    const texts = textBlocks(frame);
    const tools = toolUses(frame);
    return (
      <div className="space-y-2">
        {texts.map((t, i) => (
          <div key={`t${i}`} className="max-w-[80%] px-3 py-2 text-sm rounded-2xl bg-muted whitespace-pre-wrap">
            {t}
          </div>
        ))}
        {tools.map((tu, i) => (
          <div key={`u${i}`} className="text-xs font-mono text-muted-fg">
            → {tu.name}(<span className="text-foreground break-all">{summarizeInput(tu.input)}</span>)
          </div>
        ))}
      </div>
    );
  }

  if (type === "result") {
    return (
      <div className={`text-[11px] font-mono ${frame.is_error ? "text-red-600" : "text-muted-fg"}`}>
        {frame.is_error ? "error" : "✓ done"}
        {typeof frame.total_cost_usd === "number" ? ` · $${frame.total_cost_usd.toFixed(4)}` : ""}
      </div>
    );
  }

  if (type === "awaiting_approval") {
    return (
      <div className="text-[11px] font-mono text-amber-700">awaiting approval: {frame.tool_name}</div>
    );
  }

  if (type === "approval_resolved") {
    return (
      <div className="text-[11px] font-mono text-muted-fg">approval {frame.decision}</div>
    );
  }

  if (type === "_closed") {
    return <div className="text-[11px] font-mono text-muted-fg">session ended</div>;
  }

  return null;
}
