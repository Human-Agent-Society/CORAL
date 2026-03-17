import type { Attempt } from "../lib/api";
import StatusBadge from "./StatusBadge";

interface Props {
  attempt: Attempt;
  rank: number;
  expanded: boolean;
  onToggle: () => void;
  highlight?: boolean;
}

export default function AttemptRow({ attempt: a, rank, expanded, onToggle, highlight }: Props) {
  return (
    <>
      <tr
        onClick={onToggle}
        className={`border-b border-border cursor-pointer transition-colors duration-100 ${
          expanded ? "bg-muted" : highlight ? "bg-muted/80" : "hover:bg-muted/50"
        }`}
      >
        <td className="py-2.5 px-3 font-mono text-xs text-muted-fg">{rank}</td>
        <td className="py-2.5 px-3 font-mono text-[13px] font-medium">
          {a.score != null ? String(a.score) : "---"}
        </td>
        <td className="py-2.5 px-3 font-mono text-xs">{a.agent_id}</td>
        <td className="py-2.5 px-3">
          <StatusBadge status={a.status} />
        </td>
        <td className="py-2.5 px-3 font-mono text-xs text-muted-fg whitespace-nowrap">
          {formatTime(a.timestamp)}
        </td>
      </tr>

      {expanded && (
        <tr>
          <td colSpan={5} className="bg-muted border-b border-border">
            <div className="px-6 py-4">
              {/* Title */}
              {a.title && (
                <p className="font-display text-[14px] font-semibold mb-3">
                  {a.title}
                </p>
              )}

              {/* Metadata grid */}
              <div className="grid grid-cols-2 gap-x-8 gap-y-3 mb-4">
                <Field label="Score">
                  <span className="font-display text-lg font-bold">
                    {a.score != null ? String(a.score) : "---"}
                  </span>
                </Field>
                <Field label="Agent">
                  <span className="font-mono text-[13px]">{a.agent_id}</span>
                </Field>
                <Field label="Timestamp">
                  <span className="font-mono text-[13px]">
                    {new Date(a.timestamp).toLocaleString()}
                  </span>
                </Field>
                <Field label="Status">
                  <StatusBadge status={a.status} />
                </Field>
                <Field label="Commit">
                  <span className="font-mono text-[13px]">{a.commit_hash}</span>
                </Field>
                <Field label="Parent">
                  <span className="font-mono text-[13px] text-muted-fg">
                    {a.parent_hash ? a.parent_hash.slice(0, 12) + "..." : "---"}
                  </span>
                </Field>
              </div>

              {/* Feedback */}
              {a.feedback && (
                <div>
                  <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-2">
                    Feedback
                  </p>
                  <div className="border border-border rounded-lg p-4 bg-background">
                    <pre className="font-mono text-xs whitespace-pre-wrap leading-relaxed">
                      {a.feedback}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="font-mono text-[10px] text-muted-fg tracking-widest uppercase mb-0.5">
        {label}
      </p>
      {children}
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString([], {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso.slice(0, 16);
  }
}
