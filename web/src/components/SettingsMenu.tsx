import { useEffect, useRef, useState } from "react";
import { useTheme, type ThemePreference } from "../hooks/useTheme";

const themeOptions: Array<{
  value: ThemePreference;
  label: string;
  icon: "sun" | "moon" | "system";
}> = [
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
  { value: "system", label: "System", icon: "system" },
];

export default function SettingsMenu() {
  const [open, setOpen] = useState(false);
  const { preference, setPreference } = useTheme();
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      buttonRef.current?.focus();
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-label="Dashboard settings"
        aria-haspopup="dialog"
        aria-expanded={open}
        title="Settings"
        className={`flex h-8 w-8 items-center justify-center rounded-lg border bg-background transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
          open
            ? "border-foreground bg-foreground text-background"
            : "border-border text-muted-fg hover:border-border-strong hover:bg-muted hover:text-foreground"
        }`}
      >
        <svg
          width="16"
          height="16"
          viewBox="0 0 20 20"
          fill="none"
          aria-hidden="true"
          className={`transition-transform duration-200 ${open ? "rotate-[22deg]" : "rotate-0"}`}
        >
          <path
            d="M8.65 2.15h2.7l.45 1.72c.42.16.82.39 1.18.68l1.7-.5 1.35 2.34-1.25 1.23c.04.22.06.45.06.69s-.02.47-.06.69l1.25 1.23-1.35 2.34-1.7-.5c-.36.29-.76.52-1.18.68l-.45 1.72h-2.7l-.45-1.72a5 5 0 0 1-1.18-.68l-1.7.5-1.35-2.34L5.22 9a3.9 3.9 0 0 1 0-1.38L3.97 6.39l1.35-2.34 1.7.5c.36-.29.76-.52 1.18-.68l.45-1.72Z"
            stroke="currentColor"
            strokeWidth="1.35"
            strokeLinejoin="round"
          />
          <circle cx="10" cy="8.31" r="2.15" stroke="currentColor" strokeWidth="1.35" />
        </svg>
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Dashboard settings"
          className="absolute right-0 top-full z-[70] mt-2 w-[320px] origin-top-right rounded-2xl border border-border bg-background/95 p-2 shadow-[0_20px_64px_rgba(0,0,0,0.28)] backdrop-blur-2xl"
        >
          <div className="flex items-start justify-between px-3 pb-2.5 pt-2">
            <div>
              <p className="font-display text-[15px] font-semibold leading-none">Settings</p>
              <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.16em] text-muted-fg">
                Dashboard
              </p>
            </div>
            <span className="rounded-md border border-border bg-muted px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted-fg">
              Local
            </span>
          </div>

          <section className="rounded-xl border border-border bg-muted/60 p-3">
            <div className="mb-2.5 flex items-center justify-between">
              <div>
                <h2 className="font-body text-[12px] font-medium leading-none">Appearance</h2>
                <p className="mt-1 font-mono text-[9px] uppercase tracking-wider text-muted-fg">
                  Theme
                </p>
              </div>
              <ThemeGlyph icon={preference === "dark" ? "moon" : preference === "light" ? "sun" : "system"} />
            </div>

            <div className="grid grid-cols-3 gap-1.5" role="radiogroup" aria-label="Theme">
              {themeOptions.map((option) => {
                const selected = preference === option.value;
                return (
                  <button
                    key={option.value}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setPreference(option.value)}
                    className={`flex min-h-[66px] flex-col items-center justify-center gap-1.5 rounded-lg border px-2 py-2 transition-colors duration-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-foreground focus-visible:ring-offset-2 focus-visible:ring-offset-muted ${
                      selected
                        ? "border-foreground bg-foreground text-background"
                        : "border-border bg-background/70 text-muted-fg hover:border-border-strong hover:bg-background hover:text-foreground"
                    }`}
                  >
                    <ThemeGlyph icon={option.icon} />
                    <span className="font-mono text-[9px] font-medium uppercase tracking-wider">
                      {option.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>

          <p className="px-3 pb-1.5 pt-2.5 font-body text-[11px] leading-relaxed text-muted-fg">
            {preference === "system"
              ? "Matches your device appearance automatically."
              : "Saved for this browser."}
          </p>
        </div>
      )}
    </div>
  );
}

function ThemeGlyph({ icon }: { icon: "sun" | "moon" | "system" }) {
  if (icon === "sun") {
    return (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="10" r="3" fill="currentColor" />
        <path
          d="M10 2v1.4M10 16.6V18M18 10h-1.4M3.4 10H2M15.66 4.34l-1 1M5.34 14.66l-1 1M15.66 15.66l-1-1M5.34 5.34l-1-1"
          stroke="currentColor"
          strokeWidth="1.35"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  if (icon === "moon") {
    return (
      <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M16.45 12.25A6.55 6.55 0 0 1 7.75 3.55a6.6 6.6 0 1 0 8.7 8.7Z" fill="currentColor" />
      </svg>
    );
  }

  return (
    <svg width="16" height="16" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="2.5" y="3.25" width="15" height="10.5" rx="1.75" stroke="currentColor" strokeWidth="1.35" />
      <path d="M7 16.75h6M10 13.75v3" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" />
      <path d="M10 3.25h5.75a1.75 1.75 0 0 1 1.75 1.75v7a1.75 1.75 0 0 1-1.75 1.75H10V3.25Z" fill="currentColor" opacity=".18" />
    </svg>
  );
}
