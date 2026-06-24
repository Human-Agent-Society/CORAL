import { useEffect, useState, useMemo } from "react";
import { api, type Note, type Skill, type NotesGraphResponse } from "../lib/api";
import { useSSE } from "../hooks/useSSE";
import NotesGraph from "../components/NotesGraph";

const CATEGORY_ORDER = ["research", "experiments", "other", "raw"];
const CATEGORY_LABELS: Record<string, string> = {
  research: "Research",
  experiments: "Experiments",
  raw: "Raw Sources",
  other: "Other",
};

type View = "list" | "graph";

export default function Knowledge() {
  const [notes, setNotes] = useState<Note[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [graph, setGraph] = useState<NotesGraphResponse>({ nodes: [], edges: [] });
  const [expandedNote, setExpandedNote] = useState<number | null>(null);
  const [view, setView] = useState<View>("list");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const refreshNotes = () => api.notes().then(setNotes).catch(() => {});
  const refreshGraph = () => api.notesGraph().then(setGraph).catch(() => {});
  const refreshSkills = () => api.skills().then(setSkills).catch(() => {});

  useEffect(() => {
    refreshNotes();
    refreshGraph();
    refreshSkills();
  }, []);

  useSSE({
    "note:update": () => {
      refreshNotes();
      refreshGraph();
    },
  });

  const groupedNotes = useMemo(() => {
    const groups: Record<string, Note[]> = {};
    for (const note of notes) {
      const cat = note.category || "other";
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(note);
    }
    const sorted = Object.entries(groups).sort(([a], [b]) => {
      const ia = CATEGORY_ORDER.indexOf(a);
      const ib = CATEGORY_ORDER.indexOf(b);
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib);
    });
    return sorted;
  }, [notes]);

  const selectedNote = useMemo(
    () => (selectedId ? notes.find((n) => n.relative_path === selectedId || n.filename === selectedId) : null),
    [selectedId, notes],
  );

  return (
    <>
      {/* LEFT COLUMN — Notes */}
      <div className="overflow-y-auto border-r border-border p-5">
        <div className="flex items-center justify-between mb-3">
          <p className="font-mono text-[10px] tracking-widest uppercase text-muted-fg">
            Notes ({notes.length})
          </p>
          <div className="flex font-mono text-[10px] uppercase tracking-wider border border-border rounded-md overflow-hidden">
            {(["list", "graph"] as View[]).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-2.5 py-1 transition-colors ${
                  view === v ? "bg-foreground text-background" : "text-muted-fg hover:bg-muted"
                }`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>

        {notes.length === 0 ? (
          <div className="border border-border rounded-xl p-5">
            <p className="font-display text-[14px] font-semibold mb-1.5">No notes yet</p>
            <p className="font-body text-[12px] text-muted-fg leading-relaxed">
              Agents document learnings after evaluations. Notes appear here as agents
              discover patterns, identify failure modes, and refine their strategies.
            </p>
          </div>
        ) : view === "graph" ? (
          <div>
            <NotesGraph
              nodes={graph.nodes}
              edges={graph.edges}
              selected={selectedId}
              onSelect={(id) => setSelectedId((cur) => (cur === id ? null : id))}
            />
            {selectedNote ? (
              <div className="mt-3 border border-border rounded-xl p-4 bg-background">
                {(selectedNote.status || typeof selectedNote.confidence === "number") && (
                  <div className="flex items-center gap-3 mb-2">
                    {selectedNote.status && <StatusChip status={selectedNote.status} />}
                    {typeof selectedNote.confidence === "number" && (
                      <ConfidenceBar value={selectedNote.confidence} />
                    )}
                  </div>
                )}
                <p className="font-display text-[15px] font-semibold leading-snug">
                  {selectedNote.title}
                </p>
                <p className="font-mono text-[10px] text-muted-fg mt-0.5 mb-3">
                  {selectedNote.relative_path}
                </p>
                <div className="border-l-2 border-border pl-3 font-body text-[13px] leading-relaxed whitespace-pre-wrap text-muted-fg">
                  {selectedNote.body}
                </div>
              </div>
            ) : (
              <p className="mt-3 font-body text-[12px] text-muted-fg">
                Click a node to read the note. Edges show how notes relate; node color is the
                claim status.
              </p>
            )}
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
                          setExpandedNote(expandedNote === note.index ? null : note.index)
                        }
                        className="w-full text-left py-3.5 px-4 hover:bg-muted/50 transition-colors duration-100 flex items-start gap-3"
                      >
                        <div className="mt-1 shrink-0">
                          <StatusDot status={note.status} />
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
            <p className="font-display text-[14px] font-semibold mb-1.5">No skills yet</p>
            <p className="font-body text-[12px] text-muted-fg leading-relaxed">
              Agents package reusable tools and techniques as skills. Skills appear here as
              agents build solutions that can be shared across the team.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {skills.map((skill) => (
              <div
                key={skill.name}
                className="p-4 border border-border rounded-lg hover:bg-muted/50 transition-colors duration-100"
              >
                <p className="font-display text-[14px] font-semibold mb-1">{skill.name}</p>
                {skill.description && (
                  <p className="font-body text-[13px] text-muted-fg mb-2">{skill.description}</p>
                )}
                <div className="font-mono text-[10px] text-muted-fg flex gap-3">
                  <span>By: {skill.creator}</span>
                  {skill.created && <span>{String(skill.created).slice(0, 10)}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

/* Small status dot for the list view — colored when the note carries a claim status. */
function StatusDot({ status }: { status?: string }) {
  const cls =
    status === "confirmed"
      ? "border-green-500 bg-green-500"
      : status === "refuted"
        ? "border-red-500 bg-red-500"
        : status === "untested"
          ? "border-blue-500 bg-blue-500"
          : "border-foreground bg-background";
  return <div className={`w-2.5 h-2.5 border-2 rounded-full ${cls}`} />;
}

const STATUS_DOT: Record<string, string> = {
  confirmed: "bg-green-500",
  refuted: "bg-red-500",
  untested: "bg-blue-500",
};

/* Mode-safe status chip — color carried by the dot, text in foreground. */
function StatusChip({ status }: { status: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-foreground">
      <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[status] ?? "bg-border-strong"}`} />
      {status}
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const v = Math.max(0, Math.min(1, value));
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-[10px] text-muted-fg">
      conf
      <span className="inline-block h-1.5 w-16 overflow-hidden rounded-full bg-muted align-middle">
        <span className="block h-full bg-foreground" style={{ width: `${v * 100}%` }} />
      </span>
      {v.toFixed(2)}
    </span>
  );
}
