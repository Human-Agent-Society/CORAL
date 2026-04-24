import { useEffect, useState, useMemo } from "react";
import { api, type Note, type Skill } from "../lib/api";
import { useSSE } from "../hooks/useSSE";

const CATEGORY_ORDER = ["research", "experiments", "other", "raw"];
const CATEGORY_LABELS: Record<string, string> = {
  research: "Research",
  experiments: "Experiments",
  raw: "Raw Sources",
  other: "Other",
};

export default function Knowledge() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [expandedNote, setExpandedNote] = useState<number | null>(null);

  const refreshNotes = () => api.notes().then(setNotes).catch(() => {});
  const refreshSkills = () => api.skills().then(setSkills).catch(() => {});

  useEffect(() => {
    refreshNotes();
    refreshSkills();
  }, []);

  useSSE({ "note:update": refreshNotes });

  const groupedNotes = useMemo(() => {
    const groups: Record<string, Note[]> = {};
    for (const note of notes) {
      const cat = note.category || "other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(note);
    }
    // Sort categories by defined order, unknown categories at the end
    const sorted = Object.entries(groups).sort(([a], [b]) => {
      const ia = CATEGORY_ORDER.indexOf(a);
      const ib = CATEGORY_ORDER.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
    return sorted;
  }, [notes]);

  return (
    <>
      {/* LEFT COLUMN — Notes */}
      <div className="overflow-y-auto border-r border-border p-5">
        <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
          Notes ({notes.length})
        </p>

        {notes.length === 0 ? (
          <div className="border border-border rounded-xl p-5">
            <p className="font-display text-[14px] font-semibold mb-1.5">
              No notes yet
            </p>
            <p className="font-body text-[12px] text-muted-fg leading-relaxed">
              Agents document learnings after evaluations. Notes appear here as
              agents discover patterns, identify failure modes, and refine their
              strategies.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {groupedNotes.map(([category, catNotes]) => (
              <div key={category}>
                <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-2">
                  {CATEGORY_LABELS[category] || category} ({catNotes.length})
                </p>
                <div className="border border-border rounded-xl overflow-hidden">
                  {[...catNotes].reverse().map((note) => (
                    <div key={note.index} className="border-b border-border last:border-b-0">
                      <button
                        onClick={() =>
                          setExpandedNote(
                            expandedNote === note.index ? null : note.index
                          )
                        }
                        className="w-full text-left py-3.5 px-4 hover:bg-muted/50 transition-colors duration-100 flex items-start gap-3"
                      >
                        <div className="mt-1 shrink-0">
                          <div className="w-2.5 h-2.5 border-2 border-foreground bg-background rounded-full" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-mono text-[10px] text-muted-fg mb-0.5">
                            {note.date}
                            {note.relative_path && (
                              <span className="ml-2 opacity-60">{note.relative_path}</span>
                            )}
                          </p>
                          <p className="font-display text-[14px] font-semibold leading-snug">
                            {note.title}
                          </p>
                        </div>
                        <span className="font-mono text-xs text-muted-fg shrink-0">
                          {expandedNote === note.index ? "−" : "+"}
                        </span>
                      </button>

                      {expandedNote === note.index && (
                        <div className="pb-4 pl-10 pr-4">
                          <div className="border-l-2 border-border pl-4">
                            <div className="font-body text-[13px] leading-relaxed whitespace-pre-wrap text-muted-fg">
                              {note.body}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* RIGHT COLUMN — Skills */}
      <div className="overflow-y-auto p-5">
        <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg mb-3">
          Skills ({skills.length})
        </p>

        {skills.length === 0 ? (
          <div className="border border-border rounded-xl p-5">
            <p className="font-display text-[14px] font-semibold mb-1.5">
              No skills yet
            </p>
            <p className="font-body text-[12px] text-muted-fg leading-relaxed">
              Agents package reusable tools and techniques as skills. Skills appear
              here as agents build solutions that can be shared across the team.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {skills.map((skill) => (
              <div
                key={skill.name}
                className="p-4 border border-border rounded-lg hover:bg-muted/50 transition-colors duration-100"
              >
                <p className="font-display text-[14px] font-semibold mb-1">
                  {skill.name}
                </p>
                {skill.description && (
                  <p className="font-body text-[13px] text-muted-fg mb-2">
                    {skill.description}
                  </p>
                )}
                <div className="font-mono text-[10px] text-muted-fg flex gap-3">
                  <span>By: {skill.creator}</span>
                  {skill.created && (
                    <span>{String(skill.created).slice(0, 10)}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}
