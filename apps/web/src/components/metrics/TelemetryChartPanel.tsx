import type { ReactNode } from "react";

/** Shared chrome for Recharts tooltips — one visual system across metrics charts. */
export function TelemetryTooltipFrame({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-sm rounded border border-[var(--border-subtle)] bg-spire-panel-raised px-2 py-1.5 font-telemetry text-[13px] text-spire-primary shadow-md">
      {children}
    </div>
  );
}

/** Inset strip header + panel body (Monitor-style chassis). */
export function TelemetryChartPanel({
  title,
  caption,
  children,
  className = "",
}: {
  title: string;
  caption?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`spire-section-reveal overflow-hidden rounded border border-spire-border-subtle bg-spire-panel/90 ${className}`}
    >
      <div className="border-b border-spire-border-subtle bg-spire-panel-raised px-3 py-2">
        <h3 className="font-console text-[13px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
          {title}
        </h3>
        {caption ? (
          <p className="mt-1 text-[13px] font-normal normal-case leading-snug text-[var(--text-label)]">
            {caption}
          </p>
        ) : null}
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}
