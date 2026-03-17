import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { ReplayState } from "../hooks/useReplay";
import { REPLAY_SPEEDS } from "../hooks/useReplay";

interface Props {
  replay: ReplayState;
}

export default function ReplayBar({ replay }: Props) {
  const { togglePlay, stepBack, stepForward, stop } = replay;

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT") return;
      switch (e.key) {
        case " ":
          e.preventDefault();
          togglePlay();
          break;
        case "ArrowLeft":
          stepBack();
          break;
        case "ArrowRight":
          stepForward();
          break;
        case "Escape":
          stop();
          break;
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [togglePlay, stepBack, stepForward, stop]);

  if (!replay.active) return null;

  const pct = replay.progress * 100;

  const handleBarClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    replay.seek(Math.round(ratio * replay.totalAttempts));
  };

  const la = replay.latestAttempt;

  return createPortal(
    <div className="fixed bottom-0 left-0 right-0 z-[90] px-6 pb-4 pointer-events-none">
      <div className="max-w-3xl mx-auto pointer-events-auto">
        <div className="bg-foreground text-background rounded-xl shadow-2xl overflow-hidden">
          {/* Seekable progress bar */}
          <div
            className="h-1.5 bg-background/15 cursor-pointer group relative"
            onClick={handleBarClick}
          >
            <div
              className="absolute inset-y-0 left-0 bg-background/70 transition-[width] duration-100"
              style={{ width: `${pct}%` }}
            />
            <div className="absolute inset-0 bg-background/10 opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>

          {/* Controls */}
          <div className="flex items-center gap-3 px-4 py-2">
            {/* Transport */}
            <div className="flex items-center gap-0.5">
              <button
                onClick={replay.stepBack}
                className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-background/15 transition-colors"
                title="Step back (←)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M6 6h2v12H6zm3.5 6l8.5 6V6z" />
                </svg>
              </button>

              <button
                onClick={replay.togglePlay}
                className="w-8 h-8 flex items-center justify-center rounded-lg bg-background/15 hover:bg-background/25 transition-colors"
                title={replay.playing ? "Pause (Space)" : "Play (Space)"}
              >
                {replay.playing ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M6 4h4v16H6zM14 4h4v16h-4z" />
                  </svg>
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                )}
              </button>

              <button
                onClick={replay.stepForward}
                className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-background/15 transition-colors"
                title="Step forward (→)"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z" />
                </svg>
              </button>
            </div>

            {/* Counter */}
            <span className="font-mono text-[11px] tabular-nums min-w-[70px]">
              {replay.currentIndex} / {replay.totalAttempts}
            </span>

            {/* Latest attempt info */}
            {la && (
              <div className="flex items-center gap-2 ml-1">
                <span className="font-mono text-[12px] font-medium">
                  {la.score != null ? la.score.toFixed(4) : "---"}
                </span>
                <span className="font-mono text-[10px] opacity-50">
                  {la.agent_id}
                </span>
                <span
                  className={`inline-block w-1.5 h-1.5 rounded-full ${
                    la.status === "improved"
                      ? "bg-green-400"
                      : la.status === "crashed"
                        ? "bg-red-400"
                        : la.status === "regressed"
                          ? "bg-orange-400"
                          : "bg-background/40"
                  }`}
                />
              </div>
            )}

            {/* Speed */}
            <div className="flex items-center gap-0.5 ml-auto">
              <span className="font-mono text-[9px] uppercase tracking-widest opacity-40 mr-1.5">
                Speed
              </span>
              {REPLAY_SPEEDS.map((s) => (
                <button
                  key={s}
                  onClick={() => replay.setSpeed(s)}
                  className={`px-1.5 py-0.5 font-mono text-[10px] rounded transition-colors ${
                    replay.speed === s
                      ? "bg-background text-foreground"
                      : "opacity-50 hover:opacity-80"
                  }`}
                >
                  {s}x
                </button>
              ))}
            </div>

            {/* Exit */}
            <button
              onClick={replay.stop}
              className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-background/15 transition-colors ml-2"
              title="Exit replay (Esc)"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
}
