import { useState } from "react";
import type { RubricData } from "../lib/api";

interface Props {
  rubric: RubricData;
}

export default function RubricPanel({ rubric }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  const { versions, latest_scores, judge } = rubric;
  const current = versions.length > 0 ? versions[versions.length - 1] : null;

  if (!current && judge.total_evals === 0) return null;

  return (
    <div>
      <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
        Evaluation Rubric
      </p>

      {/* Judge status card */}
      <div className="p-3 border border-border rounded-lg bg-muted/50 mb-2">
        <div className="flex items-center justify-between mb-1.5">
          <span className="font-mono text-[12px] font-medium">
            Judge {judge.persistent ? "(persistent)" : "(stateless)"}
          </span>
          <span
            className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
              judge.successful_evals > 0
                ? "bg-emerald-500/10 text-emerald-600"
                : "bg-amber-500/10 text-amber-600"
            }`}
          >
            {judge.successful_evals}/{judge.total_evals} evals
          </span>
        </div>
        <div className="font-mono text-[11px] text-muted-fg flex gap-3">
          {judge.crash_count > 0 && (
            <span className="text-red-500">{judge.crash_count} crashed</span>
          )}
          {judge.session_id && (
            <span title={judge.session_id}>
              session {judge.session_id.slice(0, 8)}...
            </span>
          )}
        </div>
      </div>

      {/* Current rubric */}
      {current && (
        <div className="p-3 border border-border rounded-lg bg-muted/50">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[12px] font-medium">
              v{current.version}
            </span>
            <span className="font-mono text-[10px] text-muted-fg">
              {current.criteria_count} criteria &middot;{" "}
              {current.total_weight.toFixed(1)} weight
            </span>
          </div>

          {/* Criteria list */}
          <div className="space-y-1">
            {(expanded ? current.criteria : current.criteria.slice(0, 5)).map(
              (c) => {
                const verdict = latest_scores[c.name];
                return (
                  <div
                    key={c.name}
                    className="flex items-start gap-1.5 font-mono text-[11px]"
                    title={c.description}
                  >
                    <span className="shrink-0 mt-px">
                      {verdict === "PASS" ? (
                        <span className="text-emerald-500">&#10003;</span>
                      ) : verdict === "FAIL" ? (
                        <span className="text-red-500">&#10007;</span>
                      ) : (
                        <span className="text-muted-fg">&middot;</span>
                      )}
                    </span>
                    <span className="text-muted-fg w-6 text-right shrink-0">
                      {c.weight}
                    </span>
                    <span className="truncate">{c.name}</span>
                  </div>
                );
              }
            )}
          </div>

          {current.criteria.length > 5 && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="w-full mt-1.5 font-mono text-[10px] text-muted-fg hover:text-foreground transition-colors"
            >
              {expanded
                ? "show less"
                : `+${current.criteria.length - 5} more criteria`}
            </button>
          )}

          {/* Evolution timeline */}
          {versions.length > 1 && (
            <div className="mt-2 pt-2 border-t border-border">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="font-mono text-[10px] text-muted-fg hover:text-foreground transition-colors"
              >
                {showHistory ? "hide" : "show"} evolution (v1 → v
                {current.version})
              </button>

              {showHistory && (
                <div className="mt-2 space-y-1.5">
                  {versions.map((v) => (
                    <div
                      key={v.version}
                      className="font-mono text-[10px] text-muted-fg"
                    >
                      <span className="font-medium text-foreground">
                        v{v.version}
                      </span>{" "}
                      &middot; {v.criteria_count} criteria
                      {v.evolution_notes && (
                        <p className="mt-0.5 text-[9px] leading-tight opacity-75 line-clamp-2">
                          {v.evolution_notes}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
