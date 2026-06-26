import { useEffect, useState } from "react";
import { api } from "../lib/api";

interface Props {
  initialPath?: string;
  onSelect: (path: string) => void;
  onClose: () => void;
}

interface Entry {
  name: string;
  path: string;
}

export default function DirPicker({ initialPath, onSelect, onClose }: Props) {
  const [path, setPath] = useState("");
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function load(p?: string) {
    setLoading(true);
    setError(null);
    api
      .chatBrowse(p)
      .then((res) => {
        setPath(res.path);
        setParent(res.parent);
        setEntries(res.entries);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load(initialPath || undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/30 flex items-center justify-center p-8"
      onClick={onClose}
    >
      <div
        className="bg-background border border-border rounded-xl w-full max-w-lg max-h-[70vh] flex flex-col shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-4 py-3 border-b border-border flex items-center gap-2">
          <span className="font-display text-sm">Choose a directory</span>
          <button onClick={onClose} className="ml-auto text-muted-fg hover:text-foreground text-sm">
            ✕
          </button>
        </div>

        <div className="px-4 py-2 border-b border-border font-mono text-[11px] text-muted-fg truncate">
          {loading ? "…" : path || "—"}
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-2">
          {parent && (
            <button
              onClick={() => load(parent)}
              className="w-full text-left px-3 py-1.5 text-sm rounded-md hover:bg-muted font-mono text-muted-fg"
            >
              ../
            </button>
          )}
          {entries.map((e) => (
            <button
              key={e.path}
              onClick={() => load(e.path)}
              className="w-full text-left px-3 py-1.5 text-sm rounded-md hover:bg-muted font-mono flex items-center gap-2"
            >
              <span className="text-muted-fg">📁</span>
              {e.name}
            </button>
          ))}
          {!loading && entries.length === 0 && !error && (
            <div className="px-3 py-2 text-xs text-muted-fg">No sub-folders.</div>
          )}
          {error && <div className="px-3 py-2 text-xs text-red-600 font-mono">{error}</div>}
        </div>

        <div className="px-4 py-3 border-t border-border flex gap-2">
          <button
            onClick={() => onSelect(path)}
            disabled={!path}
            className="px-4 py-2 text-sm rounded-lg bg-foreground text-background font-medium disabled:opacity-40"
          >
            Select this folder
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-lg text-muted-fg hover:bg-muted"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
