import { Link } from "react-router-dom";

export type SpireNavPage = "monitor" | "metrics" | "map";

const linkCls =
  "font-console text-xs font-semibold uppercase tracking-wide text-[var(--accent-primary)] hover:text-[var(--accent-primary-hover)]";

export type SpireAgentNavProps = {
  page: SpireNavPage;
  /** Appended to /metrics and /metrics/map when set (e.g. `?run=...`). */
  runQuery: string;
};

const pageLabel: Record<SpireNavPage, string> = {
  monitor: "Monitor",
  metrics: "Run metrics",
  map: "Run map",
};

export function SpireAgentNav({ page, runQuery }: SpireAgentNavProps) {
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1">
      <span className="font-console text-sm font-bold tracking-[0.12em] text-[var(--text-primary)]">
        SPIRE AGENT
        <span className="ml-2 text-[var(--text-label)]">·</span>
        <span className="ml-2 text-[var(--accent-primary)]">{pageLabel[page]}</span>
      </span>
      <nav
        className="flex flex-wrap items-center gap-x-2 gap-y-1 border-l border-[color-mix(in_srgb,var(--border-subtle)_85%,transparent)] pl-3"
        aria-label="Other pages"
      >
        {page !== "monitor" ? (
          <Link to="/" className={linkCls}>
            Monitor
          </Link>
        ) : null}
        {page !== "metrics" ? (
          <Link to={runQuery ? `/metrics${runQuery}` : "/metrics"} className={linkCls}>
            Run metrics
          </Link>
        ) : null}
        {page !== "map" ? (
          <Link
            to={runQuery ? `/metrics/map${runQuery}` : "/metrics/map"}
            className={linkCls}
          >
            Run map
          </Link>
        ) : null}
      </nav>
    </div>
  );
}
