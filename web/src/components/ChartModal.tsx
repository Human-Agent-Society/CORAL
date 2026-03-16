import { useEffect } from "react";
import { createPortal } from "react-dom";
import ScoreChart from "./ScoreChart";
import type { Attempt } from "../lib/api";

interface Props {
  attempts: Attempt[];
  direction?: "maximize" | "minimize";
  onClose: () => void;
}

export default function ChartModal({ attempts, direction, onClose }: Props) {
  // Close on Esc
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  // Prevent body scroll while modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-foreground/40"
        onClick={onClose}
      />

      {/* Modal card */}
      <div className="relative z-10 bg-background border border-border rounded-xl m-4 w-[calc(100vw-2rem)] h-[calc(100vh-2rem)] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-2.5 border-b border-border shrink-0">
          <span className="font-mono text-[11px] text-muted-fg uppercase tracking-widest">
            Score Chart — {attempts.filter((a) => a.score !== null).length} scored attempts
          </span>
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] text-muted-fg">
              Scroll to zoom / Drag to pan
            </span>
            <button
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center rounded-md hover:bg-muted transition-colors duration-100 text-muted-fg hover:text-foreground"
              title="Close (Esc)"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* Chart area */}
        <div className="flex-1 min-h-0 p-5">
          <ScoreChart
            attempts={attempts}
            direction={direction}
            expanded={true}
          />
        </div>
      </div>
    </div>,
    document.body
  );
}
