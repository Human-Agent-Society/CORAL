const styles: Record<string, string> = {
  improved:
    "bg-foreground text-background",
  baseline:
    "bg-muted text-muted-fg border border-border",
  regressed:
    "border-2 border-foreground text-foreground",
  crashed:
    "bg-foreground text-background line-through",
  timeout:
    "border-2 border-foreground text-foreground italic",
  active:
    "bg-foreground text-background",
  idle:
    "bg-muted text-muted-fg border border-border",
  stopped:
    "border border-border text-muted-fg",
};

export default function StatusBadge({ status }: { status: string }) {
  const cls = styles[status] || styles.baseline;
  return (
    <span
      className={`inline-block px-2.5 py-0.5 text-[9px] font-mono font-medium uppercase tracking-widest rounded-full ${cls}`}
    >
      {status}
    </span>
  );
}
